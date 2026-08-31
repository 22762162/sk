# PR-45 候选工程加固 · Claude 侧状态

工作树:`~/Projects/sk-divination-hardening`,分支 `agent/divination-hardening`(起点 feat/p15-liuyao-meihua @5002b6b)。
按约定:**未提交、未推送、未合并、未部署**;未读独立参考源码/私有评测/真实数据/密钥;未新增运行态 prompts。

## 完成清单(对应预检 1/2/4 条)

1. **随机性迁出确定性模块(预检 1)**:新增 `consult-engine/divination_casting.py` 适配层
   (system_cast_liuyao/manual_cast_liuyao,带 method 来源标记);`liuyao.py` 删除 `import secrets`
   与 `system_cast`,现为零随机零时钟;测试断言引擎源码不含 secrets/random 且旧符号已移除。
2. **输入显式校验(预检 2)**:六爻——爻值须严格 int(显式拒 bool/浮点/字符串同值异类)、恰 6 爻、
   值域 {6,7,8,9};`day_ganzhi` ∈ 六十甲子全集(frozenset 生成,甲丑等非法配对被拒);
   `month_branch` ∈ 十二地支。梅花——n1/n2 严格正整数(拒 bool/浮点),时辰支白名单+类型检查;
   报数范围上限按预检留给 App 适配层。全部走受控 ValueError,无未受控异常。
3. **测试补全(预检 4)**:`consult-engine/divination_hardening_test.py`——
   4096 组爻值穷举(结构不变量逐组断言+64 本卦全现身)、六十甲子日全覆盖(六神起法/旬空逐日)、
   同输入重放字节级一致、六爻 13 组+梅花 11 组非法输入矩阵、适配层→引擎直通、
   梅花全时辰×8×8 轻量穷举。脚本态与 pytest 态双跑。
4. **预检 3 的最小处理(超出三条清单,已标注可剔除)**:梅花输出加 `relation_code`(确定性生克事实码)
   与 `relation_kind: traditional_school_reading` 标注;原 `relation` 判词一字未改,术数表未动。
   如你认为超范围,剔除这两个字段即可,测试相应两行同删。
5. 规格文档同步两行(适配层边界+校验域说明);未改其余规格内容。

## 验证记录(2026-08-31 22:51 +0700,主机真实时钟)

- `divination_selftest.py`:通过(含新适配层断言)
- `divination_hardening_test.py`:通过
- pytest 双态:12 passed
- `make golden-smoke`:**102 例全部一致**(黄金集含期望值比对 102;双实现对拍 92)——
  措辞更正(采纳 Codex 意见):本次改动**不改既有 Rust 排盘**,但六爻/梅花是**新的候选计算入口,
  仍按高风险处理**;golden-102 只覆盖既有排盘,**不覆盖新算法的独立正确性**(独立对拍与本人签署仍是保留闸门)

## 未解决/移交项

- 预检 5(三术提示词治理链)不在本任务范围,未动。
- 梅花时间起卦(农历朔日表)维持 P3 决策项,未实现。
- attestation:`governance/attestations/divination-hardening-claude-implementer.yaml`
  (真实主机时间;人工签署仍待定)。

## 收尾与冻结（2026-08-31 22:55 +0700）

- 已按你的收尾单完成:①spec 补 relation_code 五枚举+relation_kind 说明(明确为传统规则计算/解释,
  非事件事实);②状态与 attestation 的"不触 L1"措辞已更正为"不改既有 Rust 排盘,候选计算入口按高风险",
  并注明 golden-102 不覆盖新算法独立正确性;③你的 CI job/审查脚本/审查报告只读核验通过——
  我独立复跑等价脚本:六爻 245,760 组+梅花 27,648 组结果与你的报告一致;reviewer attestation 已补
  (`governance/attestations/divination-hardening-claude-reviewer.yaml`,范围仅你三份文件)。
- **本工作树全部文件自此冻结**,后续堆叠 Draft PR(base: feat/p15-liuyao-meihua)由你统一提交;
  不合并不发布,批准权在本人。
