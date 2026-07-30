# Context Snapshot

This package owns the versioned, immutable `AgentContext`, bounded conversation-history
models, `ProductionContextSnapshotAssembler`, encrypted persistence contracts, and uploaded
input projector. The composition entry consumes the assembler through `HarnessComponents`;
`ProductionAgentHarness`, `ChatService`, and `RunResumeService` are the consumers.

Validation forbids unknown fields and caps every collection/text field. A validation failure
stops the turn before model construction.

`PersistedContextSnapshot` v2 freezes the model-visible history, Profile projection and version,
Memory references, session summary, ClinicalState, exact validated Skill definitions, and
already parsed owner-scoped documents. `PersistedRunPlan` freezes route, dynamic DAG,
SAVI/C3 decision, selected capabilities and reusable results, workflow policy, Harness config,
execution budget, attachments, and regeneration identity. `FrozenRunState` cross-validates
both contracts.

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

## 容量预判与压缩实现

`ContextWindowManager` 在模型调用前统一估算 `system/tools + current input + Profile +
ClinicalState + Skills + documents + capability results + plan + images + evidence reserve +
history + summary + output reserve`。达到 `context_trigger_ratio` 前就为历史分配预算，
并额外遵守 `memory_context_budget_ratio` 上限。固定输入本身超窗时返回稳定错误，不通过
删除临床状态、文档片段或证据门禁“凑空间”。无 Provider tokenizer 的预检按 UTF-8
三字节上界估算中文 Token，并由 trigger/target 间的保留区吸收模型 tokenizer 差异。
Emergency 在首次模型调用前走确定性短路，不产生模型副作用；它仍记录完整 content-free
inventory，但即使超出模型窗口也不能阻断 120/急诊提示。

历史超额时优先调用 AgentScope `ContextConfig` 的结构化医疗摘要：最近最多六条消息保留
原文，摘要要求保留过敏、当前/停用药物及剂量、生命体征与时间、红旗和待确认项。压缩
Provider 失败时切换 `deterministic-extractive-v1`：只摘录历史原句，用户临床关键句优先，
历史助手句标为待核验，不生成新医学事实。加密 `sessions.context_summary` 保存
`source_hash` 和严格校验的 projection；完全相同的来源和预算直接复用，不再次调用模型。
若结构化摘要与保留轮次仍超过动态 history budget，会再执行同预算的确定性摘录；最终
projection 仍超过 trigger 时 fail closed。
`context-projection-v1` 只保存 content-free Token 清单、压缩策略、原始/保留消息数和
before/after 估算，并随 Run 冻结。

执行失败时，摘要、Memory 候选、assistant message 和成功终态处于同一事务；失败路径先
rollback，再单独持久化失败 Trace/Run，旧 worker 仍受 fencing 阻断。服务/worker 丢失形成
`interrupted`，恢复先公开“已恢复执行”，再使用同一快照继续；用户主动点击停止形成
`cancelled` 真终态，不把可能不完整的流式文本当作可恢复答案。用户若想继续，应发起新 Run。

Known limit: the snapshot freezes inputs and completed owner-capability results, but the
current executor does not yet persist every AgentScope tool-call checkpoint. A resumed
unfinished model/tool node may execute again behind existing idempotency and fencing
boundaries. Node-level checkpoint continuation remains a Run Lifecycle responsibility.

Measure improvement with byte-stable serialized snapshots across resume, zero mutable
context fetches on the resume path, bounded input, no cross-actor references, uninterrupted
Run/Event identity, and recovery integration tests. Acceptance requires context, Harness,
Chat, Run Resume, and real PostgreSQL/Redis recovery tests to pass.
