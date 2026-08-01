# Context Snapshot

This package owns the versioned, immutable `AgentContext`, bounded conversation-history
models, `ProductionContextSnapshotAssembler`, encrypted persistence contracts, and uploaded
input projector. The composition entry consumes the assembler through `HarnessComponents`;
`ProductionAgentHarness`, `ChatService`, and `RunResumeService` are the consumers.
`build_agent_state_context` assembles the already validated history, clinical projection,
uploaded-document projection and admitted evidence into AgentScope messages while preserving
their trust delimiters and established high-value ordering; it does not fetch or mutate them.

Validation forbids unknown fields and caps every collection/text field. A validation failure
stops the turn before model construction.

`PersistedContextSnapshot` v2 freezes the model-visible history, Profile projection and version,
Memory references, session summary, ClinicalState, exact validated Skill definitions, and
already parsed owner-scoped documents. `PersistedRunPlan` freezes route, dynamic DAG,
SAVI/C3 decision, selected capabilities and reusable results, workflow policy, Harness config,
execution budget, attachments, and regeneration identity. `FrozenRunState` cross-validates
both contracts.

上传图片按当前用户任务中性投影。只有当前请求涉及医疗内容时，图片才作为病例、检查、
用药或生活信息证据；计算、文字提取和一般图像识读不得被产品定位强行改写成医疗任务，
也不得额外生成医疗范围说明或免责声明。

New turns assemble these contracts once and save them in the encrypted
`AgentRun.context_snapshot` and `AgentRun.plan` columns. Explicit resume reconstructs the
request from the owner-scoped Message and Trace, validates tenant/actor/session/trace/input
identity, restores images from encrypted Trace artifacts with SHA-256 checks, and then passes
the frozen state to Chat. Chat does not create another user Message or reload mutable
history/Profile/Memory/Skill/document inputs.

Failure semantics:

- Unknown fields, unsupported schema versions, count/identifier drift, corrupt fingerprints,
  cross-actor identity, or route/plan mismatch fail closed as invalid resume material.
- Legacy interrupted Runs without `context-snapshot-v2`/`run-plan-v1` are intentionally not
  reconstructed from current mutable state.
- Authorization and service availability are checked at resume time; the snapshot never
  grants permissions.

## Context lifecycle

| 环节 | 继续传递的内容 | 明确不传递 |
| --- | --- | --- |
| 路由/红旗 | 当前输入、附件 Kind/数量、医疗风险代码、可用能力 ID | 历史全文、Provider payload、模型推理 |
| 临床决策/计划 | `ClinicalState` 的事实/未知/冲突/provenance、SAVI/C3、预算、DAG 和已完成能力引用 | 模型猜测、未确认 Memory |
| 模型调用 | 固定安全前缀、工具合同、当前输入、Profile/Memory 低权限投影、冻结 Skill、解析文档、临床状态、计划、证据，以及压缩后的当前有效历史 | 被替换回答、跨主体内容、原始凭据、private chain-of-thought |
| 工具节点 | 当前 Run identity、严格 input schema、该节点依赖结果和最小所需上下文 | 整个会话、其他节点私有结果 |
| 终态 | 当前答案版本、逐主张 Evidence、公开 warning、Artifact/Trace 引用和 content-free 投影清单 | 原始工具/Provider 载荷 |
| Resume | 同一 v2 Snapshot、Run Plan、原 Trace/输入、已冻结版本和已完成结果；另行重验当前授权 | 当前可变历史、Memory、Skill、Profile 或文档替换值 |
| Controlled successor | 原 Run 已冻结的历史、Profile/Memory 投影、Skill 定义、文档、配置和已完成能力结果；新指令重新计算 Routing、ClinicalState、SAVI/C3 与 DAG，并使用新 execution identity | 原 Run 未提交 attempt、当前可变 Memory/Skill、旧 route/plan、旧输入正文 |

## 容量预判与压缩实现

