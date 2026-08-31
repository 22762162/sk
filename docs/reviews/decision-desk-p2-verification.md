# 决策台 P2 · 验证与交付边界

状态：实现及双方交叉审核已完成，合成验证通过；等待人工审阅，未合并、未发布、未安装到手机。

## 实际协作

- Codex：App 路由、公司/项目绑定、预览与一次性确认、SQLite v4、手机界面和串联测试。
- 本机 Claude Code（Fable 5，桌面会话 `c06fc80a-fe7e-46f1-bace-da4207b1125a`）：独立出口服务与合成测试。
- 命令行 Claude OAuth 已失效；实际协作由既有 Claude 桌面会话接单，状态文件留痕。
- 双方隔离工作树。Claude 原先直接HTTP连接器保留未推送；未纳入本次交付。
- 只读出口经 Codex 两轮审查并修复，再由 Claude 反向审查 App，报告无阻断项。
  发布签署仍归用户；合成通过不是生产就绪证明。

## 已验证

- App 46 项合成单元/API/串联测试通过：旧记录保留、v4可重复迁移、防降级、鉴权、错误等级/来源拒绝、
  原文不持久化、跨范围拒绝、过期拒绝、改绑失效、并发一次性使用、失败整笔回滚。
- 独立出口 31 项合成测试通过；App 的串联测试使用实际出口工厂、SQLAlchemy 只读源与临时 SQLite，
  验证授权隔离、L5剔除、分币种金额合计、缺月不输出零和摘要消费；没有真实数据库/云端模型调用。
- Claude 独立复跑 App 安全与 API 子集：21 passed，另含8个subtests。
- 真实浏览器合成界面验证：公司解锁→选择明确来源→绑定→问事预览→手工摘要→云端使用确认→提交。
  提交在测试桩处停止，无任何真实云模型调用。原文在确认后从DOM清除；新页面不保留口令。
- 390×844 手机宽与1024×900桌面宽：document.scrollWidth均等于innerWidth，无横向溢出。
- 红线扫描、JS语法、git diff空白检查通过。新增CI执行App与出口合成测试，依赖固定版本与哈希。
- 已处理 Claude 的月份长度、单 worker、两种口令部署说明及“尽快提交”建议；CSP需要覆盖原生壳、
  远程API地址与旧专家页，留给独立安全变更；未直接套用可能破坏现有界面的全站策略。

## 不可误报为已完成

- 未连接/迁移真实 PostgreSQL；未配置真实数据库账号、口令、公司/项目授权映射。
- L3/L4含流水仅受保护预览，不外发。只有本人逐条编辑确认的L1/L2摘要参与模型材料。
- 摘要去标识仍需人工核对；正则无法自动识别所有人名/地址/商业秘密。
- 旧App的档案/历史接口仍采用原有部署访问边界。本次只保护新增大脑入口，不宣称全站鉴权整改完成。
- Claude 在交接之前的旧连接器探索接触过真实数据/凭据排查，其披露记录在协作文档；Codex没有复现这些操作。
  新出口与App测试全部合成；不能用新阶段的合成测试声明掩盖旧阶段接触。
- 六爻/梅花 PR45 保持草稿，未纳入本次发布；独立对拍不读取参考源码。
- 资料接入不构成术数准确性证明，不自动上调置信度或把公司流水推定为个人收入。

## 发布前需要本人处理

1. 确認公司/项目与大脑scope的精确映射和经营数据快照口径。
2. 由运行环境注入专用只读DSN与访问凭据；开发AI不得从.env或容器提取。
3. 在非生产PostgreSQL进行只读权限、超时和故障验证；备份App数据库后验证v3→v4。
4. 审阅交叉报告并明确签署合并/发布。未签署前，所有改动停留分支/PR。

## 复验命令

```sh
uv run --with-requirements backend/tests/requirements.lock python3 -m unittest discover -s backend/tests -p 'test_*.py'
uv run --with-requirements backend/tests/requirements.lock python3 -m pytest integrations/huohuo_bridge/tests -q
make redline governance-check rulebase-check prompt-symmetry prereg-check
node --check web/brain.js
node --check web/app.js
git diff --check
```

依赖存在一条上游 TestClient/httpx 弃用警告；版本已锁定，测试通过。本次未修改 L1 计算、运行态
prompts、contracts、参考实现或私有评测集。
