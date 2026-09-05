"""切题粗筛验证(P21 v3;产品所有者结论:命理不精准,切题交盲评,本函数只粗筛)。纯合成,零模型调用。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
rel = app._app_answer_relevant

Q_TASK = "本月核心业务目标能否推进到位"
Q_METRIC = "本月回款能否达到既定水平"
M = {"target": 300, "gap": 120}


def test_cross_model_phrasings_pass():
    """跨模型同义结论不再被死板主题字眼误伤(用户遇到的核心问题)。"""
    for ans in [
        "综合看本月推进可以顺利,大概率达成,宜主动出击。",
        "目标达成难以一蹴而就,取决于配合,可能延后。",
        "利于推进,概率偏高,有望在中旬落地。",
        "回款完成率约七成,尚有缺口,按日均可以达成。",   # 经营题:方向或锚点任一即可
    ]:
        assert rel(ans, Q_TASK if "回款" not in ans else Q_METRIC, {} if "回款" not in ans else M) is True, ans


def test_empty_or_hollow_still_rejected():
    assert rel("目标相关。", Q_TASK, {}) is False                          # 过短
    assert rel("今天天气不错,心情愉快,适合散步喝茶放松。", Q_TASK, {}) is False  # 决策题无任何方向/锚点
    assert rel("财务走势有些波动,继续观察一下情况变化。", Q_METRIC, M) is False  # 经营题无方向无锚点


def test_no_longer_deadlocks_on_topic_wording():
    """不再因'回答没复述问题里的某个字'而拦(去主题硬匹配)——切题交盲评。"""
    # 问业务目标,答用"事业/推进"等不同措辞,有方向词 → 粗筛放行(是否切题由盲评判)
    assert rel("事业层面可以推进,大概率达成。", Q_TASK, {}) is True


def test_decision_needs_direction_or_anchor():
    # 决策题给了方向词 → 过;既无方向也无锚点 → 拦
    assert rel("这件事有望成事,机会较大。", Q_TASK, {}) is True
    assert rel("情况比较复杂,涉及多方面因素,需要综合考量各种情形。", Q_TASK, {}) is False
