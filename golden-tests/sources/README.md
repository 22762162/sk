# sources —— 权威历源比对数据

黄金集与对拍中一切**真实历法事实**的唯一合法来源(数据来源纪律见上层 README)。

## 已入库

### `solar_terms_de440s_1900_2100.jsonl` —— 节气时刻(JPL 自算)

- **内容**:1900–2100 年全部二十四节气时刻,共 4824 条。字段:`term`(节气名)、`lambda_deg`(太阳视黄经)、`civil_year`(北京时间所在公历年)、`unix`(Unix 秒,UTC,四舍五入到秒)、`utc` / `beijing`(可读时刻)。
- **方法**:定气法(GB/T 33661-2017;太阳视黄经每达 15° 整倍数为一节气,λ=315° 为立春),由 `tools/gen_solar_terms.py` 基于 JPL DE440s 星历计算。
- **依赖与版本**(复现实验须一致):JPL DE440s(见下)+ Skyfield 1.54 + NumPy 2.4.6,Python 3.11。
- **ΔT 说明**:TT−UT 使用 Skyfield 内置 IERS 观测值 + 长期模型;未来年份为外推预测值,与各天文年历的处理一致,远期(2040+)时刻可能随 ΔT 实测更新有±数秒漂移——届时重新生成即可。
- **精度**:求根精度 ≈0.009 秒;输出取整到秒,标称 ±1 秒。

### `hko_solar_terms_2026_2028.jsonl` —— 香港天文台对照表(独立来源)

- 抓取自 [HKO 二十四节气页](https://www.hko.gov.hk/sc/gts/astronomy/Solar_Term.htm)(2026-07-14),香港时间、分钟精度。HKO 注明其数据依据英国皇家航海历书局及美国海军天文台——与 JPL 管线相互独立。
- **交叉核对结果**(`tools/check_against_hko.py`):2026–2028 共 72 条,**最大偏差 30 秒**(= HKO 分钟取整的理论上限),0 条超差。
- 历史抽查:HKO [1984 年历 PDF](https://www.hko.gov.hk/tc/gts/time/calendar/pdf/files/1984.pdf) 确认 1984 为甲子年、立春 2 月 4 日,与自算一致(日期级)。

### `ephemeris/`(gitignored)

JPL DE440s 星历二进制,31MB 不入库。复现下载:

```bash
curl -fL -o golden-tests/sources/ephemeris/de440s.bsp \
  https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp
# SHA-256: c1c7feeab882263fc493a9d5a5b2ddd71b54826cdf65d8d17a76126b260a49f2
```

## 许可

JPL/NAIF 星历数据为美国政府作品(公有领域);Skyfield 为 MIT 许可;HKO 数据仅作交叉核对引用,注明出处,不批量再分发。

## 仍待补齐(三方比对的第三方)

- [ ] 采购中科院紫金山天文台《中国天文年历》(或授权电子数据),覆盖分钟级历史年份核对——当前历史年份仅有日期级抽查。
- [ ] (可选)寿星万年历导出数据作为第四信号源。
