# PR #54 独立安全审查 · Claude(审查方)

> **审查模型**:本次会话 UI 报告 Fable 5 safeguards 触发并自动切换为 **Opus 4.8** 执行审查
> (exact model id / Claude Code 版本无法从会话内确认,详见 attestation,不猜测)。

- **最终审查对象(v3 修复):固定 commit `97941de04c2fff622e0a668d36137a247755b173`**;
  历史:v1/v2 审查对象为 `282a14744b85782ac064e6da6b97965b351cb70f`(修复前)。
- 方式:独立只读审查(reviewer worktree `sk-p54-review` @ `agent/p54-claude-review`,未改作者工作树);
  仅合成 token;未读 .env/真实 token 文件内容/真实数据库/业务记录,未调用模型 API;未合并/部署/重启线上。
- 作者测试:`test_device_auth.py` **7/7 通过**;独立探针 `test_device_auth_claude_probe.py` **10/10 通过**。

## Verdict:**approved**(修复提交 `97941de04c2fff622e0a668d36137a247755b173` 已解除 BLOCK-1/OBS-404;详见文末"增量复审 v3")

**审查演进**:v1(仅审域名 HTTPS 直连单层)→ approved;v2(补审 iOS 本地 fallback 两层)→ **blocked**
(BLOCK-1:旧 auth_proxy 剥离凭据致第二跳 401);**v3(审 97941de 修复)→ approved**——新增版本化
`native_proxy.py`:剥离浏览器凭据后在 loopback 第二跳注入服务端 device token,剥离 8788 Set-Cookie,
两层用不同 session_context;经 8 项独立两层合成探针证明 BLOCK-1/OBS-404 解除、无新 blocker。
下方 v1 逐项核验、v2 阻断记录均保留为审计历史。**部署前必须完成:8790 launcher 从旧 auth_proxy
切换到版本化 native_proxy**(见 v3;当前 launcher 仍指向旧 auth_proxy,未切换=BLOCK-1 现实仍在)。

## 逐项核验(按审查重点)

