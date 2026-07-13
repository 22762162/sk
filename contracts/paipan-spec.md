# 排盘算法数学规格（paipan-spec）

| | |
| --- | --- |
| 版本 | v0.3（v0.1/v0.2 条款已评审通过并经实现验收；v0.3 新增 4.5 不确定性 op 与第 5 章分级承诺,依 RFC-0001 由本人指示起草） |
| 状态 | v0.1 评审报告：`docs/reviews/paipan-spec-v0.1-review.md`；v0.2 新增条款依据：`docs/research-notes/calendar-facts-sources-2026-07-14.md`（日柱锚点经 KASI+中研院双源证实；五虎遁/五鼠遁经公版古籍与多源核实；早晚子时转流派配置项） |
| 定位 | `engine-paipan`（Rust）与 `engine-paipan-ref`（Python）双实现的**唯一共享契约**。两实现互不可见对方代码，只依据本文档。 |

> 撰写纪律：本文档只给数学定义与判界规则，**不给实现示例代码**（防止双实现同源失效）。凡涉及历法事实（节气时刻、时区规则）之处，一律定义为注入数据，本文档不提供任何具体数值。

---

## 1 通用约定

- **1.1 时间表示**：所有时刻以 Unix 秒（UTC，`i64`/`int`）传递。公历年号使用天文年号（含公元前时 0 = 公元前 1 年；当前范围内不涉及）。
- **1.2 历法事实注入**：节气时刻、时区偏移、夏令时规则等一律由调用方以参数或数据文件注入。实现内**不得出现任何历法常量**。
- **1.3 判界比较**：本规格中所有边界条款必须显式声明开闭区间。默认约定：**恰好等于界点的时刻归入界点之后的区间**（闭下界）。
- **1.4 确定性**：任何函数对相同输入必须返回相同输出；禁止网络、系统时钟、无种子随机。

## 2 干支（六十甲子）编号

- **2.1 天干**：序号 0–9 依次为 甲、乙、丙、丁、戊、己、庚、辛、壬、癸。
- **2.2 地支**：序号 0–11 依次为 子、丑、寅、卯、辰、巳、午、未、申、酉、戌、亥。
- **2.3 干支名**：干支组合的名称为天干名与地支名的直接拼接（如 stem=0, branch=0 →「甲子」）。

## 3 年柱（本版规格的实现范围）

### 3.1 八字年的定义

八字年以**立春**为岁首。定义函数 `resolve_bazi_year`：

- 输入：`civil_year`（时刻 t 所在的公历年号，由调用方按其时区语境解析）、`t_unix`（时刻 t）、`lichun_unix`（`civil_year` 年立春时刻，**注入数据**）。
- 规则（条款 **YP-1**）：`t_unix < lichun_unix` → 八字年 = `civil_year − 1`；`t_unix ≥ lichun_unix` → 八字年 = `civil_year`（恰好等于立春时刻归当年，见 1.3）。
- 前置条件：调用方保证 `lichun_unix` 确为 `civil_year` 年的立春时刻。实现不校验该事实（无从校验），只执行判界。

### 3.2 年柱干支

定义函数 `year_ganzhi`（条款 **YP-2**）：

- 输入：八字年 `Y`（整数）。
- 天干序号 `s = (Y − 4) mod 10`，地支序号 `b = (Y − 4) mod 12`，其中 `mod` 为**欧几里得取模**（结果非负，对 `Y < 4` 亦成立）。
- 锚点（条款 **YP-3**）：`Y = 1984` → 甲子（s=0, b=0）。此锚点为本规格的定义性事实，经人工评审确认。

### 3.3 组合

`year_pillar(civil_year, t_unix, lichun_unix)` = `year_ganzhi(resolve_bazi_year(...))`，返回八字年与干支。

## 4 四柱（v0.2 实现范围：月柱、日柱、时柱与组合 op）

### 4.0 本地民用时刻（条款 **LT-1**）

需要墙上钟时刻的条款使用 `local` 对象 `{y,m,d,hh,mm,ss}`：由调用方按其 IANA 时区语境把时刻 t 解析成当地公历日期时间后注入；引擎不做任何时区换算。前置条件：`local` 与 `t_unix` 指同一时刻（引擎无从校验）。`local` 各字段须构成合法的格里历日期时间（`y ≥ 1`；`hh ∈ [0,24)`；`mm, ss ∈ [0,60)`；`m,d` 为合法历日），非法则该 case 返回 `ok:false`。

