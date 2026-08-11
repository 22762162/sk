"""手机 App 闭环的本机私有、版本化存储。

原始出生信息、问事背景与复盘结果只写入本机 SQLite，不经本模块联网。
预测正文采用 append-only 快照：数据库触发器禁止 UPDATE/DELETE；复盘单独存表，
因此个人校准只能影响未来预测的置信度，不能回写历史结论。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "consult-engine" / "appdata" / "sanjian-app.sqlite3"
DEFAULT_LEGACY_PREDICTIONS = ROOT / "consult-engine" / "predictions" / "predictions.jsonl"
SCHEMA_VERSION = 2
MIN_CALIBRATION_SAMPLES = 8
VALID_OUTCOMES = {"hit", "partial", "miss", "unclear"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class StoreConflict(RuntimeError):
    """乐观锁冲突或不可变记录重复写入。"""


class AppStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB,
                 legacy_predictions: Path | str | None = DEFAULT_LEGACY_PREDICTIONS) -> None:
        self.db_path = Path(db_path)
        self.legacy_predictions = Path(legacy_predictions) if legacy_predictions else None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
        if self.legacy_predictions:
            self.import_legacy_predictions(self.legacy_predictions)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 5000")
        con.execute("PRAGMA journal_mode = WAL")
        return con

    def _migrate(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    birth TEXT NOT NULL,
                    gender TEXT NOT NULL,
                    place TEXT NOT NULL DEFAULT '',
                    longitude REAL,
                    timezone TEXT NOT NULL,
                    zi_hour_mode TEXT NOT NULL,
                    industry TEXT NOT NULL DEFAULT '',
                    occupation TEXT NOT NULL DEFAULT '',
                    situation TEXT NOT NULL DEFAULT '',
                    research_context TEXT NOT NULL DEFAULT '',
                    research_source TEXT NOT NULL DEFAULT '',
                    research_version INTEGER NOT NULL DEFAULT 0,
                    research_confirmed_at TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
                    version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_profile
                    ON profiles(is_active) WHERE is_active = 1;
                CREATE TABLE IF NOT EXISTS inquiries (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT REFERENCES profiles(id),
                    period TEXT NOT NULL,
                    category TEXT NOT NULL,
                    question TEXT NOT NULL,
                    background TEXT NOT NULL DEFAULT '',
                    asked_at TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS inquiry_profile_time
                    ON inquiries(profile_id, asked_at DESC);
                CREATE TABLE IF NOT EXISTS prediction_snapshots (
                    id TEXT PRIMARY KEY,
                    inquiry_id TEXT NOT NULL UNIQUE REFERENCES inquiries(id),
                    profile_id TEXT REFERENCES profiles(id),
                    snapshot_json TEXT NOT NULL,
                    locked_at TEXT NOT NULL,
                    algorithm_version TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    calibration_version TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS prediction_profile_time
                    ON prediction_snapshots(profile_id, locked_at DESC);
                CREATE TABLE IF NOT EXISTS prediction_reviews (
                    id TEXT PRIMARY KEY,
                    prediction_id TEXT NOT NULL UNIQUE REFERENCES prediction_snapshots(id),
                    outcome TEXT NOT NULL CHECK (outcome IN ('hit','partial','miss','unclear')),
                    actual_at TEXT,
                    result TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS immutable_prediction_update
                    BEFORE UPDATE ON prediction_snapshots
                    BEGIN SELECT RAISE(ABORT, 'prediction snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_prediction_delete
                    BEFORE DELETE ON prediction_snapshots
                    BEGIN SELECT RAISE(ABORT, 'prediction snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_review_update
                    BEFORE UPDATE ON prediction_reviews
                    BEGIN SELECT RAISE(ABORT, 'prediction reviews are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_review_delete
                    BEFORE DELETE ON prediction_reviews
                    BEGIN SELECT RAISE(ABORT, 'prediction reviews are append-only'); END;
                """
            )
            current = con.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()
            if current and int(current["value"]) > SCHEMA_VERSION:
                raise RuntimeError("App 数据库版本高于当前程序，拒绝降级打开")
            profile_columns = {
                str(row["name"]) for row in con.execute("PRAGMA table_info(profiles)").fetchall()
            }
            for name, definition in (
                ("research_context", "TEXT NOT NULL DEFAULT ''"),
                ("research_source", "TEXT NOT NULL DEFAULT ''"),
                ("research_version", "INTEGER NOT NULL DEFAULT 0"),
                ("research_confirmed_at", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in profile_columns:
                    con.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")
            con.execute(
                "INSERT INTO app_meta(key,value) VALUES('schema_version',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        out = dict(row)
        if "is_active" in out:
            out["is_active"] = bool(out["is_active"])
        return out

    def list_profiles(self) -> list[dict]:
        with self._connect() as con:
            rows = con.execute(
                "SELECT * FROM profiles ORDER BY is_active DESC, updated_at DESC"
            ).fetchall()
        return [self._row(r) for r in rows if r]

    def get_profile(self, profile_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return self._row(row)

    def active_profile(self) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM profiles WHERE is_active=1").fetchone()
        return self._row(row)

    def create_profile(self, values: dict) -> dict:
        now, pid = utc_now(), f"profile-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            has_any = con.execute("SELECT 1 FROM profiles LIMIT 1").fetchone() is not None
            make_active = bool(values.get("is_active")) or not has_any
            if make_active:
                con.execute("UPDATE profiles SET is_active=0")
            con.execute(
                """INSERT INTO profiles(
                    id,name,birth,gender,place,longitude,timezone,zi_hour_mode,
                    industry,occupation,situation,research_context,research_source,
                    research_version,research_confirmed_at,is_active,version,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)""",
                (pid, values["name"], values["birth"], values["gender"],
                 values.get("place", ""), values.get("longitude"), values["timezone"],
                 values["zi_hour_mode"], values.get("industry", ""),
                 values.get("occupation", ""), values.get("situation", ""),
                 values.get("research_context", ""), values.get("research_source", ""),
                 1 if values.get("research_context") else 0,
                 now if values.get("research_context") else "", int(make_active), now, now),
            )
            con.execute("COMMIT")
        return self.get_profile(pid) or {}

    def update_profile(self, profile_id: str, expected_version: int, values: dict) -> dict | None:
        now = utc_now()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            cur = con.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not cur:
                con.execute("ROLLBACK")
                return None
            if int(cur["version"]) != int(expected_version):
                con.execute("ROLLBACK")
                raise StoreConflict("基本盘已在别处更新，请刷新后重试")
            merged = {**dict(cur), **values}
            birth_changed = str(merged["birth"]) != str(cur["birth"])
            research_context = str(merged.get("research_context", ""))
            if birth_changed and "research_context" not in values:
                research_context = ""
            research_source = str(merged.get("research_source", "")) if research_context else ""
            research_changed = (
                research_context != str(cur["research_context"])
                or research_source != str(cur["research_source"])
                or (birth_changed and bool(research_context))
            )
            research_version = int(cur["research_version"]) + int(research_changed)
            research_confirmed_at = (
                now if research_changed and research_context
                else str(cur["research_confirmed_at"]) if research_context
                else ""
            )
            con.execute(
                """UPDATE profiles SET name=?,birth=?,gender=?,place=?,longitude=?,timezone=?,
                    zi_hour_mode=?,industry=?,occupation=?,situation=?,research_context=?,
                    research_source=?,research_version=?,research_confirmed_at=?,
                    version=version+1,updated_at=?
                    WHERE id=? AND version=?""",
                (merged["name"], merged["birth"], merged["gender"], merged.get("place", ""),
                 merged.get("longitude"), merged["timezone"], merged["zi_hour_mode"],
                 merged.get("industry", ""), merged.get("occupation", ""),
                 merged.get("situation", ""), research_context, research_source,
                 research_version, research_confirmed_at, now, profile_id, expected_version),
            )
            con.execute("COMMIT")
        return self.get_profile(profile_id)

    def activate_profile(self, profile_id: str) -> dict | None:
        now = utc_now()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            exists = con.execute("SELECT 1 FROM profiles WHERE id=?", (profile_id,)).fetchone()
            if not exists:
                con.execute("ROLLBACK")
                return None
            con.execute("UPDATE profiles SET is_active=0 WHERE is_active=1")
            con.execute(
                "UPDATE profiles SET is_active=1,version=version+1,updated_at=? WHERE id=?",
                (now, profile_id),
            )
            con.execute("COMMIT")
        return self.get_profile(profile_id)

    def create_inquiry(self, profile_id: str, period: str, category: str, question: str,
                       background: str, asked_at: str, period_start: str,
                       period_end: str) -> dict:
        now, qid = utc_now(), f"inquiry-{uuid.uuid4().hex[:12]}"
        with self._connect() as con:
            con.execute(
                """INSERT INTO inquiries(
                    id,profile_id,period,category,question,background,asked_at,
                    period_start,period_end,status,error,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,'running','',?,?)""",
                (qid, profile_id, period, category, question, background, asked_at,
                 period_start, period_end, now, now),
            )
        return self.get_inquiry(qid) or {}

    def get_inquiry(self, inquiry_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute("SELECT * FROM inquiries WHERE id=?", (inquiry_id,)).fetchone()
        return self._row(row)

    def set_inquiry_state(self, inquiry_id: str, status: str, error: str = "") -> None:
        if status not in {"running", "locked", "error"}:
            raise ValueError("非法问事状态")
        with self._connect() as con:
            con.execute(
                "UPDATE inquiries SET status=?,error=?,updated_at=? WHERE id=?",
                (status, error[:300], utc_now(), inquiry_id),
            )

    def lock_prediction(self, inquiry_id: str, profile_id: str | None, snapshot: dict,
                        algorithm_version: str, model_version: str, rule_version: str,
                        calibration_version: str, confidence: float,
                        prediction_id: str | None = None) -> dict:
        pid = prediction_id or f"prediction-{uuid.uuid4().hex[:12]}"
        locked_at = utc_now()
        immutable = {
            **snapshot,
            "id": pid,
            "inquiry_id": inquiry_id,
            "locked_at": locked_at,
            "algorithm_version": algorithm_version,
            "model_version": model_version,
            "rule_version": rule_version,
            "calibration_version": calibration_version,
        }
        digest = _hash(immutable)
        with self._connect() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                con.execute(
                    """INSERT INTO prediction_snapshots(
                        id,inquiry_id,profile_id,snapshot_json,locked_at,algorithm_version,
                        model_version,rule_version,calibration_version,confidence,content_hash,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (pid, inquiry_id, profile_id, _json(immutable), locked_at, algorithm_version,
                     model_version, rule_version, calibration_version, float(confidence), digest,
                     locked_at),
                )
                con.execute(
                    "UPDATE inquiries SET status='locked',updated_at=? WHERE id=?",
                    (locked_at, inquiry_id),
                )
                con.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise StoreConflict("该问事已经锁定预测，不能重复覆盖") from exc
        return self.get_prediction(pid) or {}

    def get_prediction(self, prediction_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """SELECT p.*,q.period,q.category,q.question,q.background,q.asked_at,
                    q.period_start,q.period_end,r.id AS review_id,r.outcome,r.actual_at,
                    r.result,r.note,r.created_at AS reviewed_at
                    FROM prediction_snapshots p
                    JOIN inquiries q ON q.id=p.inquiry_id
                    LEFT JOIN prediction_reviews r ON r.prediction_id=p.id
                    WHERE p.id=?""",
                (prediction_id,),
            ).fetchone()
        return self._prediction_row(row)

    @staticmethod
    def _prediction_row(row: sqlite3.Row | None) -> dict | None:
        if not row:
            return None
        raw = dict(row)
        snapshot = json.loads(raw.pop("snapshot_json"))
        review = None
        if raw.get("review_id"):
            review = {k: raw.get(k) for k in
                      ("review_id", "outcome", "actual_at", "result", "note", "reviewed_at")}
        for key in ("review_id", "outcome", "actual_at", "result", "note", "reviewed_at"):
            raw.pop(key, None)
        return {**raw, "snapshot": snapshot, "review": review}

    def list_predictions(self, profile_id: str | None = None, limit: int = 100,
                         review_state: str = "") -> list[dict]:
        where, args = [], []
        if profile_id:
            where.append("p.profile_id=?")
            args.append(profile_id)
        if review_state == "pending":
            where.append("r.id IS NULL")
        elif review_state == "reviewed":
            where.append("r.id IS NOT NULL")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        args.append(max(1, min(int(limit), 500)))
        with self._connect() as con:
            rows = con.execute(
                """SELECT p.*,q.period,q.category,q.question,q.background,q.asked_at,
                    q.period_start,q.period_end,r.id AS review_id,r.outcome,r.actual_at,
                    r.result,r.note,r.created_at AS reviewed_at
                    FROM prediction_snapshots p
                    JOIN inquiries q ON q.id=p.inquiry_id
                    LEFT JOIN prediction_reviews r ON r.prediction_id=p.id"""
                + clause + " ORDER BY p.locked_at DESC LIMIT ?",
                args,
            ).fetchall()
        return [self._prediction_row(r) for r in rows if r]

    def add_review(self, prediction_id: str, outcome: str, actual_at: str | None,
                   result: str, note: str) -> dict:
        if outcome not in VALID_OUTCOMES:
            raise ValueError("复盘结果不在允许范围内")
        rid, now = f"review-{uuid.uuid4().hex[:12]}", utc_now()
        with self._connect() as con:
            try:
                con.execute(
                    """INSERT INTO prediction_reviews(
                        id,prediction_id,outcome,actual_at,result,note,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (rid, prediction_id, outcome, actual_at, result, note, now),
                )
            except sqlite3.IntegrityError as exc:
                exists = con.execute(
                    "SELECT 1 FROM prediction_snapshots WHERE id=?", (prediction_id,)
                ).fetchone()
                if not exists:
                    raise KeyError("未找到预测") from exc
                raise StoreConflict("该预测已完成复盘；历史复盘不允许事后改判") from exc
        return self.get_prediction(prediction_id) or {}

    @staticmethod
    def _scored(outcome: str) -> float | None:
        return {"hit": 1.0, "partial": 0.5, "miss": 0.0}.get(outcome)

    def _review_rows(self, profile_id: str | None = None) -> list[dict]:
        where, args = "", []
        if profile_id:
            where, args = " WHERE p.profile_id=?", [profile_id]
        with self._connect() as con:
            rows = con.execute(
                """SELECT q.category,q.period,p.algorithm_version,p.model_version,p.rule_version,
                    p.confidence,r.outcome,r.created_at
                    FROM prediction_snapshots p
                    JOIN inquiries q ON q.id=p.inquiry_id
                    JOIN prediction_reviews r ON r.prediction_id=p.id""" + where,
                args,
            ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _metric(rows: list[dict]) -> dict:
        valid = [(AppStore._scored(r["outcome"]), float(r["confidence"])) for r in rows]
        valid = [(score, conf) for score, conf in valid if score is not None]
        unclear = sum(1 for r in rows if r["outcome"] == "unclear")
        n = len(valid)
        sufficient = n >= MIN_CALIBRATION_SAMPLES
        observed = sum(score for score, _ in valid) / n if n else None
        mean_conf = sum(conf for _, conf in valid) / n if n else None
        calibration_error = (
            sum(abs(conf - score) for score, conf in valid) / n if sufficient else None
        )
        return {
            "sample_size": n,
            "unclear": unclear,
            "minimum_sample_size": MIN_CALIBRATION_SAMPLES,
            "sufficient_sample": sufficient,
            "hit_rate": round(observed, 3) if sufficient and observed is not None else None,
            "mean_confidence": round(mean_conf, 3) if sufficient and mean_conf is not None else None,
            "calibration_error": round(calibration_error, 3)
            if calibration_error is not None else None,
            "label": "样本达到最低门槛" if sufficient else f"样本不足，仅记录数量（至少 {MIN_CALIBRATION_SAMPLES} 条）",
        }

    def stats(self, profile_id: str | None = None) -> dict:
        rows = self._review_rows(profile_id)

        def grouped(field: str) -> list[dict]:
            keys = sorted({str(r[field]) for r in rows})
            return [{"key": key, **self._metric([r for r in rows if str(r[field]) == key])}
                    for key in keys]

        with self._connect() as con:
            query = "SELECT COUNT(*) AS n FROM prediction_snapshots"
            args: list[Any] = []
            if profile_id:
                query += " WHERE profile_id=?"
                args.append(profile_id)
            total = int(con.execute(query, args).fetchone()["n"])
        return {
            "total_predictions": total,
            "reviewed": len(rows),
            "overall": self._metric(rows),
            "by_category": grouped("category"),
            "by_period": grouped("period"),
            "by_algorithm_version": grouped("algorithm_version"),
            "by_model_version": grouped("model_version"),
            "by_rule_version": grouped("rule_version"),
            "policy": "小样本不展示准确率；个人复盘只校准未来置信度，不修改历史预测或规则库。",
        }

    def calibration(self, profile_id: str, category: str, period: str,
                    raw_confidence: float) -> dict:
        rows = [r for r in self._review_rows(profile_id)
                if r["category"] == category and r["period"] == period
                and self._scored(r["outcome"]) is not None]
        if len(rows) < MIN_CALIBRATION_SAMPLES:
            return {
                "confidence": round(raw_confidence, 3),
                "version": "personal-calibration-v1:insufficient",
                "sample_size": len(rows),
                "adjusted": False,
            }
        observed = sum(self._scored(r["outcome"]) or 0.0 for r in rows) / len(rows)
        prior = sum(float(r["confidence"]) for r in rows) / len(rows)
        delta = max(-0.12, min(0.12, observed - prior))
        adjusted = max(0.2, min(0.8, raw_confidence + delta))
        through = max(str(r["created_at"]) for r in rows)
        return {
            "confidence": round(adjusted, 3),
            "version": f"personal-calibration-v1:n={len(rows)}:through={through}",
            "sample_size": len(rows),
            "adjusted": True,
        }

    def import_legacy_predictions(self, source: Path | str) -> int:
        path = Path(source)
        if not path.exists():
            return 0
        imported = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                old = json.loads(line)
            except (ValueError, TypeError):
                continue
            old_id = str(old.get("id", "")).strip()
            if not old_id:
                continue
            suffix = hashlib.sha256(old_id.encode("utf-8")).hexdigest()[:16]
            qid, pid = f"legacy-inquiry-{suffix}", f"legacy-{old_id}"
            created = old.get("created_at") or utc_now()
            inquiry = {
                "id": qid, "profile_id": None, "period": "month",
                "category": old.get("domain") or "旧版预测",
                "question": old.get("statement") or "旧版预测记录",
                "background": "", "asked_at": created,
                "period_start": old.get("window_start") or created[:10],
                "period_end": old.get("window_end") or created[:10],
                "status": "locked", "error": "", "created_at": created, "updated_at": created,
            }
            snapshot = {
                "schema_version": "prediction-snapshot-v1",
                "source": "legacy_prediction",
                "conclusion": old.get("statement") or "",
                "confidence": {"label": "low", "score": 0.35,
                               "note": "旧版记录未保存置信度，迁移后按低置信度处理"},
                "key_time_windows": [{"start": inquiry["period_start"],
                                      "end": inquiry["period_end"], "label": "旧版时间窗"}],
                "favorable_triggers": [], "unfavorable_triggers": [],
                "action_suggestions": [],
                "verifiable_events": [old.get("statement") or ""],
                "question": inquiry["question"], "category": inquiry["category"],
                "period": inquiry["period"], "asked_at": created,
                "rule_basis": {"legacy_chart_line": old.get("chart_line", ""),
                               "legacy_chart_hash": old.get("chart_hash", "")},
            }
            immutable = {
                **snapshot, "id": pid, "inquiry_id": qid, "locked_at": created,
                "algorithm_version": "legacy-prediction-v1",
                "model_version": "unknown-legacy",
                "rule_version": "legacy-unspecified",
                "calibration_version": "personal-calibration-v1:insufficient",
            }
            with self._connect() as con:
                try:
                    con.execute("BEGIN IMMEDIATE")
                    con.execute(
                        """INSERT OR IGNORE INTO inquiries(
                            id,profile_id,period,category,question,background,asked_at,period_start,
                            period_end,status,error,created_at,updated_at
                        ) VALUES(:id,:profile_id,:period,:category,:question,:background,:asked_at,
                                 :period_start,:period_end,:status,:error,:created_at,:updated_at)""",
                        inquiry,
                    )
                    cur = con.execute(
                        """INSERT OR IGNORE INTO prediction_snapshots(
                            id,inquiry_id,profile_id,snapshot_json,locked_at,algorithm_version,
                            model_version,rule_version,calibration_version,confidence,content_hash,created_at
                        ) VALUES(?,?,NULL,?,?,?,?,?,?,?,?,?)""",
                        (pid, qid, _json(immutable), created, "legacy-prediction-v1",
                         "unknown-legacy", "legacy-unspecified",
                         "personal-calibration-v1:insufficient", 0.35, _hash(immutable), created),
                    )
                    if cur.rowcount:
                        imported += 1
                    if old.get("status") in {"hit", "partial", "miss"}:
                        con.execute(
                            """INSERT OR IGNORE INTO prediction_reviews(
                                id,prediction_id,outcome,actual_at,result,note,created_at
                            ) VALUES(?,?,?,?,?,?,?)""",
                            (f"legacy-review-{suffix}", pid, old["status"], None, "",
                             old.get("note", ""), old.get("reviewed_at") or created),
                        )
                    con.execute("COMMIT")
                except sqlite3.Error:
                    if con.in_transaction:
                        con.execute("ROLLBACK")
                    raise
        return imported
