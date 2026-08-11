# web（L5 手机优先 PWA + 高级研究页）

- `/`：可安装 PWA，底部导航为“首页、问事、记录、我的”。Service Worker 只缓存 App 壳；
  私密 API 响应不进入 Cache Storage，离线查看由当前浏览器的私有缓存承担。
- `/legacy`：保留原排盘、三模型会诊、流月、合盘与档案研究页，既有能力不改接口。
- “我的 → 编辑基本盘”可从高级研究载入本人录入的既成事实；载入内容须人工检查并保存，
  后续问事才会引用。历史模型结论不会自动导入，避免循环自证。
- 离线模式只允许查看最近缓存的基本盘和预测快照；问事与复盘写入必须联网，不做假成功。

## 最小部署约束

本机用 `make v1-serve` 后访问 `http://127.0.0.1:8788`，localhost 环境可直接注册 Service Worker。
私有 VPS 必须使用 HTTPS，并让页面、`/api/*`、`/manifest.webmanifest` 与 `/sw.js` 保持同源；反向代理
不要缓存 `/api/*`，且 `/sw.js` 不应设置长期缓存。项目仍按 DESIGN 定位仅供本人使用；若跨设备访问，
须在反向代理层加认证，不能直接暴露公网。

本机私有数据在 `consult-engine/appdata/sanjian-app.sqlite3`，旧版 `predictions/`、`records/`、
`dossier/` 保持原位。以上路径均已 gitignore；迁移前可停服务后整体备份 `consult-engine/appdata/`。

文案纪律：INV-04——概率化措辞 + 免责标注；`make redline` 扫描本目录全部可见字符串。