### 4.1 月柱

八字月以**十二节**为界（不含中气）。节序号 `jie_seq` 0–11 依次为：立春、惊蛰、清明、立夏、芒种、小暑、立秋、白露、寒露、立冬、大雪、小寒。

- **MP-1（判界与月支）**：调用方注入 `month_ctx = {jie_seq, jie_unix, next_jie_unix}`，含义为「时刻 t 所处节气月：起于 `jie_unix`（该节交节时刻），止于 `next_jie_unix`（下一节交节时刻）」。引擎校验 `jie_unix ≤ t_unix < next_jie_unix`（闭下界，1.3）且 `jie_seq ∈ [0,11]`，不满足则 `ok:false`。月支序 = `(2 + jie_seq) mod 12`（立春起寅月，寅=2）。
- **MP-2（月干，五虎遁）**：`月干序 = ((年干序 mod 5) × 2 + 2 + jie_seq) mod 10`，年干序取 YP-2 之结果（以 YP-1 判定的八字年）。依据：《渊海子平》起月例（考证记录第二节）。
- 前置条件：`month_ctx` 确为权威历源中包含 t 的相邻两节交节时刻，且与 `lichun_unix` 同源一致。实现不校验该历法事实，只执行判界。

### 4.2 日柱

- **DP-1（锚点，定义性事实）**：`JDN 2451545`（格里历 2000-01-01）= **戊午**（六十甲子序 54，甲子=0）。依据：KASI 官方接口与中研院两千年中西历转换双源交叉证实并经 60 日周期验算（考证记录第一节），待人工评审确认。
- **DP-2（JDN 公式，纯数学）**：由 `local` 的 `(y,m,d)` 计算格里历儒略日数，除法一律向下取整：`a=(14−m) div 12; y′=y+4800−a; m′=m+12a−3; JDN = d + (153·m′+2) div 5 + 365·y′ + y′ div 4 − y′ div 100 + y′ div 400 − 32045`。
- **DP-3（日干支）**：`日干支序 n = (54 + (JDN − 2451545)) mod 60`（欧几里得取模）；干序 = `n mod 10`，支序 = `n mod 12`。
- **DP-4（日界，流派配置 `zi_hour_mode ∈ {split, unified}`）**：
  - `split`（早晚子时，**默认**）：日柱按当地 `00:00:00` 换日，直接以 `local` 日期计 JDN；
  - `unified`（子时换日）：`hh ≥ 23` 时该时刻记入**次日**（有效 JDN = JDN+1；恰好 23:00:00 归次日，1.3）。
  属真实流派分歧，转配置项，不裁对错（考证记录第四节）。

### 4.3 时柱

- **HP-1（时支）**：`时支序 = ((hh·3600 + mm·60 + ss + 3600) div 7200) mod 12`。即子时 23:00:00–00:59:59、丑时 01:00:00 起，每两小时一支；恰好整点界归后一支（1.3）。
- **HP-2（时干，五鼠遁）**：`时干序 = ((有效日干序 mod 5) × 2 + 时支序) mod 10`（时支序即 HP-1 结果，子=0）。**有效日干**：`unified` 模式即 DP-4 换日后的日干；`split` 模式下 `hh ≥ 23`（晚子时）用 **JDN+1 日**的日干起遁，其余用当日日干。依据：《渊海子平》起时例（考证记录第三节）。

### 4.4 组合 op `four_pillars`

输入：`{t_unix, lichun_unix, local, month_ctx, zi_hour_mode}`；其中 `civil_year := local.y`（供 YP-1 使用）。输出：`bazi_year` 与四柱 `year/month/day/hour` 各 `{stem, branch, ganzhi}`。任何字段缺失、类型不符（含浮点/布尔混入整型字段）、非法 `zi_hour_mode`、LT-1/MP-1 校验失败 → `ok:false`，进程不得崩溃。前置条件汇总（调用方责任）：`lichun_unix` 为 `local.y` 年立春；`month_ctx` 与历源一致且含 t；`local` 与 `t_unix` 同刻。

