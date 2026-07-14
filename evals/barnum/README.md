# 巴纳姆自盲实验(evals/barnum/)

检验「三模型会诊报告」是否携带**针对本人命盘的可辨识信息**,还是仅为对任何人都成立的巴纳姆式泛化。
预注册见 [`docs/prereg/barnum-2026-07-14.md`](../../docs/prereg/barnum-2026-07-14.md)(冻结,INV-13)。

## 组成

| 文件 | 作用 |
| --- | --- |
| `barnum-statements.jsonl` | 预注册巴纳姆语句库(Forer 经典陈述),供 `barnum_rate` 词面代理 |
| `anchors.py` | 命盘实体词表 + claim 分类器(specificity / falsifiable / barnum) |
| `build_packet.py` | 构建盲测 packet:真报告 + 匹配干扰盘 → `packet.json` / `packet.key.json` / `experiment.html` |
| `score_packet.py` | 揭盲评分:读作答 + 私有 key,精确二项检验对随机水平 |

自动代理指标(巴纳姆率 / 具体性率 / 可证伪率)已并入 `evals/metrics.py::compute`,随四臂评测一并输出。
**这些是词面代理,仅描述性,不替代人类盲判、不作优化目标(INV-13)。**

## 离线演示(零 API,零密钥)

```bash
make barnum-smoke
# → evals/barnum/out/experiment.html 用浏览器打开即可体验盲测流程
```

## 真实自测(需 .env 密钥;约 k 场会诊,受日熔断约束)

```bash
python3 evals/barnum/build_packet.py --birth 1990-06-15T08:30 --out evals/barnum/out
open evals/barnum/out/experiment.html         # UI 实验模式作答,导出 choices.json
python3 evals/barnum/score_packet.py --choices choices.json --key evals/barnum/out/packet.key.json
```

## 盲法与冻结纪律

- `packet.json` **不含**真伪答案,可安全查看;`experiment.html` 只加载它,打开页面不可能泄漏答案。
- `packet.key.json`(真报告索引 + 洗牌种子 + packet 哈希)**gitignore、本机私有**;严禁先看 key 再作答。
- 顺序不可逆:先作答固定 → 后揭盲评分。
- 预注册开跑前须 `make prereg-freeze` 冻结哈希;CI 用 `check_prereg_lock.py` 校验不漂移。
- 单主体先导统计功效先天不足,主结论只能判「不确定」(预注册 §9);powered 判定须多主体扩展。
