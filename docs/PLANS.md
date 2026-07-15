# GerClaw 交付路线

> 更新：2026-07-15。最高权威为 `references/gerclaw设计要求.md`；状态以 `REQUIREMENTS_MATRIX.md` 和 exec-plan 证据为准。

## 当前阶段

生产全栈迁移进行中。0014–0020 已完成基础设施、RAG、Agent Harness 核心、Memory、Search、Skill 和 Development Harness；旧 MVP 中仍有 mock 的临床页面不计为生产完成。

## 活跃计划

| 编号 | 任务 | 目标 |
|---|---|---|
| 0021 | Runtime Permission/HITL/Tool Registry/多智能体 | ALLOW/DENY/ASK、可恢复审批、工具边界、预算和复核 Trace |

## 后续顺序

| 编号 | 任务 | 主要验收 |
|---|---|---|
| 0021 | Runtime Permission/HITL/Tool Registry/多智能体 | ALLOW/DENY/ASK、可恢复审批、工具 allowlist、复核 Trace |
| 0022 | Voice/Privacy/Document | 真实 ASR/TTS、统一隐私策略、MinerU 上传/URL/轮询/会话绑定 |
| 0023 | CGA/风险预警/慢病管理/情感陪伴 | 量表计分、风险事件闭环、慢病计划与趋势、安全陪伴和危机升级 |
| 0024 | 五大处方与用药审查 | 模板 JSON、四重校验、DDI/Beers/剂量/重复、审批与导出 |
| 0025 | 账号/RBAC/患者授权 | 注册登录、刷新退出、角色固定、资源授权、加密临床数据 |
| 0026 | Feedback/Eval/Bad Case/性能 | 反馈闭环、eval 回放、10 并发、指标与性能报告 |
| 0027 | 前端全接入与无障碍 | 清除 mock、四断点、患者/医生核心 E2E、全站适老化 |
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
