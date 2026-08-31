"""huohuo_bridge 合成测试(RFC-0003 全项拒绝矩阵;零真实数据)。"""

from __future__ import annotations

import sys
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from integrations.huohuo_bridge.config import BridgeConfig, ScopeCfg
from integrations.huohuo_bridge.service import create_app
from integrations.huohuo_bridge.source import KnowledgeRow, RevenueRow, SqlAlchemySource

TOKEN = "synthetic-token-0123456789-0123456789-ok"  # 40 字符,合成
CFG = BridgeConfig(token=TOKEN,
                   scopes={"synthetic-scope": ScopeCfg("合成范围", "p-test", ("g-1", "g-2"))})
AUTH = {"Authorization": f"Bearer {TOKEN}"}


_DB_SEQ = iter(range(10_000))


def make_db(tmp_path, know=(), rev=()):
    url = f"sqlite:///{tmp_path}/synthetic-{next(_DB_SEQ)}.db"
    eng = create_engine(url, future=True)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE knowledge_items(id TEXT, content TEXT, knowledge_layer TEXT,"
                       " confidentiality_level TEXT, project_id TEXT, verified_by_owner BOOLEAN,"
                       " source_system TEXT, created_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE revenue_snapshots(id TEXT, period_type TEXT, period_key TEXT,"
                       " entity_type TEXT, entity_id TEXT, revenue_amount NUMERIC,"
                       " currency TEXT, synced_at TIMESTAMP)"))
        for r in know:
            c.execute(text("INSERT INTO knowledge_items VALUES(:a,:b,:c,:d,:e,:f,:g,:h)"),
                      dict(zip("abcdefgh", r)))
        for r in rev:
            c.execute(text("INSERT INTO revenue_snapshots VALUES(:a,:b,:c,:d,:e,:f,:g,:h)"),
                      dict(zip("abcdefgh", r)))
    eng.dispose()
    return url


def K(i, content="事实", layer="company_reference", level="L2", pid="p-test",
      ok=True, src="manual", at=datetime(2026, 8, 30, 10, 0)):
    return (f"k{i}", content, layer, level, pid, ok, src, at)


def R(i, gid="g-1", amount="100.5", cur="CNY", at=datetime(2026, 8, 30, 6, 0),
      ptype="monthly", pkey="2026-08", etype="group"):
    return (f"r{i}", ptype, pkey, etype, gid, amount, cur, at)


def client(tmp_path, know=(), rev=(), cfg=CFG):
    src = SqlAlchemySource(make_db(tmp_path, know, rev))
    return TestClient(create_app(cfg, src))


# ── 关闭态 / 鉴权 ──

def test_unconfigured_all_503(tmp_path):
    c = TestClient(create_app(None, None))
    for p in ("/v1/health", "/v1/scopes", "/v1/context?scope_id=x&period=2026-08"):
        assert c.get(p, headers=AUTH).status_code == 503