### 4.5 不确定性 op `four_pillars_uncertainty`（v0.3 新增；`four_pillars` 保持 v0.2 语义不变）

当输入时刻本身有精度限制（如出生时间只记到分）且落在判界附近时，单一命盘不可靠
（DESIGN V3.0 §5.2）。本 op = `four_pillars` 全部输入外加**必填** `input_time_precision_seconds`
（整数 ≥ 0），输出 = `four_pillars` 全部输出外加以下三个字段：

- **AMB-1（立春距离）**：`d_lichun = |t_unix − lichun_unix|`。
- **AMB-2（节界距离）**：`d_jie = min(|t_unix − jie_unix|, |t_unix − next_jie_unix|)`。
- **AMB-3（时辰界距离）**：设 `s = hh·3600 + mm·60 + ss`，`x = (s + 3600) mod 7200`，
  则 `d_hour = min(x, 7200 − x)`（当地墙钟秒；时支界在各奇数整点）。
- **AMB-4（日界距离）**：`split` 模式界在当地 00:00:00：`d_day = min(s, 86400 − s)`；
  `unified` 模式界在 23:00:00：`d_day = min(|s − 82800|, 86400 − |s − 82800|)`。
- **AMB-5（判定）**：`uncertainty_sources` = 距离**严格小于** `input_time_precision_seconds`
  的来源列表，元素取自 `["lichun_boundary","jie_boundary","hour_boundary","day_boundary"]`
  （按此固定顺序）；`boundary_distance_seconds = min(d_lichun, d_jie, d_hour, d_day)`;
  `result_status` = 列表非空时 `"ambiguous"`，否则 `"exact"`。precision = 0 恒为 exact。
- 负的 `input_time_precision_seconds` 或缺失 → `ok:false`。其余校验与错误路径同 4.4。

**调用方候选盘协议（呈现层责任，引擎不承担）**：`result_status = ambiguous` 时，调用方
应对 `t − p` 与 `t + p` 各自重新解析上下文（各自的 civil_year、lichun、month_ctx）并调用
`four_pillars`,将去重后的结果作为 `candidate_charts` 与 `uncertainty_sources` 一并呈现,
不得只给单一命盘。

## 5 分级承诺（DESIGN V3.0 §5.1;天文可算 ≠ 民用时间可换算 ≠ 时刻转换无误差）

| 承诺层 | 当前值 | 说明 |
| --- | --- | --- |
| 天文计算范围 | 1900–2100（数据）/ 1901–2099（呈现层开放） | 以已入库并经交叉核对的节气数据为准；扩到 1600–2200 须新历源入库并重新审计 |
| 节气时刻容差 | 标称 ±1 秒（自算求根精度 ≈0.009 s,输出取整到秒） | 外部核对:HKO 分钟级(2026–2028 全量)+ 1984 日期级;分钟级以下的绝对真值以《中国天文年历》入库后为准 |
| ΔT 不确定性 | 2030 年前 ≪1 秒;远期(2040+)随实测更新可能漂移±数秒 | 未来年份节气为**暂定值**(future_provisional),数据再生成即更新 |
| 民用时间(tzdb) | pinned IANA tzdata(呈现层 zoneinfo) | 1970 年前为 historical_best_effort:tzdb 不保证可靠,结果须携带不确定性提示;中国近现代时区/夏令时的人工核验区间随历源逐步登记 |
| 判界归属 | 全部条款闭下界(1.3) | 恰好等于界点不属于不确定性,归界点之后区间 |

### 5.1 留待后续版本（实现方不得先行猜测实现）

- **真太阳时**（v0.4）：均时差与经度修正、跨日对日柱影响、平/真流派开关；
- **大运**（v0.4）：顺逆判定（年干阴阳×性别）、「三天折一岁」精确到天、出生即交节边界；
- **节气注入文件格式**（v0.4）：数据文件 schema、三方比对协议（当前由调用方逐 case 注入）。

## 附录 A 对拍 I/O 协议（JSONL）

两实现各自提供 CLI（Rust：`paipan-cli`；Python：`python3 -m paipan_ref.cli`），从 stdin 逐行读入、向 stdout 逐行输出，行序与输入一致：

**输入行**

