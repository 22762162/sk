# PR#55 交叉审查 · 答非所问闸放宽

审查提交：`9a19a2f`（基线：`origin/main` / `220a30b`）。身份：主仓独立交叉评审。
本次只审查 `backend/app.py` 的 `_app_answer_relevant` 放宽、PR#41 相关测试与十神/生克闸
调用边界；未改实现、未调用模型、未读取 `.env`、真实数据、密钥、私有评测集或参考实现。

## 结论

三级结论为：通过 / 整改 / 阻断。本次结论：**阻断（修复后复审）**。

PR#55 的确修复了一部分跨模型同义措辞误伤，但当前正向启发式仍可让明显未回答原问题的文本
通过。以下四个合成反例在当前分支均为 `True`，而在 PR#41 基线函数中为 `False`；其中主题
闸还可将财务问题放行为合作问题、将工作考核问题放行为学业问题。该风险直接影响“未切题不
保存”的 fail-closed 目标，不能以作者新增的正例测试抵消。

## BLOCKER

### B1 · 新增结论词可把泛泛文本当成任务结论

位置：`backend/app.py:1519-1525,1555-1557`。

```text
问题：本月核心业务目标能否推进到位
回答：项目现场天气晴朗，适合散步喝茶，整体顺利，建议放松。
metrics：{}
当前：True    PR#41 基线：False
```

答案只回显了一个泛化主题词“项目”，并命中新增的“顺利/建议/适合”，没有回答目标能否
推进。将通用行动建议或场景描述单独作为结论证据，会让劣质答案蒙混过闸。建议将结论词与
问题主题/目标动作绑定，或保留更窄的判断短语；至少为每个新增词加入“只含泛泛句应拒绝”
的负例。

### B2 · 指标闸只要求命中一个词，新增“增长”等词可替代真实量化回答

位置：`backend/app.py:1527-1529,1558-1559`。

```text
问题：本月回款能否达到既定水平
回答：财务走势增长有望，建议继续观察。
metrics：{"target": 300, "gap": 120}
当前：True    PR#41 基线：False
```

回答没有目标值、缺口、日均、剩余天数或完成判断，只因“财务”命中主题、“增长”命中新增
指标词、“有望/建议”命中结论词而通过。`“万事顺利”` 这类包含“万”的泛句也可满足同一
个指标条件。指标闸至少应要求回答触及实际计算指标锚点/关系，而不是任一泛量化词。

### B3 · 多主题问题被压平成一个词集合，财务题可被合作答复通过

位置：`backend/app.py:1551-1554`。

```text
问题：本月客户回款能否完成
回答：合作伙伴关系有望缓和，建议继续观察。
metrics：{}
当前：True    PR#41 基线：False
```

问题同时命中“财务”（回款）与“合作”（客户）；实现使用
`any(w in answer for words in hit_groups for w in words)`，答案命中“伙伴”即可，不必
回答回款。这个“任一主题类即可”的语义不能证明主问题已被回答。应明确选出主主题，或在
问题命中多个主题时要求各个必需主题分别有证据；相关负例必须覆盖“客户回款→合作关系”。

### B4 · 单字主题词“考”造成工作考核→学业的跨主题放行

位置：`backend/app.py:1533-1543,1551-1554`。

```text
问题：本月工作考核能否通过
回答：录取结果有望，参考资料充足，准备节奏稳定。
metrics：{}
当前：True    PR#41 基线：False
```

“工作/考核”命中事业类；学业类的单字词“考”又命中“考核”。答案只命中学业类“录取”，
再以“有望”满足结论条件，因而通过，实际完全没有回答工作考核。主题词需使用短语/边界化
匹配并处理高碰撞单字，不能把单字子串当作稳定主题证据。

## 主题闸专项判断

PR#41 原实现本身也对多个逐字主题词使用 `any(...)`，因此“问题同时含两类时只答其中一类”
是既有残余风险；本 PR 的新分组没有将它收紧，且通过新增同义词和“考”子串扩大了命中集合。
因此，B3 是当前设计的直接反例，B4 是本 PR 引入的可复现跨主题回归。PR#55 声称“跨主题
错答仍拦”与上述观测不符。

## 十神 / 生克矛盾闸

未发现本 PR 波及该闸。`origin/main...HEAD` 的代码差异从
`_app_ten_god_text_valid` 结束后的新词表开始；现函数仍位于 `backend/app.py:1489-1516`，
直答校验仍在 `backend/app.py:1609-1610` 以 `and` 组合执行，放宽相关性不会绕过十神/生克
校验。