| 检查面 | 结论 | 依据 |
|---|---|---|
| fail-closed 配置 | ✓ | `enabled 且 token 非法→DeviceAuthConfigError`;env 缺 token 文件/权限过宽(&0o077)/不可读→抛错不启动;探针 test_config/env_* 验证 |
| token 文件权限 | ✓ | `stat.S_IMODE & 0o077` 拒 group/other 可读;探针实测 0o644 拒、0o600 过 |
| 时序比较 | ✓ | `_matches`/`_valid_session` 均 `hmac.compare_digest`;整数解析怪癖(`1_0`/`+`/前导空格)由最终全串规范化比较兜底,不绕过(探针 test_int_parse_quirks) |
| Cookie 签名+30天到期 | ✓ | 会话=`ts.HMAC(token,ctx:ts)`;`issued_at>now+300` 或 `now-issued_at>30d` 拒;探针 test_session_tamper_and_expiry |
| 轮换失效 | ✓(需重启) | 签名密钥=device token;换 token 后旧会话签名验证失败即失效(探针 test_rotation)。**限制**:token 仅 from_environment 读一次,轮换生效须重启服务——见确认项①ROTATION |
| 前端移除可见口令/JS 凭据 | ✓ | app.html 删除 `#brain-access` password 输入与解锁/锁定;brain.js `token`→`authorized` 布尔、`headers()` 返回 `{}`;残留"解锁/管理绑定"仅为路由文案,非凭据 |
| 全站中间件顺序 | ✓ | 单一 app-level middleware,`DEVICE_AUTH.middleware` 在 `call_next`(路由)前设 `request.state.device_authenticated`;含 `/static` 挂载与所有 API |
| request.state 注入可靠性 | ✓ | 未注入路径经 `getattr(...,False)` 安全默认为未认证;无法在不持有效会话时置 True |
| Brain route/问事快照授权可否绕过 | ✓ 未发现绕过 | `require_access` 与 `app_question_start` 均经 `request_authorized`;启用设备门后请求必先过全站门禁。数据隔离仍由 `brain_context.consume` 在 DB 层校验(公司/项目/版本/单次消费),授权放宽不导致越权数据(见权衡项①) |
| CSRF/会话固定/重放 | ✓/观察 | SameSite=Strict+HttpOnly+原生 WKWebView 同源→CSRF 面极小;会话服务端签发不可固定;30 天 bearer 会话在此期可重放(标准模型,HttpOnly 挡 XSS 窃取)——见建议① |
| X-Forwarded-* 信任 | ✓ | `secure=True` 硬编码,不依据任何代理头决策,无 X-Forwarded 欺骗面 |
| Secure/HttpOnly/SameSite | ✓ | 三属性齐全且 SameSite=strict;RFC 已声明"生产设备会话要求 HTTPS" |
| 缓存/SW 离线壳 | 观察 | 中间件对全响应加 no-store(原仅 /api/app/*);SW Cache API 不受 HTTP no-store 约束,离线壳仍可工作,但启用门禁后 SW 预缓存时序需确认——见确认项②SW |
| 关门时合成测试/运维兼容 + 生产误配安全失败 | ✓ | 未启用门禁时 `device_authenticated=False`,brain 回退 `access_allowed(supplied)`;前端已不发口令→生产误配"想开却没开"时 brain 全 401(fail-closed);合成测试/运维仍可用 X-Sanjian-Brain-Access |

## 上线前必须确认项(不阻断合并,启用生产门禁前逐条落实)

**① HTTPS 拓扑(最高优先)**:会话 Cookie `Secure=True`。原生 App 首屏导航带 `X-Sanjian-Device-Token`
换 Set-Cookie,后续子资源/XHR 仅靠 Cookie(WKWebView 不给子资源加自定义头)。**若 App 直连
`http://127.0.0.1` loopback,Secure Cookie 会被丢弃→子资源全部 401→白屏**。这是 fail-closed(安全),
但运维不得为"修白屏"而关闭 Secure。RFC 已声明生产要求 HTTPS——请确认 App 实际经 HTTPS 中继
(sk.live 或本地 https)访问,并将"禁止关闭 Secure"写入运维契约。

**② SW 预缓存时序**:启用门禁后,Service Worker install 的 `cache.addAll(['/','/static/...'])`
以 `credentials:'same-origin'` 发起——须在设备会话 Cookie 已写入后注册/更新 SW,否则预缓存请求
401 致 install 失败、离线壳不可用。建议:仅在首个已认证响应后再 `register()`,并对 SW 更新做同样约束。

**③ ROTATION 生效需重启**:device token 轮换后须重启 App 后端进程才生效(token 仅 from_environment
读一次)。请把"轮换=改文件+重启服务"写入运维手册;与出口侧 `HUOHUO_EXPORT_TOKEN` 轮换同步进行。

## 设计权衡(信息项,非缺陷)

**① 设备会话即全权 Brain**:启用门禁后,设备会话通过全站门禁即视为 Brain 授权,原"公司页独立口令
二次解锁"的纵深防御被移除(产品无感目标的取舍)。可接受的前提是:数据仍受 snapshot 的
company/project/version/单次消费在 DB 层强隔离(P2 审查已确认),故授权放宽不产生越权数据。
若未来 Brain 数据敏感度上升,建议恢复对 L4 预览的二次确认。

## 建议(可选,非必须)

**① 会话重放收敛**:30 天 bearer 会话较长。可选加入服务端会话版本号(随 token 轮换递增)或缩短
到期并滑动续期,降低 Cookie 泄漏后的重放窗口。当前模型可接受。

**② 探针纳入 CI**:建议把本审查探针(或作者测试)纳入后端 CI 常驻,防未来回归削弱授权边界。

## 最小修复建议(若作者选择在本 PR 收敛确认项)

- 确认项①/②/③均为部署契约,代码无需改;若要在代码侧加固:SW 注册门控(②)可在 app.js 加
  `navigator.serviceWorker.register` 前置"首个已认证响应"判断;其余写入 RFC/README 运维节即可。

---

## 增量复核 v2(两层拓扑兼容性;2026-09-01)

**触发**:第一版遗漏 iOS 本地 Wi-Fi/USB fallback 的两层拓扑。补审 `sk-ios/RemoteAccess/auth_proxy.py`
(只读源码,未 import、未读 token 内容)与 `sk-ios/SanjianIOS/ContentView.swift`(既有 iOS,不在本 PR diff)。
独立探针 `test_device_auth_twohop_probe.py` **4/4 通过**(纯合成两层 ASGI,零真实/网络/重启)。

### 阻断项 BLOCK-1:8790 auth_proxy → 8788 第二跳凭据被剥离,启用门禁后必然 401

- **事实链**(源码依据):
  1. `auth_proxy.py:20` UPSTREAM=`http://127.0.0.1:8788`;`:69` 用自有 `sanjian_native_session` cookie 鉴权;
  2. `:121-125` 转发到 8788 时,请求头过滤集合含 `cookie` 与 `x-sanjian-device-token`——**两者都被剥离**;
  3. PR#54 在 8788 启用 `SANJIAN_REQUIRE_DEVICE_AUTH=1` 后,`device_auth.middleware` 对全站要求
     设备头或 8788 自签会话;proxy 转发来的请求二者皆无 → 401。
- **iOS 侧证据**:`ContentView.swift:156` 本地候选 `http://skdeMac-Studio.local:8790/`;`:171` 仅经
  `/__native_auth` 握手(不含 direct-root 例外),即本地接入**只能**经 8790 代理这一跳。
- **合成证明**:`test_local_fallback_through_proxy_is_broken` —— 剥离后转发的请求对 8788 返回 **401**。
- **影响**:上线启用门禁后,**iOS 本地 Wi-Fi/USB fallback 必然断连**(Mac 关机/域名不可达时的唯一本地路径)。
  这是 fail-closed(安全方向),但中断既有已支持接入路径,与 PR"无感连接"目标冲突。
- **附带**:两侧 cookie 同名 `sanjian_native_session` 但签名密钥不同(8790=其 device token / 8788=
  `SANJIAN_DEVICE_TOKEN_FILE`),即便不剥离也会签名不匹配——剥离使其成为纯"无凭据 401"。

### 核对①:固定域名直连 8788 路径 —— 正常(未受本阻断影响)

- `ContentView.swift:138` 探测请求设 `X-Sanjian-Device-Token`;`:165` 固定域名先试 allow-listed root。
- 合成证明:`test_direct_domain_with_device_token_passes` —— 带 device token 直连 → **200 + Set-Cookie**;
  `test_direct_domain_with_session_cookie_passes` —— 带会话 cookie → **200**。
- 结论:App→固定域名 HTTPS 直连 8788 的路径在门禁下正常(仍受第一版确认项①HTTPS/②SW 时序约束)。

### 核对②:/__native_auth 在直连 8788 的 404 降级 —— 会导致该候选失败(非卡死循环,但断链)

- 8788 无 `/__native_auth` 路由。合成证明:`test_native_auth_route_404_on_direct_backend` —— 带有效
  device token 过门禁后,该路径返回 **404**(而非 App 期望的 200+Set-Cookie)。
- iOS 候选注释(`:162-164`)预期"auth proxy 会以 401 前进握手";但直连 8788 时:root 直连带 device token
  已 200 成功,不会前进到 /__native_auth;仅当 root 直连失败(device token 无效)才前进,此时得 404
  → 该候选判失败 → 尝试下一候选(本地 8790,已被 BLOCK-1 断)→ **全部候选失败**。非无限卡死循环,
  但在 device token 失效或域名不可达时无可用接入。

## 最小修复建议(不改产品实现;跨组件协调,择一)

1. **(推荐)auth_proxy 转发时注入 8788 服务间凭据**:8790 验证完自身会话后,转发前注入
   `X-Sanjian-Device-Token: <8788 的设备 token>`(仍剥离用户 cookie 以保持隔离)。需 auth_proxy 侧改动
   + 运维给其只读 8788 token 文件权限。此方案保留本地 fallback 且不弱化 8788 门禁。
2. 或 8788 为**本机 loopback 的 auth_proxy**开受信内网路径——**不推荐**(弱化全站门禁,任何本机进程可绕过)。
3. 或产品决策**放弃本地 fallback**,仅域名 HTTPS,并从 iOS 候选移除 8790 与 /__native_auth 分支
   (牺牲 Mac 局域网/USB 离线接入)。
- 附:若保留本地 fallback,建议 iOS 候选对"固定域名直连 8788"移除会导向 404 的 /__native_auth 分支,
  或由 8788 提供兼容握手端点,避免 device token 失效时的候选断链。

**解除阻断的验收**:采用方案后,需要一次合成两层探针证明"经 auth_proxy 转发的请求在 8788 门禁下通过",
且固定域名直连与本地 fallback 两条路径同时 200;由独立审查复核。

## 测试统计(增量后汇总)

- 作者 `test_device_auth.py`:7/7
- 独立单层探针 `test_device_auth_claude_probe.py`:10/10
- 独立两层探针 `test_device_auth_twohop_probe.py`:4/4(BLOCK-1 证明 + 域名直连/404 核对)

---

## 增量复审 v3(BLOCK-1/OBS-404 修复验证;2026-09-01)

**审查对象**:修复提交 `97941de04c2fff622e0a668d36137a247755b173`。只读审查,未改产品实现。
独立两层探针 `test_native_proxy_claude_probe.py` **8/8 通过**(纯合成 token + ASGITransport
两层直连,零真实/网络/重启);作者 `test_native_proxy.py`+`test_device_auth.py` 复核 **10/10 通过**。

### BLOCK-1 → 已解除
新增 `backend/native_proxy.py`(版本化 8790 代理),经探针逐条证明:
- 第二跳注入服务端凭据(`native_proxy.py:130-138`):先剥浏览器 cookie 与 device header,**之后**注入
  服务端 device token → 8788 门禁认得 → **200**(`test_local_fallback_end_to_end_200`)。
- 注入顺序不可被浏览器覆盖(`test_browser_device_header_cannot_override_injection`)。
- 浏览器 cookie 不进第二跳 + 8788 Set-Cookie 不回浏览器(`:133`/`:152`;双向探针证明)。
- 两层会话 session_context 隔离,双向不可重放(`test_session_contexts_are_isolated`)。
- 代理自身 `sanjian_proxy_session` 鉴权;错误 token/错误 proxy cookie 均 401。

### OBS-404 → 已解除
`app.py` 新增 `/__native_auth`→302;直连 8788 带 device token 时 middleware refresh 设 native cookie,
302 即完成 cookie 交换(`test_native_auth_direct_backend_is_302_with_cookie`:302+cookie,非 404)。

### 固定域名直连 8788 → 仍正常
`test_direct_backend_token_then_cookie`:device token→200+native cookie,后续 cookie→200。

### device_auth.py 重构核验
session_context 参数化(空 context→DeviceAuthConfigError)、read_device_token_file 公共化(保留权限
&0o077 检查)、issue_session/valid_session 公共方法;v1 的 10 项授权探针语义不变仍适用。

### 其它(SSRF/压缩/body/安全头/token 泄漏)
upstream client `follow_redirects=False`+`trust_env=False`+base_url 固定 loopback;压缩用
`upstream.content` 重建并剥 content-encoding/length,自洽;请求 1MB 上限;异常响应带安全头、
错误文案不含 token(`test_error_responses_have_security_headers_and_no_token_leak`)。低危观察:
path 逃逸未证实可利用(需先持有效 proxy 会话,固定 base_url 下仍解析 loopback),建议作者补断言;
上游响应体无显式上限(本地可信后端)。

## 部署前必须完成(未部署,勿写成已上线)
1. **【最高】8790 launcher 切换到版本化 native_proxy**:实测 `com.sanjian.auth-proxy.plist` 当前仍
   指向旧 `RemoteAccess/auth_proxy.py`(剥离且不注入)。**不切换=8788 启用门禁后 BLOCK-1 现实仍在**。
   切换后需一次两层合成冒烟确认第二跳 200。
2. HTTPS 拓扑(Secure 全程 HTTPS,严禁为 http loopback 关闭)、SW 预缓存时序、
   device token 轮换须同步 proxy 与 backend 并重启、proxy token 文件 &0o077 收紧。

## 测试统计(v3 汇总)
- 独立两层修复探针 `test_native_proxy_claude_probe.py`:8/8
- 作者 `test_native_proxy.py`+`test_device_auth.py` 复核:10/10(作者声称全套 57 unittest + 32 bridge pytest 全绿)
- v1 单层独立探针 10/10、v2 两层 blocked 证明 4/4:历史留痕,BLOCK-1 由本次修复解除。