```json
{"case_id": "yp-anchor-0001", "op": "year_pillar",
 "input": {"civil_year": 1984, "t_unix": 460000000, "lichun_unix": 444444444}}
```

**成功输出行**

```json
{"case_id": "yp-anchor-0001", "ok": true,
 "output": {"bazi_year": 1984, "stem": "甲", "branch": "子", "ganzhi": "甲子"}}
```

**失败输出行**

```json
{"case_id": "...", "ok": false, "error": "unknown op: xxx"}
```

- 未知 `op`、缺字段、类型不符 → `ok:false`，进程不得崩溃，继续处理后续行。
- 输出 JSON 的字段顺序不作要求；比较按字段语义严格相等；输出编码为 UTF-8，干支字段为汉字字符串。
- 本协议中的时间戳示例为任意占位数值，不代表任何真实历法事实。

**`four_pillars` 输入/输出行示例（数值为占位）**

```json
{"case_id": "fp-xxxx-0001", "op": "four_pillars",
 "input": {"t_unix": 100, "lichun_unix": 50,
   "local": {"y": 2000, "m": 6, "d": 1, "hh": 8, "mm": 30, "ss": 0},
   "month_ctx": {"jie_seq": 3, "jie_unix": 90, "next_jie_unix": 200},
   "zi_hour_mode": "split"}}
```

```json
{"case_id": "fp-xxxx-0001", "ok": true,
 "output": {"bazi_year": 2000,
   "year":  {"stem": "庚", "branch": "辰", "ganzhi": "庚辰"},
   "month": {"stem": "辛", "branch": "巳", "ganzhi": "辛巳"},
   "day":   {"stem": "戊", "branch": "戌", "ganzhi": "戊戌"},
   "hour":  {"stem": "丙", "branch": "辰", "ganzhi": "丙辰"}}}
```

（示例输出不构成期望值；期望值一律由条款公式与权威历源生成。）

## 附录 B 边界用例枚举

**年柱**：立春前 1 秒 / 恰好立春 / 立春后 1 秒；`Y < 4` 的取模非负性；60 年周期回环；负 Unix 时间戳。
**月柱**：各节交节前 1 秒 / 恰好 / 后 1 秒；`month_ctx` 窗口不含 t 的错误路径；`jie_seq` 越界。
**日柱**：格里历闰年 2 月 29 日；世纪年（1900 平年/2000 闰年）；两种 `zi_hour_mode` 下 22:59:59 / 23:00:00 / 23:59:59 / 00:00:00 的日柱归属。
**时柱**：全部 12 个整点界（恰好归后一支）；晚子时（23 点起）在 `split` 模式下时干用次日日干、`unified` 模式下与日柱一致换日。
**组合**：非法 local（2 月 30 日、hh=24）、非法 `zi_hour_mode`、浮点/布尔混入整型字段。

## 附录 C 条款-测试映射（V2.1 规格 Oracle 要求）

| 条款 | 黄金用例前缀（golden-tests/） |
| --- | --- |
| YP-1/YP-2/YP-3 | `yp-*`（fixed/year-pillar-smoke、boundary/year-pillar-lichun） |
| LT-1 | `fp-badlocal-*` |
| MP-1 | `mp-jie-*`（boundary）、`fp-badctx-*` |
| MP-2 | `mp-wuhu-*` |
| DP-1/DP-2/DP-3 | `dp-anchor-*`、`dp-cycle-*` |
| DP-4 | `dp-zimode-*` |
| HP-1 | `hp-branch-*` |
| HP-2 | `hp-wushu-*`、`hp-latezi-*` |
| four_pillars 错误路径 | `fp-err-*` |
| AMB-1…5 | `fp-amb-*` |

---

*变更记录：v0.1（2026-07-12）首版，仅含年柱（作为双实现对拍全流程彩排的最小算法）。v0.1 评审通过（2026-07-14），内容无改动。v0.2（2026-07-14）新增 LT-1、MP-1/2、DP-1/2/3/4、HP-1/2、four_pillars op、附录 B 扩充与附录 C 条款-测试映射；依据见 docs/research-notes/calendar-facts-sources-2026-07-14.md。v0.3（2026-07-14）新增 four_pillars_uncertainty op（AMB-1…5,独立 op 保持 v0.2 位级兼容）与第 5 章分级承诺。*