OpenAI 公开说明确认 Codex 会在 Token 超过阈值后自动 compaction，并用较小、具有代表性的
items 继续执行；公开资料还明确说明后续上下文由 compaction item 与早期窗口的高价值部分组成。
GerClaw 只借鉴这两个公开语义，不复制未公开阈值、Prompt 或调度算法：
[Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)、
[Equipping the Responses API with a computer environment](https://openai.com/index/equip-responses-api-computer-environment/)。

`ContextWindowManager` 在模型调用前统一估算 `system/tools + current input + Profile +
ClinicalState + Skills + documents + capability results + plan + images + evidence reserve +
history + summary + output reserve`。`context_trigger_ratio` 是提前压缩的 soft trigger，
`context_hard_stop_ratio` 是固定输入不可再缩时的 hard stop，配置必须满足
`reserve < soft < hard < 1`；不使用 Codex 的私有比例。达到 soft trigger 前就为历史分配预算，
并额外遵守 `memory_context_budget_ratio` 上限。固定输入本身超窗时返回稳定错误，不通过
删除临床状态、文档片段或证据门禁“凑空间”。无 Provider tokenizer 的预检按 UTF-8
三字节上界估算中文 Token，并由 trigger/target 间的保留区吸收模型 tokenizer 差异。
Emergency 在首次模型调用前走确定性短路，不产生模型副作用；它仍记录完整 content-free
inventory，但即使超出模型窗口也不能阻断 120/急诊提示。

历史超额时优先调用 AgentScope `ContextConfig` 的结构化医疗摘要：最近最多六条消息保留
原文，摘要要求保留过敏、当前/停用药物及剂量、生命体征与时间、红旗和待确认项。压缩
Provider 失败时切换 `deterministic-extractive-v1`：只摘录历史原句，用户临床关键句优先，
用户明确目标、禁止项和验收要求与过敏/用药/红旗具有同级高价值优先级；历史助手句标为待核验，
不生成新医学事实。结构化压缩抛错、超时或结果仍超预算时自动使用 deterministic fallback，
不会把一次可修复的压缩失败升级成整轮失败。加密 `sessions.context_summary` 保存
`source_hash` 和严格校验的 projection；完全相同的来源和预算直接复用，不再次调用模型。
若结构化摘要与保留轮次仍超过动态 history budget，会再执行同预算的确定性摘录；最终
projection 仍超过有效上限时才 fail closed。
新 Run 使用 `context-projection-v2`，保存 content-free soft/hard/有效上限、Token 清单、
压缩策略、源消息范围、稳定 source/retained/omitted IDs、摘要 hash 谱系、unknown/conflict
不透明 ID 和 before/after 估算，并随 Run 冻结。v1 仍可解析，保证已中断旧 Run 不因合同升级
丢失恢复能力。

ReAct 执行期间，每个 model 副作用和每个 AgentScope tool batch 副作用前还会生成
`ContextBoundaryDraft`。AgentScope 的自动压缩发生在公开 `ModelCallStartEvent` 之前，因此
生产编排直接在请求级 Agent 的 `compress_context` 入口安装边界，而不再把公开事件误当作
压缩前门禁。hard preflight 优先调用固定 AgentScope 版本的实际 `_prepare_model_input()` 和
model token counter，计入动态 system prompt、summary、全部 Text/Hint/Thinking/ToolCall/
ToolResult/Data block 及当前 tool schema；counter/formatter 不可用时退回同一 prepared input
的完整本地投影，不会因计数器故障阻断正常回答。它将实际 AgentScope state 的 before/after
Token 估算、message/summary
唯一稳定 ID、omitted/retained
集合、required input hash、压缩失败状态和上下文 hash 写入私有
`agent_run_context_boundaries`。写入必须持有当前 Run fencing token，按 Run row lock 分配
sequence，并用 `previous_projection_hash` 形成链；该表使用加密 JSON，且不进入公开
Run/Event/SSE。一个 concurrency-safe 工具批次先合并全部 name、arguments 和 result
reserve，完成一次原子 soft compaction 与 hard preflight 后才允许任何成员进入 Runtime。
Runtime 仍逐工具执行 Schema、权限和风险治理；若整批容量拒绝，Runtime 的原 owner
invocation 不会发生，AgentScope 收到同批稳定私有工具失败并从该步骤继续修复。不同工具的
临时容量 marker 不会同时写入共享 context；marker 只表示估算容量，真实 tool arguments 和
待应用 directive 不会为了压缩而复制进摘要 Provider，实际内容仍在各自验证/应用边界处理。

AgentScope 摘要失败时，运行期 fallback 由代码保护 `clinical_state`、临床决策、上传资料、
admitted evidence、Profile/Memory 投影、执行期用户指令、输出修复指令和最新用户消息，再在
剩余目标预算内从新到旧保留原文；这些高价值 Msg 在 Provider 摘要成功时也由代码移出可压缩
集合并逐对象校验后恢复，不能只依赖 Prompt/Schema。不会从空上下文重启，也不会把一次可修复
的压缩或工具容量错误升级为默认用户可见错误。结构化摘要 schema 的每个高价值字段均禁止
空串。`context_trigger_ratio` 同时满足项目 soft/hard 配置和 AgentScope
`trigger_ratio < 0.9` 合同，
防止合法项目配置在 Agent 构造时才失败。
压缩边界在调用前同时快照 `state.summary` 与 `state.context`；AgentScope shielded apply
完成后才传播取消也必须原子恢复两者，普通压缩异常同样先恢复再做 extractive fallback。
lineage 在 before projection 为每个消息对象分配 source ID，after projection 对仍保留的
对象回填原 ID；删除较早的 exact duplicate 不会再把较晚重复消息误记为被删除项。

执行失败时，摘要、Memory 候选、assistant message 和成功终态处于同一事务；失败路径先
rollback，再单独持久化失败 Trace/Run，旧 worker 仍受 fencing 阻断。服务/worker 丢失形成
`interrupted`，恢复先公开“已恢复执行”，再使用同一快照继续；用户主动点击停止形成
`cancelled` 真终态，不把可能不完整的流式文本当作可恢复答案。用户若想继续，应发起新 Run。

Known limit: private boundary rows persist content-free lineage and fencing evidence, not
decrypted AgentScope message bodies or an in-flight Provider stream. Resume still restores the
frozen v2 Snapshot/Plan and re-executes an unfinished model/tool node behind idempotency and
fencing; it does not claim exact mid-model continuation. Exact owner-tool checkpoint continuation
remains a Run Lifecycle responsibility.
运行中 `queue_for_next_boundary` 使用独立 reserve 和 exactly-once 领取；立即 steer 先让旧
Run 到达持久化 `interrupted`，再以 `ControlledSuccessorState` 建立新 Run。successor 复用上述
冻结高价值输入但重新执行当前指令的容量预检和确定性规划，不重新读取可变 Memory、Profile、Skill 或
文档；`ControlledSuccessorState` 会把 source Trace 与冻结快照显式交叉校验，数据库绑定阶段再核对
source Run、directive target 与 successor fence。成功后仍允许 Memory 按正常在线 CRUD 语义吸收
这次新交互。节点级 checkpoint 尚未完成前，
最小恢复单元仍是整个回答 attempt，不伪装成已支持工具节点内续跑。

Measure improvement with byte-stable serialized snapshots across resume, zero mutable
context fetches on the resume path, bounded input, no cross-actor references, uninterrupted
Run/Event identity, and recovery integration tests. Acceptance requires context, Harness,
Chat, Run Resume, and real PostgreSQL/Redis recovery tests to pass.
