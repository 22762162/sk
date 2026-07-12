# backend（FastAPI 应用层）

P1 中后期启动，当前为占位。

- 用户可见文案受红线词扫描约束（`make redline` 覆盖本目录）：大陆版禁用词见 `infra/compliance/redline-words.txt`，论断一律概率化措辞。
- 结果页/报告/订阅接口的响应文案必须包含免责声明字段（compliance-auditor 检查项）。
- 未成年人拦截与危机识别转介属于本层强制路径，接口设计时预留。
