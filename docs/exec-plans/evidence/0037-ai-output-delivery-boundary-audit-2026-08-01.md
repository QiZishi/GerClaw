# GerClaw AI 输出交付边界审计

日期：2026-08-01

范围：生产代码 `apps/api/src`、`apps/mvp/src`，以及 Docker 启动链路。现有测试文件、测试脚本和测试断言未作为验证手段；本审计采用源码索引、生产构建、运行日志和 GUI 实测计划。

## 结论

系统此前不是单一模型故障，而是“模型输出已经存在，但被输入边界、流式医学后处理、引用合同重试、记忆增强异常和前端终态合同共同影响”的组合问题。最直接的可用性问题是：

1. 聊天文本在浏览器输入、`ChatRequest`、`AgentRequest` 三处受 4,000 字约束，且语音识别结果再次被截断。
2. `SafeSentenceBuffer` 和 `project_agent_stream` 把“当前句没有本轮证据”传给 `sanitize_medical_text`，触发确定性医学表述改写；这不是引用展示，而是模型正文被改变。
3. 输出合同修复提示曾把 `[E]/[W]` 引用标记写成医学事实的必需条件；重复失败路径还会删除未绑定引用的临床句子。
4. Memory 检索异常在模型文本已经产生后仍被 `raise_if_failed()` 当作终态失败，导致本来可以交付的回答没有 `done`。
5. 音色曾被作为环境变量、账号字段、请求字段和 provider payload 配置；这会让一个本不需要用户选择的音色设置阻断语音模块启动或 TTS 请求。
6. 生成预算、终态 DTO、持久化模型和前端 schema 之间曾复制 131,072 字上限；安全提示在模型正文之后追加时，正好达到模型上限的回答可能再次被终态校验拒绝。
7. RAG、Memory 检索和 Memory 抽取还保留 4,000 字硬失败；这些是从用户问题派生的正常查询，可能在模型正文生成前就中断增强链路。
8. RAG/Search 路由、AgentScope 搜索工具、语音 DTO 和外部隐私投影还复制 4,000 字或 100,000 字限制；长的正常问题或长回答会在检索、TTS 或模型请求前被拒绝。

修复原则是删除上述影响正常内容交付的边界，不添加针对问题样例的规则。会话归属、租户/用户权限、数据库 fencing、SSE 事件完整性、私有工具协议剥离、紧急风险短路和医疗免责声明仍然保留，因为它们是交付安全边界，不是医学引用强制条件。

## 研究依据

公开的生产实践与本项目现象一致：

