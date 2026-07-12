# Codex 任务模板 · ref-implementer（盲实现参考版）

> 使用方式：在 Codex 的**独立工作区**（独立 worktree 或云端沙箱）中，将本模板 + 指定的 spec 章节作为任务输入。

## 任务

依据 `docs/paipan-spec.md` 第 {{SPEC_SECTION}} 节，在 `engine-paipan-ref/` 中用 Python 实现 {{FEATURE_NAME}}。

## 硬性约束

1. **禁止查看 `engine-paipan/` 目录的任何文件**——这是对拍有效性的前提。接口契约以 spec 为唯一依据；spec 有歧义时停止实现并列出问题清单，不得自行猜测补齐。
2. 仅使用 Python 标准库（测试可用 pytest）。零第三方运行时依赖。
3. 确定性：禁止网络、系统时钟、无种子随机。历法事实只能来自注入的参数或数据文件。
4. 实现 spec 附录的对拍 JSONL 协议：`python3 -m paipan_ref.cli` 从 stdin 读 case、向 stdout 写结果。
5. 附单元测试：判界函数必须含边界三连测（界前 1 秒、恰好等于、界后 1 秒）。

## 交付

- 实现代码 + 测试（`engine-paipan-ref/`）
- `SPEC-QUESTIONS.md`：实现过程中发现的 spec 模糊点（供 Opus 规格会话消歧）
