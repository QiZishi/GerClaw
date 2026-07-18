# Skill

对应设计要求 §4.9。契约覆盖 list/load/register/execute/generate/evolve；执行实现复用 AgentScope SkillLoader/Toolkit。

自然语言“自进化”是受控修订，而不是自动发布：`POST /skills/{skill_id}/evolve` 仅对当前调用者的自定义 Skill 生成下一版本的 Markdown 草稿。后端校验当前 revision、原 ID 与递增 SemVer；草稿不会写入数据库、不会启用，也不会改变当前对话加载的版本。用户仍须在界面完整审阅后调用正常更新接口保存。

保存新的 `source_markdown` 时也会比较旧、新 SemVer；同版本或倒退版本的行为替换被拒绝。每个启用并实际加载到 AgentScope 的 Skill 还会由服务端按其已验证的 ID、版本与 allowlisted tools 构建精确 `security-risk-profile-v1`：所有 Skill 都要求 schema、输出、预算、非信任数据和患者归属控制；联网 Skill 额外要求外发脱敏，证据检索 Skill 额外要求 provenance。此档案不来自 Markdown、浏览器或模型，不能由 Skill 自行放宽。

生成与修订响应还包含 `skill-draft-quality-v1` 的确定性审阅提示，覆盖输入核对、本地证据、红旗和医疗免责声明是否在草稿中出现。它不读取或回传额外用户内容，不调用第二个模型，不评估医学有效性，也不改变“人工审阅后显式保存”的发布边界。

模型生成和修订的原始投影必须通过严格的
`skill-generation-model-output-v1`。缺失/旧版本、未知字段或不符合 schema
的 provider 输出会在 Markdown 序列化前受控失败，不能作为未版本化草稿进入
人工审阅。
