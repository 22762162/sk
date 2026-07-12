# app（Flutter 客户端）

P1 中后期启动，当前为占位（`flutter create` 时再初始化工程）。

- 双 AI 按页面模块并行：Claude Code 负责排盘可视化、会诊直播 UI、订阅支付；Codex 分担学习模块、档案页——按接口契约并行开发，契约先行。
- 全部用户可见字符串集中于本地化文件，受 `make redline` 扫描约束。
- 免责声明组件不得被折叠/截断（compliance-auditor 检查项）。
