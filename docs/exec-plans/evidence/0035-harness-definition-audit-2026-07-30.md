# Harness 核心定义与偏离审计（2026-07-30）

审计方式：由独立子智能体只读检查生产代码、权威设计文档和阶段计划，并联网核对官方文档/论文；不使用
Claude，不修改代码。审计完成时 Context V2 尚在工作区，随后已由
`a080dd1a feat(context): preserve high-value compaction lineage` 正式提交。

## 结论

没有发现 Harness 组件因安全治理而丧失核心定义的 P0 问题。Memory 在线 CRUD、Skill 在线可变性、
RAG/Evidence 真实检索与引用、ClinicalState 事实/未知/冲突分离、确定性 Routing 和 Run 状态机仍然成立。
当前 P1 集中在尚未实现完整的执行连续性，而不是已有组件被“改废”：

1. 缺少逐 `PlanNode` 持久化 checkpoint，resume 仍可能重跑整个 answer attempt。
2. `interrupt_and_steer` / `queue_for_next_boundary` 尚无持久化指令账本和 exactly-once 消费。
3. 完整 Context inventory/preflight 目前覆盖 Turn 首次模型边界，尚未覆盖每次 ReAct 模型调用和大型工具边界。
4. PlanNode repair/fallback 和 Chat `completed_with_warnings` 生产路径尚不完整。

## 定义、实现与判断

| 组件 | 不可改变的核心机制 | 当前判断 | 权威参考 |
| --- | --- | --- | --- |
| Routing | 模型前按意图、风险和能力确定路径；Emergency 早于模型短路 | 符合；Quick/Standard/Deep/Emergency 为确定性决策 | [OpenAI Agents orchestration](https://openai.github.io/openai-agents-python/multi_agent/) |
| Planning | 目标分解为依赖、预算、fallback 明确的可执行节点 | DAG/预算真实；逐节点持久化不足 | [OpenAI running agents](https://openai.github.io/openai-agents-python/running_agents/) |
| Context | 区分应用上下文与模型上下文；压缩可压缩历史并保留当前目标和关键状态 | v2 双阈值/lineage 已提交；逐执行边界 preflight 待补 | [OpenAI context](https://openai.github.io/openai-agents-python/context/)、[OpenAI sessions](https://openai.github.io/openai-agents-python/sessions/)、[AgentScope task memory](https://doc.agentscope.io/tutorial/task_memory.html) |
| Run Lifecycle | 状态机、事件 replay、幂等取消、checkpoint resume 和 fencing | 状态/replay/fencing 符合；节点级 resume 不完整 | [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) |
| ClinicalState | 事实、未知、冲突、确认状态和 provenance 分离；推测不能成为 confirmed | 符合；Reducer 只接收用户或可信工具来源 | [FHIR Provenance](https://hl7.org/fhir/provenance.html)、[FHIR Observation](https://hl7.org/fhir/R4/observation.html) |
| Evidence | 引用绑定实际采用的陈述、locator、来源和适用范围 | 符合；阈值、去重、adopted text、claim binding 均存在 | [Attributed QA](https://aclanthology.org/2024.acl-long.182/) |
| RAG | 检索真实外部知识并把真实结果交给生成；失败不得伪造引用 | 符合；hybrid/RRF/rerank，reranker 失败回到真实候选 | [RAG](https://arxiv.org/abs/2005.11401) |
| Memory | 随用户使用进行有作用域的存储、检索、更新、删除和压缩 | 符合；在线 CRUD/revision/tombstone/conflict/restore 均存在 | [MemGPT](https://arxiv.org/abs/2310.08560)、[Generative Agents](https://arxiv.org/abs/2304.03442) |
| Skill | 可发现、装载、执行、注册、更新、删除的能力包 | 符合；在线人工 CRUD 和低风险窄 DSL 演化保留 | [AgentScope Agent Skill](https://doc.agentscope.io/tutorial/task_agent_skill.html) |
| Plugin Runtime | 能力清单、schema、权限、选择和调用；不得复制/绕过能力所有者 | 边界正确；当前是固定 GerClaw 能力适配层，不是任意第三方平台 | [AgentScope tools](https://doc.agentscope.io/tutorial/task_tool.html)、[OpenAI MCP](https://openai.github.io/openai-agents-python/mcp/) |
| Evolution | 在线收集可审计信号；危险控制面只经隔离评测和审批晋升 | 边界正确；通用 Memory/Skill/Planning/Prompt runner 仍待扩展 | [GEPA](https://arxiv.org/abs/2507.19457)、[A-Evolve](https://arxiv.org/abs/2605.30621)、[Adaptive Auto-Harness](https://arxiv.org/abs/2606.01770) |
| Harness facade | 组合路由、计划、上下文、工具和生命周期，不复制底层实现 | Protocol/DI 和小 facade 符合；orchestrator 规模仍偏大 | 项目分层与组件宪章 |

## 必须长期保留的反退化门禁

- Memory：继续允许在线 create/update/delete/restore/压缩/作用域召回；不可变的是语义、权限和 provenance，
  不是记忆内容。
- Skill：继续允许人工 CRUD、执行和低风险在线演化；医疗决策、权限、外部副作用和安全门变更进入离线审核。
- ClinicalState：unknown 不得变 negative，conflict 不得被覆盖，模型推测不得升级为 confirmed。
- Evidence/RAG：检索降级不得生成伪引用，无 locator/adopted text 的证据不得伪装成已采用。
- Context：任何压缩不得删除当前要求、红旗、unknown/conflict、用药/过敏和来源；无法压缩时使用确定性摘录。
- Run：attempt 未验证前不得进入 SSE/replay/Memory/Context/Artifact；旧 fence 不得写 checkpoint 或终态。
- Evolution：平均提升不得抵消任一组件核心 invariant 或高风险单病例退化。

## 只读验证记录

- Harness/ClinicalState/Run/Resume/Evidence/Plugin/Evolution/Memory 合同：63 passed，2 skipped。
- Memory/Skill/Runtime/RAG：209 passed。
- Model Router/Run Event/Cancellation/AgentRun：47 passed。
- 合计：319 passed，2 skipped；另有 1 个本地 Qdrant payload index warning。
- 首次定向测试因全局 coverage 统计只有 40.49% 而退出，测试断言本身通过；随后按模块规范使用
  `--no-cov` 完成行为验证，未把定向 coverage 误报为全局通过。
