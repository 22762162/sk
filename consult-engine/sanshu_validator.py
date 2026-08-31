"""三术分段输出校验器(RFC-0004 §2-§4;fail-closed;banlists: sanshu-banlists-v1)。

词表原则:只禁**对方法独有**的词汇——干支本身是共享输入(卦的月建日辰/爻支),不禁;
"用神"两法皆用,不禁(见 RFC §3)。词表只作第二道防线,物理隔离在编排层。
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

import liuyao as _liuyao

SCHEMA_VERSION = "sanshu-sealed-v1"
BANLISTS_VERSION = "sanshu-banlists-v1"
_CONF = ("low", "medium", "high")
_CONF_RANK = {c: i for i, c in enumerate(_CONF)}
_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_DATE_RE = re.compile(_DATE)
_COMPARATORS = (">=", "<=", "==", "发生", "未发生")

# gua 段禁出现的八字独有词
BAZI_ONLY_TERMS = tuple(
    ["大运", "流年", "流月", "日主", "四柱", "年柱", "月柱", "日柱", "时柱",
     "十神", "纳音", "喜用神", "忌神", "身强", "身弱", "格局用神"]
    + ["正官", "七杀", "偏官", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "正印", "偏印", "枭神"])
# bazi 段禁出现的卦独有词(64 卦全名程序生成)
GUA_ONLY_TERMS = tuple(
    ["卦", "爻", "世应", "世爻", "应爻", "动爻", "变卦", "互卦", "本卦", "体用", "卦宫",
     "纳甲", "六神", "青龙", "朱雀", "勾陈", "腾蛇", "螣蛇", "玄武", "六爻", "梅花易", "起卦"]
    + sorted(_liuyao.PALACES.keys()))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE)
    return s.lower()


def _all_strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_all_strings(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_all_strings(v))
    return out


def scan_banned(section_obj, banned: tuple[str, ...]) -> list[str]:
    blob = _norm("".join(_all_strings(section_obj)))
    return [t for t in banned if _norm(t) in blob]


def _err(errors: list[str], cond: bool, msg: str) -> None:
    if cond:
        errors.append(msg)


def _real_date(s) -> bool:
    """真历法日期(探针修复:2026-99-99 之类正则可过但历法不存在)。"""
    if not isinstance(s, str) or not re.fullmatch(_DATE, s):
        return False
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _check_window(w, errors: list[str], where: str) -> None:
    if not isinstance(w, dict) or set(w) != {"start", "end"}:
        errors.append(f"{where}.window 须为 {{start,end}}")
        return
    for k in ("start", "end"):
        if not _real_date(w.get(k)):
            errors.append(f"{where}.window.{k} 须为真实历法日期 YYYY-MM-DD")
            return
    _err(errors, w["start"] > w["end"], f"{where}.window start 晚于 end")


def _check_events(evs, errors: list[str], where: str) -> None:
    if not isinstance(evs, list) or len(evs) > 3:
        errors.append(f"{where}.verifiable_events 须为 0-3 条数组")
        return
    for i, e in enumerate(evs):
        w = f"{where}.verifiable_events[{i}]"
        if not isinstance(e, dict) or set(e) - {"statement", "window", "metric", "adjudication"}:
            errors.append(f"{w} 含未定义字段或类型错误")
            continue
        _err(errors, not isinstance(e.get("statement"), str) or not 8 <= len(e["statement"]) <= 300,
             f"{w}.statement 须为 8-300 字")
        _check_window(e.get("window"), errors, w)
        m = e.get("metric")
        if not isinstance(m, dict) or set(m) - {"indicator", "comparator", "threshold", "unit"}:
            errors.append(f"{w}.metric 结构不合规")
        else:
            _err(errors, not isinstance(m.get("indicator"), str) or not 2 <= len(m["indicator"]) <= 120,
                 f"{w}.metric.indicator 须为 2-120 字")
            _err(errors, m.get("comparator") not in _COMPARATORS,
                 f"{w}.metric.comparator 须为 {_COMPARATORS}")
            th = m.get("threshold")
            cmp_ = m.get("comparator")
            bad_num = isinstance(th, bool) or not isinstance(th, (int, float)) \
                or (isinstance(th, float) and not math.isfinite(th))
            if cmp_ in (">=", "<=", "=="):
                # 交接保留项:数值比较符必须配有限数值阈值,缺 threshold 不得通过
                _err(errors, th is None or bad_num,
                     f"{w}.metric:comparator {cmp_} 必须配有限数值 threshold")
            elif cmp_ in ("发生", "未发生"):
                _err(errors, th is not None, f"{w}.metric:事件型 comparator 不得携带 threshold")
            _err(errors, th is not None and bad_num, f"{w}.metric.threshold 须为有限数值或 null")
            _err(errors, m.get("unit") is not None and not isinstance(m["unit"], str),
                 f"{w}.metric.unit 须为字符串或 null")
        _err(errors, not isinstance(e.get("adjudication"), str) or not 8 <= len(e["adjudication"]) <= 300,
             f"{w}.adjudication 须为 8-300 字")


def _check_yingqi(y, errors: list[str], where: str) -> None:
    if isinstance(y, dict) and set(y) == {"abstain_reason"}:
        _err(errors, not isinstance(y["abstain_reason"], str) or not 4 <= len(y["abstain_reason"]) <= 300,
             f"{where}.yingqi.abstain_reason 须为 4-300 字")
        return
    if isinstance(y, dict) and set(y) == {"start", "end"}:
        _check_window(y, errors, f"{where}.yingqi")
        return
    errors.append(f"{where}.yingqi 须为 {{start,end}} 或 {{abstain_reason}}")


def _check_common(sec, errors: list[str], where: str, extra_allowed: set[str],
                  meta_fields: set[str] = frozenset(), require_reading: bool = True) -> None:
    """meta_fields:编排器回显的元数据层(如 gua 的 method/cast_hash)——
    abstain 时仍须携带(交接保留项:元数据分层,弃答白名单不拒元数据)。
    require_reading=False 用于 combined(其正文字段为 answer/reasoning)。"""
    allowed = {"status", "reason", "confidence", "yingqi",
               "verifiable_events", "method_basis"} | extra_allowed | meta_fields
    if require_reading:
        allowed.add("reading")
    if not isinstance(sec, dict):
        errors.append(f"{where} 须为对象")
        return
    _err(errors, bool(set(sec) - allowed), f"{where} 含未定义字段:{sorted(set(sec) - allowed)}")
    st = sec.get("status")
    if st == "abstain":
        _err(errors, not isinstance(sec.get("reason"), str) or not 4 <= len(sec["reason"]) <= 300,
             f"{where}.reason(abstain)须为 4-300 字")
        # 合法弃答不夹带结论:判断字段一律拒;元数据字段(meta_fields)必须保留
        stray = sorted(set(sec) - {"status", "reason"} - meta_fields)
        _err(errors, bool(stray), f"{where} abstain 时不得携带判断字段:{stray}")
        return
    if st != "ok":
        errors.append(f"{where}.status 须为 ok|abstain")
        return
    if require_reading:
        _err(errors, not isinstance(sec.get("reading"), str) or not 20 <= len(sec["reading"]) <= 1200,
             f"{where}.reading 须为 20-1200 字")
    conf = sec.get("confidence")
    _err(errors, not isinstance(conf, str) or conf not in _CONF,  # 探针修复:[] 等不可哈希值不抛异常
         f"{where}.confidence 须为 low|medium|high")
    _check_yingqi(sec.get("yingqi"), errors, where)
    _check_events(sec.get("verifiable_events", []), errors, where)
    _err(errors, not isinstance(sec.get("method_basis"), str) or not 4 <= len(sec["method_basis"]) <= 400,
         f"{where}.method_basis 须为 4-400 字")


def validate_bazi(sec) -> list[str]:
    errors: list[str] = []
    _check_common(sec, errors, "bazi", set())
    hits = scan_banned(sec, GUA_ONLY_TERMS)
    _err(errors, bool(hits), f"bazi 段含卦象独有词(跨段借证):{hits[:5]}")
    return errors


def validate_gua(sec, expect_method: str, expect_cast_hash: str) -> list[str]:
    errors: list[str] = []
    _check_common(sec, errors, "gua", set(), meta_fields={"method", "cast_hash"})
    _err(errors, sec.get("method") != expect_method if isinstance(sec, dict) else True,
         "gua.method 须回显编排器注入值")
    _err(errors, sec.get("cast_hash") != expect_cast_hash if isinstance(sec, dict) else True,
         "gua.cast_hash 须回显装卦哈希(B5 绑定)")
    hits = scan_banned({k: v for k, v in sec.items() if k not in ("method", "cast_hash")}
                       if isinstance(sec, dict) else sec, BAZI_ONLY_TERMS)
    _err(errors, bool(hits), f"gua 段含八字独有词(跨段借证):{hits[:5]}")
    return errors


def validate_combined(sec, bazi_conf: str, gua_conf: str) -> list[str]:
    errors: list[str] = []
    _check_common(sec, errors, "combined", {"answer", "reasoning", "dissent_note"},
                  require_reading=False)
    if isinstance(sec, dict) and sec.get("status") == "ok":
        _err(errors, not isinstance(sec.get("answer"), str) or not 10 <= len(sec["answer"]) <= 600,
             "combined.answer 须为 10-600 字")
        _err(errors, not isinstance(sec.get("reasoning"), str) or not 20 <= len(sec["reasoning"]) <= 1200,
             "combined.reasoning 须为 20-1200 字")
        _err(errors, "dissent_note" in sec and not isinstance(sec["dissent_note"], str),
             "combined.dissent_note 须为字符串")
        cap = max(_CONF_RANK.get(bazi_conf, 0), _CONF_RANK.get(gua_conf, 0))
        conf = sec.get("confidence")
        rank = _CONF_RANK[conf] if isinstance(conf, str) and conf in _CONF_RANK else 99
        _err(errors, rank > cap, "combined.confidence 不得高于两个单法中的较高者")
    return errors