def test_bad_or_missing_token_401(tmp_path):
    c = client(tmp_path)
    assert c.get("/v1/health").status_code == 401
    assert c.get("/v1/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = c.get("/v1/health", headers=AUTH)
    assert r.status_code == 200 and r.json()["schema_version"] == "huohuo-readonly-v1"
    assert r.headers["Cache-Control"] == "no-store"
    assert "database" not in r.text.lower()  # 不返回 DSN


def test_short_token_config_rejected(monkeypatch):
    monkeypatch.setenv("HUOHUO_EXPORT_TOKEN", "short")
    monkeypatch.setenv("HUOHUO_EXPORT_SCOPES_JSON", '{"s":{"project_id":"p"}}')
    assert BridgeConfig.from_env() is None  # 短 token 即关闭


# ── scope / period ──

def test_unknown_scope_403_and_bad_period_400(tmp_path):
    c = client(tmp_path)
    assert c.get("/v1/context?scope_id=evil&period=2026-08", headers=AUTH).status_code == 403
    for bad in ("2026-8", "2026-13", "202608", "2026-08-01", ""):
        assert c.get(f"/v1/context?scope_id=synthetic-scope&period={bad}",
                     headers=AUTH).status_code == 400


# ── 知识白名单 ──

def test_knowledge_filters(tmp_path):
    know = [
        K(1, "正常事实"),
        K(2, "五级机密", level="L5"),            # L5 不出库
        K(3, "未知等级", level="LX"),            # 未知等级不出库
        K(4, "越项目", pid="p-other"),           # 跨项目不出库
        K(5, "未确认", ok=False),                # 未确认不出库
        K(6, "自循环", src="Sanjian-Consult"),   # 来源自循环不出库(大小写无关)
        K(7, "私有层", layer="private_decision"),  # 层不合规不出库
    ]
    c = client(tmp_path, know=know)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    texts = [i["text"] for i in j["items"] if i["kind"] == "knowledge"]
    assert texts == ["正常事实"]
    it = [i for i in j["items"] if i["kind"] == "knowledge"][0]
    assert it["id"] == "knowledge:k1" and it["scope_id"] == "synthetic-scope"
    assert it["known_at"].endswith("Z")          # naive 按 UTC 规范化
    assert it["verification"] == "source_marked_verified"


def test_knowledge_truncation_flag(tmp_path):
    know = [K(i, f"事实{i}", at=datetime(2026, 8, 1, 0, 0, i)) for i in range(25)]
    c = client(tmp_path, know=know)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    ks = [i for i in j["items"] if i["kind"] == "knowledge"]
    assert len(ks) == 20 and j["coverage"]["knowledge_truncated"] is True


# ── 流水 ──

def test_revenue_happy_multicurrency(tmp_path):
    rev = [R(1, "g-1", "100.50", "CNY"),
           R(2, "g-2", "0.25", "CNY", at=datetime(2026, 8, 29, 5, 0))]
    c = client(tmp_path, rev=rev)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    rs = {i["metrics"]["currency"]: i for i in j["items"] if i["kind"] == "revenue"}
    assert j["coverage"]["revenue_complete"] is True
    assert rs["CNY"]["metrics"]["amount"] == "100.75"          # Decimal 精确合计
    assert rs["CNY"]["known_at"] == "2026-08-29T05:00:00Z"     # 最早同步时间
    assert rs["CNY"]["level"] == "L4" and "非个人收入" in rs["CNY"]["text"]


def test_revenue_currency_mapping_yinlang(tmp_path):
    """币种映射(2026-08-31 本人批准):音浪→YINLANG,金额不换算,原始标签留档,注记入 text。"""
    c = client(tmp_path, rev=[R(1, "g-1", "1000", "音浪"), R(2, "g-2", "500", "音浪")])
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert j["coverage"]["revenue_complete"] is True
    r = [i for i in j["items"] if i["kind"] == "revenue"][0]
    assert r["metrics"]["currency"] == "YINLANG"
    assert r["metrics"]["amount"] == "1500"                    # 只映射标签,金额一律不换算
    assert r["metrics"]["original_currency"] == "音浪"
    assert "10音浪≈1人民币" in r["text"] and "金额未换算" in r["text"]
    assert len(r["text"]) <= 1200


def test_revenue_currency_whitelist(tmp_path):
    # R1-2:映射表外的币种仅明确 ASCII 标识;名称型/小写/中文一律该组缺失,不猜
    for badcur in ("cny", "人民币", "快币", "AB", "X" * 17):
        c = client(tmp_path, rev=[R(1, "g-1", "9", badcur), R(2, "g-2", "1", "CNY")])
        j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
        assert j["coverage"]["revenue_complete"] is False, badcur
        assert [i for i in j["items"] if i["kind"] == "revenue"] == []
    c = client(tmp_path, rev=[R(1, "g-1", "9", "DIAMOND"), R(2, "g-2", "1", "DIAMOND")])
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert j["coverage"]["revenue_complete"] is True


def test_revenue_latest_row_wins(tmp_path):
    rev = [R(1, "g-1", "1", "CNY", at=datetime(2026, 8, 1)),
           R(2, "g-1", "9", "CNY", at=datetime(2026, 8, 30)),
           R(3, "g-2", "5", "CNY", at=datetime(2026, 8, 15))]
    c = client(tmp_path, rev=rev)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    r = [i for i in j["items"] if i["kind"] == "revenue"][0]
    assert r["metrics"]["amount"] == "14"                      # 9+5,旧行不入

def test_revenue_incomplete_no_partial_sum(tmp_path):
    c = client(tmp_path, rev=[R(1, "g-1", "9", "CNY")])        # g-2 整月无行 → 缺失
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert [i for i in j["items"] if i["kind"] == "revenue"] == []
    assert j["coverage"]["revenue_complete"] is False
    assert j["coverage"]["revenue_missing_groups"] == 1


@pytest.mark.parametrize("rows,miss", [
    ([R(1, "g-1", "9", "CNY", at=datetime(2026, 8, 30)),        # 同组同刻冲突
      R(2, "g-1", "8", "CNY", at=datetime(2026, 8, 30)),
      R(3, "g-2", "1", "CNY")], 1),
    ([R(1, "g-1", "NaN", "CNY"), R(2, "g-2", "1", "CNY")], 1),  # 非有限金额
    ([R(1, "g-1", "9", ""), R(2, "g-2", "1", "CNY")], 1),       # 空币种
    ([R(1, "g-1", "9", "CNY", at=None), R(2, "g-2", "1", "CNY")], 1),  # 无有效时间
])
def test_revenue_broken_rows_mean_missing(tmp_path, rows, miss):
    c = client(tmp_path, rev=rows)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert [i for i in j["items"] if i["kind"] == "revenue"] == []
    assert j["coverage"]["revenue_complete"] is False
    assert j["coverage"]["revenue_missing_groups"] == miss


def test_revenue_scope_and_type_isolation(tmp_path):
    rev = [R(1, "g-1", "9", "CNY"), R(2, "g-2", "1", "CNY"),
           R(3, "g-evil", "999", "CNY"),                        # 未授权组,不得影响
           R(4, "g-1", "50", "CNY", ptype="daily"),             # 日表不得合计
           R(5, "g-1", "70", "CNY", pkey="2026-07"),            # 他月不得混入
           R(6, "g-1", "80", "CNY", etype="anchor")]            # 非 group 不得入
    c = client(tmp_path, rev=rev)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    r = [i for i in j["items"] if i["kind"] == "revenue"][0]
    assert r["metrics"]["amount"] == "10" and j["coverage"]["revenue_complete"] is True


def test_empty_group_ids_complete_and_empty(tmp_path):
    cfg = BridgeConfig(token=TOKEN, scopes={"synthetic-scope": ScopeCfg("空", "p-test", ())})
    c = client(tmp_path, rev=[R(1, "g-1", "9", "CNY")], cfg=cfg)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert [i for i in j["items"] if i["kind"] == "revenue"] == []
    assert j["coverage"]["revenue_complete"] is True
    assert j["coverage"]["revenue_missing_groups"] == 0


# ── 数据库异常与只读 ──

def test_db_error_503_no_sensitive_echo(tmp_path):
    class Boom:
        def knowledge(self, *_a, **_k):
            raise RuntimeError("postgresql://user:pass@host/db SELECT boom")
        def revenue_monthly(self, *_a, **_k):
            return []
    c = TestClient(create_app(CFG, Boom()))
    r = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH)
    assert r.status_code == 503
    assert "postgresql" not in r.text and "SELECT" not in r.text  # 不回显 DSN/SQL


