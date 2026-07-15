# GerClaw 需求→模块→验收矩阵

> 更新：2026-07-15。状态必须以代码与可复现证据为准：✅完成、🚧部分实现、❌未实现。

| ID | 需求 | 设计→实现合同/模块 | 测试→运行证据 | 状态与缺口 |
|---|---|---|---|---|
| DEV-01 | 统一开发门禁 | 根脚本、CI、docs verifier | 一条命令跑 docs/format/lint/type/test/build/security | ✅ quality modes 与 CI workflow 已实现 |
| DEV-02 | 分层测试和隔离依赖 | `apps/api/tests` | unit/integration/external/e2e；独立 DB/Redis/Qdrant | ✅ marker 与隔离 fixture 已有 |
| DEV-03 | 证据和独立审阅 | exec-plan、`output/` | 每里程碑命令、截图、审阅 PASS、commit | ✅ 0014–0019 已执行 |
| DEV-04 | 模块合同 | `modules/*` | Protocol+生产实现+README+测试 | 🚧 RAG/Memory/Search/Skill 完成；其余缺实现 |
| DEV-05 | owner/预算/checkpoint | exec-plan、runtime | owner、预算、恢复入口、独立 reviewer | 🚧 exec-plan/reviewer 有，缺运行时预算与统一 checkpoint |
| RUN-01 | AgentScope ReAct/SSE/取消 | agent_harness、chat service | 真实模型+RAG+工具+原子终态 | ✅ 0016–0019 证据 |
| RUN-02 | ALLOW/DENY/ASK 与 HITL | permission、approval | 三决策单测；ASK 可恢复审批 | ❌ 缺模块与 API |
| RUN-03 | 工具注册表和边界 | tools、harness | allowlist、schema、超时/大小/结果校验 | 🚧 RAG/Search/Skill 已接入，缺统一注册表 |
| RUN-04 | PHI-free Trace | trace repo/routes | 成功/失败/取消/工具/Skill 全事件 | 🚧 核心 Chat 已有，缺审批/临床模块/反馈 |
| RUN-05 | workflow 与多智能体复核 | harness | standard/CGA；全科→老年专科复核 | 🚧 workflow 字段已有，缺生产复核链 |
| RUN-06 | 长任务 checkpoint/replay | runtime、repositories | 重启恢复且副作用不重复 | 🚧 Trace replay/索引 generation 已有，缺统一任务 checkpoint |
| RUN-07 | 执行预算 | harness、config | token/tool/time/call/output 超限稳定失败 | 🚧 模型/迭代/输出有阈值，缺统一预算对象和成本审计 |
| AI-01 | 本地 RAG | `modules/rag` | 436 文档、39,837 chunks、混合检索/重排/引用 | ✅ 真实重建与 E2E 通过 |
| AI-02 | Memory/健康画像引擎 | `modules/memory` | 加密、跨会话、冲突、无 PHI vector | ✅ 0017 独立 PASS |
| AI-03 | Skill 生命周期 | `modules/skill`、Skill UI | 注册/版本/隔离/viewer/安全/真实模型 | ✅ 0019 独立 PASS |
| AI-04 | AnySearch→Tavily | `modules/search` | provider failover、网页隔离、引用 | ✅ 0018 独立 PASS |
| AI-05 | Voice 后端 | `modules/input_output` 或 voice | ASR/TTS schema、PCM16 流、取消、故障 | ❌ 仅前端 Next route 和 Protocol |
| AI-06 | Privacy | security、harness safety | PHI/凭证、注入、诊断、红旗、自伤、免责声明 | 🚧 核心规则分散，缺独立完整模块 |
| AI-07 | MinerU Document | document module、上传 UI | PDF/Office/MD/TXT 真实解析、轮询、重试 | ❌ Next route 仍返回 mock |
| AI-08 | Provider capability/version | services/adapters | schema/version/能力协商与不兼容拒绝 | 🚧 AgentScope 版本固定，其他 adapter 合同未统一 |
| CLN-01 | CGA 后端闭环 | cga module/API/UI | 量表、答案、确定性计分、报告、历史 | ❌ 前端本地状态，缺后端 |
| CLN-02 | 五大处方后端闭环 | prescription module/API/UI | 模板 JSON、四重校验、证据、版本、审批、导出 | ❌ 前端生成/表单含 mock |
| CLN-03 | 用药审查规则 | medication module/API/UI | DDI/Beers/剂量/重复、版本和来源 | ❌ 当前为前端 mock/LLM 文案 |
| CLN-04 | 健康画像产品 UI | memory API、RightPanel | 本人/授权医生读取、确认/退役、历史 | 🚧 后端完成，前端为 mock 信息 |
| CLN-05 | 临床规则版本 | cga/prescription/medication/safety | 报告保存规则/模板/证据版本 | ❌ 临床后端尚未实现 |
| CLN-06 | 统一风险预警闭环 | alert rules/workflow/API/患者医生 UI | 红旗/CGA/慢病/用药事件分级、通知确认、升级和紧急就医 | 🚧 Chat 红旗/自伤策略已有；缺统一事件、规则、通知与处置闭环 |
| CLN-07 | 慢病管理闭环 | chronic-care workflow/API/患者医生 UI | 疾病/目标/测量/用药/生活计划、趋势、依从性、提醒、异常升级 | ❌ 健康画像不是慢病管理，缺真实前后端链路 |
| CLN-08 | 安全情感陪伴 | companion agent/privacy/safety/UI | 支持性对话、痛苦识别、禁依赖/禁冒充、危机和人工升级、可关闭记忆 | ❌ 产品合同已建立；缺 Agent/workflow、前端入口与运行证据 |
| IAM-01 | 账号注册登录 | auth/account | 患者/医生注册登录、密码哈希、刷新/退出 | ❌ 仅访客短期 JWT |
| IAM-02 | 租户/主体/角色隔离 | auth/repositories | 越权 403/404、跨租户不可见 | 🚧 核心资源隔离，缺账号角色/RBAC |
| IAM-03 | 临床数据持久化加密 | DB/repositories | 文件、CGA、处方、审批、反馈、Bad Case | 🚧 会话/Memory/Skill/Trace 已有，其余缺表 |
| IAM-04 | 环境配置安全 | config、env templates | 生产拒绝 placeholder/缺 Key/不安全 URL | ✅ FastAPI 核心配置已验证 |
| IAM-05 | 患者授权生命周期 | consent/RBAC/cache | 授予/到期/撤回，缓存与链接失效 | ❌ 缺账号和授权模型 |
| IAM-06 | 管理/审计职责分离 | auth/RBAC | 无万能 scope；服务端角色校验 | ❌ 缺生产角色/RBAC |
| UI-01 | 三栏响应式布局 | MVP layout | 四断点浏览器证据 | 🚧 desktop 已有，完整断点 E2E 待补 |
| UI-02 | 多模态输入框 | ChatInput | 文本/语音/图片/10文件/Skill/处方/CGA/停止 | 🚧 UI 齐，文档与 Voice 后端未接 |
| UI-03 | Runtime 状态映射 | ChatArea/MessageBubble | 全 SSE 终态、错误恢复、HITL | 🚧 Chat/取消完成，缺 HITL/临床流程 |
| UI-04 | 适老化与无障碍 | globals/components | ≥18px/≥48px/AAA/ARIA/键盘/reduced-motion | 🚧 关键 Skill/免责声明通过，需全站审计 |
| UI-05 | 医疗安全呈现 | Message/clinical panels | 免责声明、引用、红旗、自伤、审批优先 | 🚧 Chat 已有，临床 mock 页面待统一 |
| UI-06 | 多格式导出 | export libs | PDF/Word/MD/TXT 内容与布局回归 | 🚧 前端能力已有，缺后端报告真数据和 TXT 一致性 |
| UI-07 | 兼容/恢复/审批/删除状态 | app UI | 不兼容、恢复、等待、撤回均可理解可操作 | ❌ 缺统一产品状态 |
| OPS-01 | Readiness | health service | DB/Redis/Qdrant/RAG generation/配置 503 | ✅ 真实依赖套件通过 |
| OPS-02 | metrics/feedback/eval/Bad Case | metrics/trace/feedback/eval | API、存储、回放、趋势 | ❌ metrics/Trace 部分有，闭环未实现 |
| OPS-03 | 测试覆盖门禁 | pytest/coverage | ≥80%，负向阈值 exit 1 | ✅ 80.02%，审阅者验证负向门禁 |
| OPS-04 | ≤10 并发 | integration/perf | 隔离、幂等、限流、取消、p50/p95 | 🚧 多项并发单测已有，缺统一 10 并发报告 |
| OPS-05 | Docker 全栈 | Dockerfiles/compose | 空卷启动、迁移、health、重启、非 root | 🚧 基础 compose/Dockerfile 有，最终应用验收未做 |
| OPS-06 | 故障注入 | unit/integration/e2e | 断流/429/5xx/依赖中断/lost-ack/竞争/重启 | 🚧 RAG/Chat 有较强覆盖，临床/Document/HITL 缺失 |
| OPS-07 | 供应链/SBOM | locks/CI/images | 固定版本、audit、SBOM、许可证、升级策略 | 🚧 lock/audit/CI pin 有，缺 SBOM/许可证策略 |
| OPS-08 | 千级扩展容量规划 | architecture/perf | 容量模型、背压、水平扩展、成本、压测计划 | ❌ 仅允许声明已验证的 10 并发范围 |
| SEC-01 | red-team 与安全 eval | security/eval/bad-case | 攻击语料、复现、回放、修复回归 | 🚧 多项对抗测试已有，缺统一语料与回放 |
| SEC-02 | 全出口泄露检测 | API/SSE/export/log/trace/vector | PHI/密钥 canary 在所有出口均不出现 | 🚧 核心日志/Trace/vector 已测，导出/临床未覆盖 |
| SEC-03 | 第三方/依赖/镜像威胁模型 | security/CI | 最小权限、固定版本、响应/替换策略 | 🚧 部分 pin/audit，缺完整威胁模型 |
| SEC-04 | 服务端安全边界 | auth/middleware/repos | scope/tenant/role/ownership/CSRF/CORS/SSRF/rate limit | 🚧 核心 scope/tenant/SSRF 已有，角色/CSRF 待补 |
| DATA-01 | 统一 schema/version/兼容 | domain/Zod/API | version、兼容窗口、迁移、unknown fields | 🚧 严格 schema 已有，缺统一版本兼容策略 |
| DATA-02 | 保留/导出/删除/备份 | privacy/storage | 各数据类别生命周期与可验证删除 | ❌ 缺数据生命周期实现 |
| DATA-03 | PHI 外发最小化与透明度 | privacy/provider audit | 脱敏、目的、处理方、撤回后续处理 | 🚧 query/Trace 脱敏已有，缺统一外发台账与用户透明度 |
| DATA-04 | 字段级分类与敏感度 | schema registry/privacy policy | 字段分类绑定处理方、存储、日志、Trace/vector/export 和保留规则 | ❌ 缺统一数据分类注册表与强制执行 |
| DATA-05 | 假名化与受控再识别 | identity vault/privacy/RBAC/audit | 可轮换 token、隔离映射、审批再识别、重识别风险评估 | 🚧 访客伪名主体已有；缺独立映射、审批与风险评估 |
| DATA-06 | 脱敏版本与误漏评测 | privacy/eval/bad-case | 规则/模型版本、canary/golden、FP/FN、跨文本/OCR/ASR/schema 回归 | ❌ 缺统一版本库、基准集与发布阈值 |

## 发布规则

- 任何 `❌` 都阻止总目标完成。
- `🚧` 只有在对应 exec-plan 中列出明确缺口、负责人和验收命令时才允许存在于开发分支；发布前必须归零。
- 每次里程碑归档必须同步更新本矩阵，禁止仅修改 README 声称完成。
