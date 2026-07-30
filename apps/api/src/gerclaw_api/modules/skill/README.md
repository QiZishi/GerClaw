# Skill

对应设计要求 §4.9。契约覆盖 list/load/register/execute/generate/evolve；执行实现复用 AgentScope SkillLoader/Toolkit。

自然语言“自进化”采用双轨隔离。`POST /skills/{skill_id}/evolve` 先按
tenant/actor 查出真实 Skill，再校验当前 revision、原 ID、递增 SemVer、schema、
tool allowlist 和实际内容差异：

- `presentation` 与受限 `retrieval` 只有在当前版本和候选都使用服务端固定 directive DSL，
  且 name、category、工具、参数 schema 与自由文本完全不变时，才可通过
  `skill-evolution-decision-v1` 在线形成下一 revision；它只允许增删固定指令并保留原 enabled 状态。
- 临床规则、工具列表、参数 schema、权限/控制面内容和无法可靠分类的变更进入
  immutable track。服务端把候选、基线、请求、Trace 绑定和内容摘要写入 owner-scoped、
  AES-GCM 加密的 append-only `skill_evolution_proposals`，在线响应只返回
  `skill-evolution-proposal-receipt-v1` 去内容化回执，不回传候选 Markdown，也不改变生产 Skill
  或当前对话冻结的 revision。相同 owner、Skill、基线 revision 和候选内容只形成一条提案。
  后续隔离离线控制器必须从该提案冻结候选并完成 paired/sealed evaluation，在线路径没有批准或激活接口。
  所有 evolve 调用都必须由请求边界提供真实 Trace ID 和用途隔离 HMAC request fingerprint；Skill
  模块不会生成临时 Trace 或用候选明文的普通摘要冒充请求 provenance。
- `category`、风险等级、ownership 与 governance authority 均不能由浏览器、模型或
  Markdown 自报获得；分类使用服务端实际定义，未知情况 fail closed。

人工创建、导入和显式编辑仍是既有的用户内容管理边界，不属于自动自演化授权。
它们仍会经过完整解析、安全校验、工具 allowlist、SemVer 与 revision 检查。

固定 DSL 的准入常量和 `evolution_policy.ONLINE_EVOLUTION_DSL_GUIDANCE` 由同一 policy 模块持有；
guidance 同时注入 generate/evolve 模型 Prompt，避免“只有测试夹具能创建”的隐藏格式。presentation 必须保留原意且
不新增事实，只能组合短句、标题、分段、项目符号、重点和语言等固定指令；retrieval 只能组合与声明工具
严格一致的本地知识库/已确认记忆、关键词、去重、排序、来源定位、原文和无结果固定指令。任何同义改写、
新增自由文本或未声明来源都会 fail closed 到 immutable track。

保存新的 `source_markdown` 时也会比较旧、新 SemVer；同版本或倒退版本的行为替换被拒绝。每个启用并实际加载到 AgentScope 的 Skill 还会由服务端按其已验证的 ID、版本与 allowlisted tools 构建精确 `security-risk-profile-v1`：所有 Skill 都要求 schema、输出、预算、非信任数据和患者归属控制；联网 Skill 额外要求外发脱敏，证据检索 Skill 额外要求 provenance。此档案不来自 Markdown、浏览器或模型，不能由 Skill 自行放宽。

生成与修订响应还包含 `skill-draft-quality-v1` 的确定性审阅提示，覆盖输入核对、本地证据、红旗和医疗免责声明是否在草稿中出现。它不读取或回传额外用户内容，不调用第二个模型，不评估医学有效性，也不能替代双轨分类器或离线临床审核。

临床诊断、开始/停用/替换药物或调整剂量不能在无可追溯证据时被写成事实或指令。存在本轮证据时，生成器可以生成带适用条件和依据的可审阅建议；Skill 本身不能执行该动作。患者版产物只在全文末尾保留一句风险与医生复核提示，医生版直接呈现建议、条件和证据，不添加机械性拦截。

模型生成和修订的原始投影必须通过严格的
`skill-generation-model-output-v1`。缺失/旧版本、未知字段或不符合 schema
的 provider 输出会在 Markdown 序列化前受控失败，不能作为未版本化草稿进入
人工审阅。

## 维护与演进

**可安全改进。** 可提高生成/修订质量、编辑器体验、外部模型评测和临床 Skill 发布审核；生成器变化必须同步更新 `skill-generation-model-output-v1`、`skill-evolution-decision-v1`、quality case、SemVer/revision 测试和审核界面。

**不可破坏的契约。** 低风险在线演化不能改变 name、category、自由文本、工具、参数 schema、enabled
状态或权限；危险和未知变更不能通过在线响应取得候选内容，也不能自动写库、启用、执行或改变正在使用的 revision。
这里的“不能自动写库”指不能写入生产 Skill 定义；危险候选必须写入独立加密提案账本，不能被丢弃或要求
离线阶段重新生成。提案账本不提供 update/delete/activate mutator，状态推进应写入独立审核事件。
相同 ID 的行为替换必须递增 SemVer，加载前必须重新通过服务端 profile。无证据的
诊断/调药事实不得进入自动激活路径，有证据的临床建议仍进入离线审核而非在线执行。

**性能与回归验收。** 覆盖 generate→审阅保存→会话加载→低风险 evolve 在线
revision→临床/工具 evolve 加密提案及去内容化回执→幂等重放→revision 冲突→删除，以及 provider 结构输出
失败；运行 `skill-draft-case-v1`。真实模型回归要单列耗时、成功率、schema 拒绝率
与 fail-closed 分类率；10 并发 evolve 同一 Skill 只能产生一个可接受的下一 revision。