def test_source_is_truly_readonly(tmp_path):
    url = make_db(tmp_path, know=[K(1)])
    src = SqlAlchemySource(url)
    with pytest.raises(Exception):
        with src._conn() as conn:  # noqa: SLF001  只读事务验证
            conn.exec_driver_sql("INSERT INTO knowledge_items VALUES"
                                 "('x','x','company_reference','L2','p-test',1,'m',NULL)")
    assert src.knowledge("p-test", 5)  # 读仍正常


class FakeSource:
    """注入源:绕过 SQL 层,专测服务层兜底。"""

    def __init__(self, know=(), rev=()):
        self._k, self._r = list(know), list(rev)

    def knowledge(self, project_id, limit):
        return self._k

    def revenue_monthly(self, period_key, group_ids):
        return self._r


def test_r1_first21_excluded_does_not_mask_legit(tmp_path):
    """R1-1:最新 21 条全是 L5/自循环时,更旧的合法条目仍须出库且不误报截断。"""
    know = ([K(i, f"密{i}", level="L5", at=datetime(2026, 8, 30, 12, 0, i)) for i in range(11)]
            + [K(100 + i, f"环{i}", src="sanjian-loop", at=datetime(2026, 8, 30, 11, 0, i))
               for i in range(10)]
            + [K(200, "合法旧事实", at=datetime(2026, 8, 1))])
    c = client(tmp_path, know=know)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    ks = [i for i in j["items"] if i["kind"] == "knowledge"]
    assert [i["text"] for i in ks] == ["合法旧事实"]
    assert j["coverage"]["knowledge_truncated"] is False