- OpenAI Responses streaming contract 将生成过程拆成事件流，并明确区分 `response.output_text.delta`、完成状态、错误和 incomplete reason；客户端必须等待终态并处理错误，而不能把任意中间片段当作最终结果。[OpenAI Responses streaming API](https://platform.openai.com/docs/api-reference/responses-streaming/response/incomplete?lang=node.js)
- OpenAI Agents SDK 把 output guardrail 放在最终 agent output 上，触发 tripwire 会抛异常；这类检查如果把“可用文本”直接等同于“必须完全通过所有附加规则”，就会形成模型成功、应用失败的交付断点。[OpenAI Agents SDK Guardrails](https://openai.github.io/openai-agents-js/guides/guardrails/)
- OpenAI Agents SDK 的运行文档把结构化输出失败、工具错误、max-turns、guardrail tripwire 分开处理，并提供 validated fallback；说明恢复策略应区分“无效结构字段”和“已经可读的正文”，不能把所有失败统一转换成空输出。[OpenAI Agents SDK Running Agents](https://openai.github.io/openai-agents-js/guides/running-agents/)
- Google Checks Guardrails 文档提醒：对流式不完整片段做判断会因为上下文不足产生 false positive；应积累足够上下文后再评估。这个风险对应本项目逐句流式改写造成的误判。[Google Checks Guardrails](https://developers.google.com/checks/guide/ai-safety/guardrails?hl=en)

## 源码链路审计

### 1. 页面提交与输入链

链路为：

`ChatInput` → `useComposerVoice` → `streamAgentChat` → `ChatRequest` → `ChatService.process` → `ProductionInputOutputModule.normalize` → `ProductionAgentHarness.process_message`。

审计到的正常内容损失点：

- `apps/mvp/src/components/chat/ChatInput.tsx` 原先在 `handleInput` 中 `slice(0, INPUT_LIMITS.maxMessageLength)`。
- `apps/mvp/src/components/chat/composer/useComposerVoice.ts` 原先把 ASR 文本拼接后再次 slice。
- `apps/mvp/src/lib/constants.ts` 把聊天正文与附件限制放在同一个对象中，容易把正文限制误认为产品合同。
- `apps/api/src/gerclaw_api/domain/chat_schemas.py` 的 `ChatRequest.message` 同时有 `min_length=1,max_length=4000`，并在进入服务前 strip/拒绝空白。
- `apps/api/src/gerclaw_api/modules/contracts.py` 的 `AgentRequest.text` 又复制了 4,000 字约束。
- `apps/api/src/gerclaw_api/modules/input_output/module.py` 曾拒绝控制字符，且 voice render 还把已经生成的回答截到 4,000 字。

处理结果：删除聊天正文的前端截断、ASR 截断、ChatRequest/AgentRequest 正文长度边界和控制字符拒绝；保留 Unicode/换行规范化、附件引用唯一性、文件大小、请求体和会话权限等资源与安全边界。voice render 不再截断已生成正文。没有写入 `TTS_VOICE` 配置。

另外，所有公共正文 DTO、消息持久化、恢复快照和 Web SSE schema 统一使用 132,000 字上限，为模型 131,072 字生成预算预留安全提示空间；这不是对普通用户输入增加拦截，`ChatRequest.message` 仍不设正文长度校验。RAG 查询、Memory 长期检索查询和 Memory 抽取输入也改为只检查是否有文本，不再按 4,000 字拒绝；RAG/Search 路由、AgentScope 搜索工具和语音 DTO 同样统一到公共容量。外部搜索、TTS 和模型 prompt 的隐私投影不再用更小的 4,000/100,000 字硬失败；若外部服务因自身上下文能力失败，按对应增强模块的降级路径处理，不把该失败升级为已生成正文的终态失败。

### 2. 医学识别、证据和正文后处理

`apps/api/src/gerclaw_api/modules/agent_harness/safety.py` 将医学识别、紧急风险、免责声明和确定性诊断措辞分开。引用绑定在 `evidence/turn_binding.py` 和 `evidence/markers.py` 完成，终态合同 `run_lifecycle/terminal_contract.py` 已明确“不把引用覆盖率当作 hard gate”。这部分设计本身允许无引用回答，但流式调用仍把 `citation_scope.segment_has_evidence` 传进句子缓冲，形成了实现与合同不一致。

处理结果：

- `SafeSentenceBuffer` 不再接收 evidence validator；它只保留句子边界和医疗安全措辞处理。
- `project_agent_stream` 不再用 evidence validator 重写 retained model text。
- `sanitize_medical_text` 删除了已废弃的 claim-level validator 参数和分支。
- 保留重复免责声明清理和确定性诊断措辞的安全改写；引用展示仍是“有则绑定、无则为空”，不再决定回答是否交付。

### 3. 重试、修复和删除路径

`run_lifecycle/output_repair.py` 对 provider partial stream、tool input schema、answer schema 和显式列表格式做有限重试，这是修复协议损坏所需的边界。但 `orchestration_support.py` 的 answer schema repair 指令曾强制要求医学句子使用 `[E]/[W]`；`UnboundClinicalClaimsError` 与 `prune_unbound_clinical_claims` 还可能在重复失败时删除临床句子。

处理结果：

- 删除 schema repair 中“医学事实必须有引用”的指令。
- 删除引用缺失异常的分类和专用 repair instruction。
- 删除重复失败时按临床句子删除的旧路径；重复验证失败时保留已生成正文，并只继续做已声明的 public citation marker 规范化。
- 保留私有 tool markup 拦截、事件 schema 校验和真正的 provider partial stream 重试，因为这些内容若直接进入页面会破坏协议或泄漏内部控制语法。

### 4. Memory、持久化与终态交付

`agent_stream.py` 在模型流结束后会检查 Memory adapter；`GerClawMem0Client` 原先把 Memory provider/database 异常与 owner boundary 异常都放进 `_fatal_error`，从而在回答已经生成后抛出异常。另一方面，ChatService 在 assistant、Trace、Run journal 原子提交后才发 `done`，这是可恢复会话与前端终态一致性要求，不能简单绕过。

处理结果：

- Memory 检索/数据库故障改为 `MEMORY_SEARCH_FAILED` warning，继续交付正文。
- 用户/租户边界不匹配仍然抛错，避免跨用户记忆泄漏。
- Memory 写入失败继续作为 `MEMORY_WRITE_FAILED` warning。
- `done` 仍只在会话、Trace 和 Run journal 成功提交后发送；若数据库本身不可用，这是基础设施不可交付故障，不通过删除一致性边界来伪造成功。

### 5. 前端 SSE 终态

`apps/mvp/src/services/gerclaw/chat.ts` 严格解析 `text_delta` 和 `done`，校验 durable cursor、run metadata、safety 和 references。`useAgentConversationStream.ts` 在 `done` 时用服务器 `full_text` 覆盖流式草稿，在 error 时将草稿变成错误状态。

这里的主要风险不是普通医学正文被引用过滤，而是后端若在 `done` 前抛错，前端必然把已显示的临时片段转换为失败状态。后端修复“模型文本存在但终态被后处理/增强异常吞掉”后，严格终态合同仍保留，以避免页面显示不可恢复的半条回答。

### 6. 输出容量一致性

模型生成预算由 `agent_max_output_characters` 控制为 131,072；终态文本还可能包含医疗免责声明和高风险提示。此前多个后端 DTO、数据库内容模型和前端 Zod schema 各自复制同一个 131,072 边界，导致合法的“模型正文 + 安全提示”可能在生成之后被拒绝。

处理结果：公共文本容量集中到 `MAX_PUBLIC_TEXT_CHARACTERS = 132_000`，后端持久化、恢复、流式终态、路由快照和 Web schema 均引用或同步该容量；模型本身的生成预算不扩大，避免把资源控制误改为无界输出。

已删除 `TTS_VOICE`/`tts_voice` 的环境配置、账号配置、设置页面字段和 TTS 请求字段；provider payload 也不再发送 `voice`，直接使用 provider 默认音色，不写入任何音色配置。

## 已修改文件

- `apps/api/src/gerclaw_api/domain/chat_schemas.py`
- `apps/api/src/gerclaw_api/modules/contracts.py`
- `apps/api/src/gerclaw_api/modules/input_output/module.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/safety.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/streaming.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/protocols.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/agent_stream.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/terminal_contract.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/run_lifecycle/__init__.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/evidence/markers.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/evidence/__init__.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/orchestration_support.py`
- `apps/api/src/gerclaw_api/modules/agent_harness/orchestrator.py`
- `apps/api/src/gerclaw_api/modules/memory/agentscope_adapter.py`
- `apps/api/src/gerclaw_api/services/chat_service.py`
- `apps/api/src/gerclaw_api/modules/voice/module.py`
- `apps/api/src/gerclaw_api/modules/voice/models.py`
- `apps/api/src/gerclaw_api/modules/rag/module.py`
- `apps/api/src/gerclaw_api/api/routes/rag.py`
- `apps/api/src/gerclaw_api/api/routes/search.py`

## 2026-08-02 交付失败链路复核与修正

上一轮修复后仍可能出现“这次回答没有完整生成，请重试”的共性路径，实际根因不是模型没有返回文本，而是以下后处理/交付边界把可读正文升级成了失败：

1. `run_lifecycle/agent_stream.py` 在模型流结束后把 AgentScope retained state 与已发送增量做逐字符比较；引用规范化、医疗措辞安全处理或空白差异都会进入 `agent_state_stream_mismatch` 并抛出 `AgentHarnessError`。该异常发生在 `done` 之前，前端只能收到重试提示。
2. `run_lifecycle/output_repair.py` 用私有 events 缓冲整轮回答，只有最终校验成功后才发布；因此任何终态校验的偶发差异都会让前端完全看不到已经生成的步骤和正文，也不符合流式交付要求。
3. `evidence/markers.py` 对越界的公共 `[C#]` 标记直接抛出 `CitationMarkerValidationError`。引用不是回答的必需条件，旧标记不能使正文失败。
4. `apps/mvp/src/services/gerclaw/chat.ts` 对非核心辅助 SSE 事件采用严格 schema；单个 thinking/tool 元数据异常会中断整条正文流。未知辅助事件也会被当成协议失败。
5. `useAgentConversationStream.ts` 在已收到正文后把 transport/runtime 错误追加到正文末尾，用户会看到一份可读答案加一条“没有完整生成”，从而被误判为整轮失败。

本次修正将规则收敛为：私有工具协议仍不得进入公共文本；终态 `done`、权限归属、数据库一致性和医疗免责声明仍保留；其余不会改变正文安全性的差异只记录诊断、删除无意义引用标记或忽略辅助事件。正文和步骤事件即时发布，`done.full_text` 负责最终收敛；前端已有正文时不再追加通用重试文案。

本次真实 GUI 验证（隔离 headless Chrome、未使用项目测试文件）：主页四个医学示例 4/4 均出现过程状态并最终展示正文、免责声明和“重新生成”，未出现重试提示；直接输入“你们这个系统是做什么的？”也返回完整系统说明并完成终态。独立 TTS 请求仍可返回 502，但未阻断聊天正文，故不计入聊天交付失败。
- `apps/api/src/gerclaw_api/modules/runtime/tool_schemas.py`
- `apps/api/src/gerclaw_api/modules/privacy_redaction/models.py`
- `apps/api/src/gerclaw_api/modules/privacy_redaction/policy.py`
- `apps/api/src/gerclaw_api/services/run_regeneration_service.py`
- `apps/api/src/gerclaw_api/services/account_model_configuration.py`
- `apps/api/src/gerclaw_api/modules/input_output/README.md`
- `apps/api/src/gerclaw_api/modules/memory/memory_module.py`
- `apps/api/src/gerclaw_api/modules/memory/extractor.py`
- `apps/mvp/src/lib/constants.ts`
- `apps/mvp/src/components/chat/ChatInput.tsx`
- `apps/mvp/src/components/chat/composer/useComposerVoice.ts`
- `apps/mvp/src/components/settings/ModelConfigurationPanel.tsx`
- `apps/mvp/src/services/model-configuration.ts`
- `apps/api/src/gerclaw_api/api/routes/auth.py`
- `apps/api/src/gerclaw_api/api/routes/chat.py`
- `apps/api/src/gerclaw_api/api/routes/voice.py`
- `apps/mvp/src/app/api/account/model-configuration/route.ts`
- `apps/mvp/src/app/api/mineru/parse/route.ts`
- `apps/mvp/src/components/settings/SettingsPanel.tsx`
- `apps/mvp/src/components/layout/sidebar/SidebarAccountMenu.tsx`
- `apps/mvp/src/components/layout/sidebar/useSidebarAccountController.ts`
- `apps/mvp/src/server/gerclaw-access.ts`

### 7. 访客工作台与登录边界

此前访客 scope、BFF proxy 和前端导航同时把 Skill、医生工作台和模型服务配置当作账号专属，造成“访客能进入页面但功能不可用”的交付断点。处理结果：

- `_guest_scopes()` 允许完整的自有产品 scope，包含 Skill discovery/mutation/execution、CGA、五大处方、文件、语音、检索、Memory 和 Trace/反馈；不授予跨患者访问、患者授权、管理员或临床审批决策。
- BFF 对访客开放自有 GerClaw proxy target；`access-grants` 仍保持账号授权边界。
- 侧栏、Skill 工作台、Composer 技能选择器对访客可见；访客菜单可在患者端/医生端切换，账号仍固定在服务端角色端。
- 模型/外部服务配置按当前 `tenant_id + actor_id` 保存，账号和访客均可读取、保存并让新对话生效；MinerU 和 voice override 不再要求持久账号。
- 这些改动没有增加用户问题拦截规则，角色切换只改变工作台状态，不把访客身份伪装成医生账号，也不放宽跨患者数据授权。

## 验证要求

本报告不以仓库现有测试文件作为证据。代码修改后必须：

1. 重新构建 API/Web 并检查容器健康状态。
2. 连接真实 GUI；从页面输入问题，读取页面最终消息，而不是只看 SSE 或 API 返回。
3. 按通用问答、医学咨询、用药/风险、附件/检索、CGA/五大处方、陪伴/语音等功能类别分别进行 10 个不同角度提问。
4. 对每个失败记录：用户问题、页面显示、最后一个成功阶段、错误码/日志原因和修复归属；没有失败时明确记录完成终态。

## GUI 实测状态

本轮使用 Playwright 启动独立 headless Chromium shell：

`/private/tmp/gerclaw-playwright-browsers/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell`

没有连接或修改用户的 Chrome/Edge，也没有运行仓库现有测试文件。每条成功记录均以“页面出现完整回答、医疗免责声明、生成终态控件/终态卡片且停止按钮消失”为准；观察后端返回本身不计为成功。

| 功能类别 | GUI 提问数 | 页面最终交付 | 流式过程 | 说明 |
|---|---:|---:|---:|---|
| 通用问答 | 10 | 10/10 | 已验证 | 页面最终回答完整 |
| 症状/医学咨询 | 10 | 10/10 | 已验证 | 一条观察器先超时，随后页面完整收束，未计失败 |
| 用药风险 | 10 | 10/10 | 已验证 | 页面有正文、免责声明和终态控件 |
| 急症风险 | 10 | 10/10 | 已验证 | 高风险问题显示就医警示或完整安全回答 |
| 附件/检索 | 10 | 10/10 | 已验证 | 包含真实文件上传；一条观察窗口超时后页面已完整收束 |
| CGA/五大处方 | 10 | 10/10 | 已验证 | 每条都观察到过程标记和最终页面答案 |
| 陪伴/心理支持 | 10 | 10/10 | 已验证 | 页面最终正文、免责声明和终态控件完整 |
| 语音朗读/输入 | TTS 1 次；ASR 2 次 | TTS 1/1；ASR 0/2 | 录音界面可进入 | TTS 默认音色路径正常；ASR 受隔离浏览器设备/无有效语音样本限制，页面给出重试提示 |

访客身份和功能入口的 GUI 证据：

- 无账号进入患者端后，用户菜单显示“切换到医生端”；切换后页面显示“医生工作台”，再次切换回患者端后显示“患者模式”。
- 访客医生端真实打开“临床技能工作台”，显示 4 个可用技能；点击“加载到对话”后显示“1 个已加载”。
- 访客患者端打开 Composer 技能选择器，显示 `0/10`，选择“健康宣教”后显示 `1/10` 和“移除”；随后发送医学问题，页面按“正在分析/医学检索/完成”逐步渲染最终答案。
- 访客设置页可打开“模型配置”；真实执行空配置保存，页面显示“模型配置已安全保存”，没有 `AUTH_REQUIRED`、`ACCOUNT_REQUIRED` 或“请登录”。
- TTS 真实点击“朗读”入口后页面无“音色必填”或服务错误，使用 provider 默认音色路径。

真实失败/限制记录：

1. 一次从技能工作台点击“开始咨询”的 Playwright 观察调用超过等待窗口，内核重置；重新进入后技能工作台和对话均正常。原因是导航观察调用超时，不是页面输出失败。
2. 陪伴类两条短回答没有被观察器捕获到“停止”按钮，但页面已经显示完整正文、免责声明和“重新生成/朗读/分享/更多”终态控件；原因是生成结束快于轮询采样，已按页面终态判定成功。
3. 普通 headless Chromium 的真实麦克风能力返回 `Not supported`；使用 Playwright fake media stream 后可以进入录音状态，但停止后 ASR 显示“语音识别失败，请重试”。原因是 fake 设备没有可识别的有效语音，页面按预期给出可重试提示；这不是登录、音色或文本输出边界，不能据此虚构语音识别成功。

因此，本轮可交付的文本/流式/技能/访客角色/配置/朗读路径均以页面终态完成；仅真实音频输入受隔离 headless 设备与无有效语音样本限制，失败原因已记录，未修改业务规则绕过该限制。