当前源代码的合成检查结果：

```text
火为财星，土为官杀，金为印星，木为食伤。  -> True
财星土弱。                                  -> False
癸水克甲木。                                -> False
```

这只证明既有文本硬闸仍工作，不证明完整命理正确性。

## 与 PR#41 既有测试的关系

- `backend/tests/test_app_api.py` 在 PR#55 中没有改动；其中
  `:239-249` 的相关性正/负例以及 `:250-254` 的十神/生克例与当前逻辑不冲突。
- 新增 `backend/tests/test_answer_relevance.py` 的 4 组测试也没有与旧断言发生冲突，但其
  负例只覆盖无主题天气、无结论事业句、缺少指标词的财务句和完全不命中主题；没有覆盖
  B1-B4 这种“回显一个词 + 泛泛结论/指标词”的情况。
- `git diff --check` 通过。完整 pytest 未能在本审查环境执行：默认 Python 缺少 FastAPI；
  `uv run --offline --with-requirements backend/tests/requirements.lock ...` 又因锁定包
  `annotated-doc` 不在离线缓存而无法解析。上述反例使用标准库从当前源代码提取并执行目标
  常量/函数，未调用任何模型或外部服务。

## 合成反例探针（建议加入修复后的回归集）

以下每项按安全闸预期都应为 `False`；当前分支观测均为 `True`：

```python
PROBES = [
    (
        "本月核心业务目标能否推进到位",
        "项目现场天气晴朗，适合散步喝茶，整体顺利，建议放松。",
        {},
    ),
    (
        "本月回款能否达到既定水平",
        "财务走势增长有望，建议继续观察。",
        {"target": 300, "gap": 120},
    ),
    (
        "本月客户回款能否完成",
        "合作伙伴关系有望缓和，建议继续观察。",
        {},
    ),
    (
        "本月工作考核能否通过",
        "录取结果有望，参考资料充足，准备节奏稳定。",
        {},
    ),
]
for question, answer, metrics in PROBES:
    assert _app_answer_relevant(answer, question, metrics) is False
```

## 修复后验收建议

1. 对结论词、指标词分别加入通用泛句负例；结论必须和目标动作/主题形成同一证据，而非
   只命中“建议、适合、顺利”等词。
2. 指标题要求回答触及确定性指标（目标、缺口、日均、剩余天数、完成率等）及其判断关系；
   对“增长、百分、万、冲刺”等词单独出现的情况 fail closed。
3. 主题识别改用明确的主主题/多主题要求，并为“客户回款”“工作考核”等高碰撞问题增加
   跨主题负例；避免单字子串直接建立主题命中。
4. 修复后保留本报告四项负例，重新执行后端完整测试，再由本人完成人工签署；本报告不替代
   人工裁决或上线批准。

## Auditor attestation

```yaml
artifact_id: p55-answer-relevance-codex-reviewer-9a19a2f
timestamp: "2026-09-01"
timestamp_source: session_date
provider: openai
model_id: Codex (exact runtime model id unavailable)
model_release: Codex session 2026-09-01
agent_role: reviewer
session_id: codex-main-repo-session(pr55-answer-relevance-review)
run_manifest_id: not-applicable (offline synthetic source probe only)
source_repository: https://github.com/22762162/sk
source_commit: 9a19a2f
generated_files:
  - docs/reviews/pr55-codex-review.md
  - governance/attestations/p55-answer-relevance-codex-reviewer.yaml
reviewed_files:
  - backend/app.py
  - backend/tests/test_answer_relevance.py
  - backend/tests/test_app_api.py
  - docs/reviews/PR-41-question-relevance-risk.md
  - governance/attestations/p21-answer-relevance-claude-implementer.yaml
verdict: blocked
human_signoff: pending
notes: >-
  独立静态源探针复现四项当前分支放行反例：泛泛结论词、单一指标词、财务题被合作答复、
  工作考核题被学业答复。未调用模型，未读取密钥、真实数据、私有评测或参考实现；未修改
  实现。完整pytest因FastAPI及锁定依赖不在离线环境而未执行。人工签署待定；本attestation
  不构成人工批准、合入批准或上线批准。
```

最终状态：**阻断；修复上述反例并完成独立复审后，方可重新评估合入。**
