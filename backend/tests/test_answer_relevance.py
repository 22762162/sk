"""答非所问闸门放宽验证(P21):同义结论措辞不再误伤,真跑题仍拦。纯合成,零模型调用。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
rel = app._app_answer_relevant

Q_TASK = "本月核心业务目标能否推进到位"
Q_METRIC = "本月回款能否达到既定水平"
M = {"target": 300, "gap": 120}


def test_synonym_conclusions_no_longer_false_rejected():
    # 这些此前会因只认「能/不能」被误伤,现应通过
    for ans in [
        "从事业与合作看,本月推进可以顺利,机会较大,建议主动出击把握窗口。",
        "综合判断,本月目标达成难以一蹴而就,取决于合作方配合,大概率延后。",
        "工作层面利于推进,概率偏高,宜在中旬前落地关键节点。",
    ]:
        assert rel(ans, Q_TASK, {}) is True, ans


def test_metric_question_synonyms_pass():
    assert rel("回款目标完成率约七成,尚有缺口,按日均推算本月可以达成。", Q_METRIC, M) is True
    assert rel("财务上冲刺目标,差距约百分之三十,需提高增速方能完成。", Q_METRIC, M) is True


def test_genuinely_off_topic_still_rejected():
    assert rel("今天天气不错,心情愉快,适合散步喝茶。", Q_TASK, {}) is False   # 无主题+无结论
    assert rel("事业方面整体平稳,气象温和。", Q_TASK, {}) is False              # 有主题但无任何结论词
    assert rel("目标相关。", Q_TASK, {}) is False                               # 过短
    # 经营题给了结论却完全不触及量化维度 → 仍拦
    assert rel("财务方面可以顺利,机会较大。", Q_METRIC, M) is False


def test_topic_gate_unchanged():
    # 问题含主题词但回答完全不提该主题 → 仍拦(未放宽此闸)
    assert rel("大概率可以完成,概率较高,建议推进。", "感情关系本月能否缓和", {}) is False
