# prompts(运行态辩手/仲裁提示词,版本化管理)

```
prompts/
├── base/                 # 提示词本体(debaters/、arbiter/),模型无关骨架
├── provider-adapters/    # 各供应商适配层(输出格式、工具调用差异)
└── manifests/            # 每版提示词的清单与评测基线引用
```

**纪律(INV-10 + dev-plan 2A.1)**:

1. **提示词视同代码**:改动走 PR;文件头部维护 `version:` 与变更说明。
2. **起草与审计分离**:Fable 5 起草 → Codex 做偏袒盲审计(三辩手提示词的信息量、约束严格度、示例质量对称性,警惕对 Claude 辩手的隐性利好)→ Change Eval 闸门(含对称性检查)→ 本人批准。Codex 不参与编写。
3. **单向阀**:开发会话中的临时 prompt 片段禁止直接上线;运行态模型不写代码。
4. 防隐性漂移:每月对比首版基线,累计偏移写入 `CHANGELOG.md`;指标劣化 CI 拒绝(指标见 evals/README.md)。