def test_r1_config_strictness():
    from integrations.huohuo_bridge.config import ScopeCfg as SC, validate
    ok = {"label": "合", "project_id": "p", "group_ids": ["g1"]}
    assert validate(TOKEN, {"s1": ok}) is not None
    assert validate("short", {"s1": ok}) is None                        # 短 token
    assert validate(TOKEN, {"s1": {**ok, "group_ids": "g1"}}) is None   # 字符串误当列表
    assert validate(TOKEN, {"s1": {**ok, "project_id": None}}) is None  # None 不得 str 化
    assert validate(TOKEN, {"s1": {**ok, "project_id": 123}}) is None   # 非字符串
    assert validate(TOKEN, {"s1": {**ok, "group_ids": ["g", "g"]}}) is None  # 重复组
    assert validate(TOKEN, {"s1": {**ok, "group_ids": ["g", ""]}}) is None   # 空组
    assert validate(TOKEN, {"恶意 id": ok}) is None                     # scope id 非法字符
    assert validate(TOKEN, {"x" * 161: ok}) is None                     # scope id 超长
    assert validate(TOKEN, {"s1": {**ok, "label": ""}}) is None         # label 空
    assert validate(TOKEN, {"s1": {**ok, "group_ids": [f"g{i}" for i in range(101)]}}) is None
    # 直接注入 create_app 的不合规配置同样关闭
    bad = BridgeConfig(token="short", scopes={"s": SC("l", "p", ())})
    c = TestClient(create_app(bad, FakeSource()))
    assert c.get("/v1/health", headers={"Authorization": "Bearer short"}).status_code == 503


def test_r1_old_duplicates_do_not_poison_latest(tmp_path):
    rev = [R(1, "g-1", "1", "CNY", at=datetime(2026, 8, 1)),
           R(2, "g-1", "1", "CNY", at=datetime(2026, 8, 1)),   # 旧时刻重复,不应误伤
           R(3, "g-1", "9", "CNY", at=datetime(2026, 8, 30)),
           R(4, "g-2", "1", "CNY")]
    c = client(tmp_path, rev=rev)
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    r = [i for i in j["items"] if i["kind"] == "revenue"][0]
    assert j["coverage"]["revenue_complete"] is True and r["metrics"]["amount"] == "10"


def test_r1_service_recheck_and_mixed_tz():
    rev = [RevenueRow("r1", "daily", "2026-08", "group", "g-1", "9", "CNY",
                      datetime(2026, 8, 30)),                      # 日表混入:服务层复核剔除
          RevenueRow("r2", "monthly", "2026-07", "group", "g-1", "9", "CNY",
                     datetime(2026, 8, 30)),                       # 他月混入
          RevenueRow("r3", "monthly", "2026-08", "anchor", "g-1", "9", "CNY",
                     datetime(2026, 8, 30)),                       # 非 group
          RevenueRow("r4", "monthly", "2026-08", "group", "g-1", "5", "CNY",
                     datetime(2026, 8, 20)),                       # naive
          RevenueRow("r5", "monthly", "2026-08", "group", "g-1", "7", "CNY",
                     datetime(2026, 8, 21, tzinfo=timezone.utc)),  # aware,更新
          RevenueRow("r6", "monthly", "2026-08", "group", "g-2", "1", "CNY",
                     datetime(2026, 8, 21))]
    c = TestClient(create_app(CFG, FakeSource(rev=rev)))
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    r = [i for i in j["items"] if i["kind"] == "revenue"][0]
    assert r["metrics"]["amount"] == "8"                           # aware 7 胜 naive 5,+g-2 1


def test_r1_over_limit_rejected_whole_month():
    rows = [RevenueRow(f"r{i}", "monthly", "2026-08", "group", "g-1", "1", "CNY",
                       datetime(2026, 8, 1, 0, 0, 0)) for i in range(1001)]
    c = TestClient(create_app(CFG, FakeSource(rev=rows)))
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert j["coverage"]["revenue_complete"] is False
    assert j["coverage"]["revenue_missing_groups"] == 2
    assert [i for i in j["items"] if i["kind"] == "revenue"] == []


def test_r1_incomplete_knowledge_rows_dropped():
    know = [KnowledgeRow("k1", "  ", "company_reference", "L2", "p-test", True, "manual",
                         datetime(2026, 8, 1)),                    # 空文本
            KnowledgeRow("k2", "有文本", "company_reference", "L2", "p-test", True, "",
                         datetime(2026, 8, 1)),                    # 空来源
            KnowledgeRow("k3", "有文本", "company_reference", "L2", "p-test", True, "manual",
                         None),                                    # 无效时间
            KnowledgeRow("k4", "合法", "company_reference", "L2", "p-test", True, "manual",
                         datetime(2026, 8, 1))]
    c = TestClient(create_app(CFG, FakeSource(know=know)))
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert [i["text"] for i in j["items"] if i["kind"] == "knowledge"] == ["合法"]


