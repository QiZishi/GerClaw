# Skill

对应设计要求 §4.9。契约覆盖 list/load/register/execute/generate/evolve；执行实现复用 AgentScope SkillLoader/Toolkit。

自然语言“自进化”是受控修订，而不是自动发布：`POST /skills/{skill_id}/evolve` 仅对当前调用者的自定义 Skill 生成下一版本的 Markdown 草稿。后端校验当前 revision、原 ID 与递增 SemVer；草稿不会写入数据库、不会启用，也不会改变当前对话加载的版本。用户仍须在界面完整审阅后调用正常更新接口保存。

保存新的 `source_markdown` 时也会比较旧、新 SemVer；同版本或倒退版本的行为替换被拒绝。每个启用并实际加载到 AgentScope 的 Skill 还会由服务端按其已验证的 ID、版本与 allowlisted tools 构建精确 `security-risk-profile-v1`：所有 Skill 都要求 schema、输出、预算、非信任数据和患者归属控制；联网 Skill 额外要求外发脱敏，证据检索 Skill 额外要求 provenance。此档案不来自 Markdown、浏览器或模型，不能由 Skill 自行放宽。

生成与修订响应还包含 `skill-draft-quality-v1` 的确定性审阅提示，覆盖输入核对、本地证据、红旗和医疗免责声明是否在草稿中出现。它不读取或回传额外用户内容，不调用第二个模型，不评估医学有效性，也不改变“人工审阅后显式保存”的发布边界。

临床诊断、开始/停用/替换药物或调整剂量不能在无可追溯证据时被写成事实或指令。存在本轮证据时，生成器可以生成带适用条件和依据的可审阅建议；Skill 本身不能执行该动作。患者版产物只在全文末尾保留一句风险与医生复核提示，医生版直接呈现建议、条件和证据，不添加机械性拦截。

模型生成和修订的原始投影必须通过严格的
`skill-generation-model-output-v1`。缺失/旧版本、未知字段或不符合 schema
的 provider 输出会在 Markdown 序列化前受控失败，不能作为未版本化草稿进入
人工审阅。

## 维护与演进

**可安全改进。** 可提高生成/修订质量、编辑器体验、外部模型评测和临床 Skill 发布审核；生成器变化必须同步更新 `skill-generation-model-output-v1`、quality case、SemVer/revision 测试和人工审核界面。

**不可破坏的契约。** 自进化只能产出草稿，不能自动写库、启用、执行或改变正在使用的 revision；相同 ID 的行为替换必须递增 SemVer，加载前必须重新通过服务端 profile。无证据的诊断/调药事实不得进入草稿，有证据的建议仍是可审阅而非可执行动作。

**性能与回归验收。** 覆盖 generate→审阅保存→会话加载→evolve→revision 冲突→删除，以及 provider 结构输出失败；运行 `skill-draft-case-v1`。真实模型回归要单列耗时、成功率、schema 拒绝率；10 并发 evolve 同一 Skill 只能产生一个可接受的下一 revision。
