# GerClaw 交付路线

> 更新：2026-07-15。最高权威为 `references/gerclaw设计要求.md`；状态以 `REQUIREMENTS_MATRIX.md` 和 exec-plan 证据为准。

## 当前阶段

生产全栈迁移进行中。0014–0022、0024 已交付基础设施、RAG、Runtime Agent Harness 核心、Memory、Search、Skill、Development Harness、前端真实接入与 MinerU 会话级文档信任链。当前仍不能将未审核的临床规则、前端展示角色或访客 JWT 视为真实处方、医生授权或生产 IAM。

## 活跃计划

| 编号 | 任务 | 目标 |
|---|---|---|
| 0023 | CGA 后端确定性评估闭环 | 完成已获医学依据量表的服务端状态机与患者端；Mini-Cog/MMSE 的人工审核和医生授权保持 fail closed |
| 0025 | 真实身份、RBAC 与患者授权 | 等待账号、资质、授权粒度、保留和访客迁移的产品/合规决策后实施 |
| 0026 | 反馈、Bad Case 与回归闭环 | 反馈纵切面已实现；补独立审阅、Eval 回放与统一 ≤10 并发性能报告 |
| 0029 | 五大处方与用药审查生产闭环 | 已有受限信息收集；等待医学规则、来源许可、授权和医生批准链路 |

## 后续顺序

| 编号 | 任务 | 主要验收 |
|---|---|---|
| 0023 | CGA 剩余临床审核能力 | Mini-Cog/MMSE 的图形采集、合格人工审核和医生授权；不得让患者或模型自行判分 |
| 0025 | 账号/RBAC/患者授权 | 注册登录、刷新退出、固定角色、最小范围授权与加密临床数据 |
| 0026 | Feedback/Eval/Bad Case/性能 | 独立复审、Eval 回放、10 并发、指标与性能报告 |
| 0029 | 五大处方与用药审查 | 经审核模板、确定性 DDI/Beers/剂量/重复规则、批准与导出 |
| 0028 | Docker 与最终验收 | 空卷迁移/索引/health/重启、真实外部回归、独立最终 PASS |

## 交付规则

1. 每次只执行 active 中编号最小的计划。
2. 阶段二禁止 mock 成功路径；未配置服务只能明确失败或安全降级。
3. 行为变更同步更新产品规格、架构/安全/可靠性和需求矩阵。
4. 默认只跑当前模块的必要测试；全部模块完成后执行全量回归。
5. 前端任务必须有真实浏览器审阅；医疗、安全、权限或数据任务必须有负向边界测试。
6. 独立审阅 PASS、证据回写和 conventional commit 后才能移入 completed。

## 已完成生产里程碑

| 编号 | 能力 | 结果 |
|---|---|---|
| 0014 | FastAPI/PostgreSQL/Redis/Qdrant/JWT/Trace 骨架 | 独立 PASS |
| 0015 | 本地 Agentic RAG | 436 文档真实索引与检索 |
| 0016 | AgentScope Agent Harness 与 SSE | 真实模型、工具、原子终态 |
| 0017 | Memory 与健康画像引擎 | 加密事实源、无 PHI vector、独立 PASS |
| 0018 | Search 联网医疗证据 | AnySearch→Tavily、SSRF、安全引用 |
| 0019 | Skill 注册执行与前端集成 | 真实生成/viewer/RAG/Trace、独立 PASS |
| 0020 | 生产交付基线与 Development Harness | 59 项需求矩阵、统一门禁、负向自检、独立 PASS |
| 0021 | Runtime Permission/HITL/Tool Registry 基础 | 权限决策、持久化 HITL、工具 permit、预算/checkpoint、审批 Trace，独立 PASS |
| 0022 | 前端全接入与适老化设计 | `apps/mvp` 为唯一前端、真实 BFF 接入、无障碍与浏览器回归 |
| 0024 | MinerU 文档信任链 | 真实解析、加密会话绑定、不可信上下文、撤销与取消/重试 |