def test_r1_no_store_on_404_405(tmp_path):
    c = client(tmp_path)
    r404 = c.get("/no-such", headers=AUTH)
    r405 = c.post("/v1/context", headers=AUTH)
    assert r404.headers["Cache-Control"] == "no-store"
    assert r405.status_code == 405 and r405.headers["Cache-Control"] == "no-store"


def test_r2_injected_scopecfg_str_groupids_closed():
    """R2-1:直接注入 ScopeCfg.group_ids 为字符串(可迭代成单字符)必须关闭而非洗白。"""
    bad = BridgeConfig(token=TOKEN, scopes={"s": ScopeCfg("l", "p", "g-1")})  # type: ignore[arg-type]
    c = TestClient(create_app(bad, FakeSource()))
    assert c.get("/v1/health", headers=AUTH).status_code == 503
    weird = BridgeConfig(token=TOKEN, scopes=[("s", 1)])  # type: ignore[arg-type]
    assert TestClient(create_app(weird, FakeSource())).get(
        "/v1/health", headers=AUTH).status_code == 503  # 类型错误不抛异常,按关闭


def test_r2_token_ascii_and_newline_tricks(tmp_path):
    from integrations.huohuo_bridge.config import validate
    ok = {"label": "合", "project_id": "p", "group_ids": []}
    assert validate("秘" * 32, {"s": ok}) is None            # 非 ASCII token 拒载
    assert validate(TOKEN + "\n", {"s": ok}) is None          # 末尾换行拒载
    c = client(tmp_path)
    r = c.get("/v1/context", headers=AUTH,
              params={"scope_id": "synthetic-scope", "period": "2026-08\n"})
    assert r.status_code == 400                               # fullmatch 拒末尾换行
    # (非 ASCII token 的线上路径:测试客户端无法发非 ASCII 头;服务端以 bytes 比较,
    #  配置侧非 ASCII 已由上面 validate 用例覆盖)


def test_r2_decimal_extremes_missing():
    def rows(amount):
        return [RevenueRow("r1", "monthly", "2026-08", "group", "g-1", amount, "CNY",
                           datetime(2026, 8, 1)),
                RevenueRow("r2", "monthly", "2026-08", "group", "g-2", "1", "CNY",
                           datetime(2026, 8, 1))]
    for bad in ("1E1000000", "9" * 65, "1E19", "0.1234567", "-2E18"):
        c = TestClient(create_app(CFG, FakeSource(rev=rows(bad))))
        j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
        assert j["coverage"]["revenue_complete"] is False, bad
        assert [i for i in j["items"] if i["kind"] == "revenue"] == [], bad
    c = TestClient(create_app(CFG, FakeSource(rev=rows("999999999999999999"))))  # =1E18-1 合法
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert j["coverage"]["revenue_complete"] is True


def test_r2_knowledge_id_and_source_len_rules():
    know = [KnowledgeRow("bad id!", "文本", "company_reference", "L2", "p-test", True, "manual",
                         datetime(2026, 8, 1)),                 # id 含空格/!
            KnowledgeRow("x" * 150, "文本", "company_reference", "L2", "p-test", True, "manual",
                         datetime(2026, 8, 1)),                 # 全串>160
            KnowledgeRow("okid", "文本", "company_reference", "L2", "p-test", True, "s" * 81,
                         datetime(2026, 8, 1)),                 # 来源>80
            KnowledgeRow("okid2", "合法", "company_reference", "L2", "p-test", True, "manual",
                         datetime(2026, 8, 1))]
    c = TestClient(create_app(CFG, FakeSource(know=know)))
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    ids = [i["id"] for i in j["items"] if i["kind"] == "knowledge"]
    assert ids == ["knowledge:okid2"]


def test_r2_bad_dsn_scheme_rejected():
    for dsn in ("mysql://u@h/db", "oracle://u@h/db", "file:///etc/passwd", "", None):
        with pytest.raises(ValueError):
            SqlAlchemySource(dsn)  # type: ignore[arg-type]


def test_all_items_share_scope_id(tmp_path):
    c = client(tmp_path, know=[K(1)], rev=[R(1, "g-1", "9", "CNY"), R(2, "g-2", "1", "CNY")])
    j = c.get("/v1/context?scope_id=synthetic-scope&period=2026-08", headers=AUTH).json()
    assert j["items"] and all(i["scope_id"] == "synthetic-scope" for i in j["items"])
