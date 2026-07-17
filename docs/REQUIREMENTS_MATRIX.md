# GerClaw 需求→模块→验收矩阵

> 更新：2026-07-16。状态必须以代码与可复现证据为准：✅完成、🚧部分实现、❌未实现。

| ID | 需求 | 设计→实现合同/模块 | 测试→运行证据 | 状态与缺口 |
|---|---|---|---|---|
| DEV-01 | 统一开发门禁 | 根脚本、CI、docs verifier | 一条命令跑 docs/format/lint/type/test/build/security | ✅ quality modes 与 CI workflow 已实现 |
| DEV-02 | 分层测试和隔离依赖 | `apps/api/tests` | unit/integration/external/e2e；独立 DB/Redis/Qdrant | ✅ marker 与隔离 fixture 已有 |
| DEV-03 | 证据和独立审阅 | exec-plan、`output/` | 每里程碑命令、截图、审阅 PASS、commit | ✅ 0014–0019 已执行 |
| DEV-04 | 模块合同 | `modules/*` | Protocol+生产实现+README+测试 | 🚧 所有含实现源码的核心模块现由 docs gate 强制要求 AGENTS.md/README.md；RAG/Memory/Search/Skill 已有完整生产纵切面，其余模块仍按各自计划补齐 Protocol、生产实现或真实集成证据 |
| DEV-05 | owner/预算/checkpoint | exec-plan、runtime | owner、预算、恢复入口、独立 reviewer | 🚧 Runtime 预算与加密 version-bound checkpoint 已实现；临床副作用 continuation executor 尚未启用 |
| RUN-01 | AgentScope ReAct/SSE/取消 | agent_harness、chat service | 真实模型+RAG+工具+原子终态 | ✅ 0016–0019 证据 |
| RUN-02 | ALLOW/DENY/ASK 与 HITL | permission、approval | 三决策单测；ASK 可恢复审批 | 🚧 PermissionEngine、加密审批 API、一次性 token、pending SSE 已实现；临床副作用 resume executor 待业务模块启用 |
| RUN-03 | 工具注册表和边界 | tools、harness | allowlist、schema、超时/大小/结果校验 | 🚧 RAG/Memory/Search/Skill 已通过 Runtime registry；初始本地 RAG 预取现以 `search_knowledge` 事件真实投影，临床写入工具待对应模块接入 |
| RUN-04 | PHI-free Trace | trace repo/routes | 成功/失败/取消/工具/Skill 全事件 | 🚧 核心 Chat 已有，缺审批/临床模块/反馈 |
| RUN-05 | workflow 与多智能体复核 | harness | standard/CGA；全科→老年专科复核 | 🚧 workflow 字段已有，缺生产复核链 |
| RUN-06 | 长任务 checkpoint/replay | runtime、repositories | 重启恢复且副作用不重复 | 🚧 加密 checkpoint、状态指纹和版本 fail-closed 已实现；副作用 replay executor 待临床模块接入 |
| RUN-07 | 执行预算 | harness、config | token/tool/time/call/output 超限稳定失败 | ✅ 统一 RuntimeBudgetTracker 已在 Agent Harness 计量 model/tool/step/token/output/wall-clock |
| AI-01 | 本地 RAG | `modules/rag` | 436 文档、39,837 chunks、混合检索/重排/引用、显式 opt-in 合成评测 | 🚧 当前生产镜像 readiness 已核验语料/索引一致，2026-07-17 的真实 embedding/rerank/Qdrant 回归同时通过“命中文档”和“无本地证据返回空结果”两例；仍需扩大人工审核的医学正例/反例集并完成临床有效性评测 |
| AI-02 | Memory/健康画像引擎 | `modules/memory` | 加密、跨会话、冲突、无 PHI vector | ✅ 2026-07-17 隔离 external/integration 用例实测模型抽取、跨会话召回、数据库密文与 Qdrant PHI-free payload；医生授权和生命周期属于后续 IAM/DATA 闭环 |
| AI-03 | Skill 生命周期 | `modules/skill`、Skill UI | 注册/版本/隔离/viewer/安全/真实模型 | ✅ 2026-07-17 隔离 external/integration 用例实测模型草稿、复核注册、会话加载、AgentScope 查看器、本地证据事件与 Trace；医疗业务发布审核和持续质量评测仍属临床闭环 |
| AI-04 | AnySearch→Tavily | `modules/search` | provider failover、网页隔离、引用 | ✅ 0018 独立 PASS |
| AI-05 | Voice 后端 | `modules/input_output` 或 voice | ASR/TTS schema、PCM16 流、取消、故障 | 🚧 浏览器现在仅经受限 `/api/gerclaw/voice/*` BFF 调用 FastAPI Voice Runtime；旧的直接 Provider BFF 已删除。TTS 的 24kHz 单声道 PCM16 在浏览器内封装为 WAV，因此消息播放器仍完整提供暂停、继续、停止与进度控制；ASR 有专用的受限 base64 音频请求体上限。2026-07-17 实际 BFF→FastAPI TTS 返回 `200 audio/L16;rate=24000;channels=1`；将该 PCM 封装为 WAV 后通过同一 BFF 调用 ASR，`200` 返回原句，两个 route 都记录 trace。FastAPI 仍执行受限 ASR、文本/style 脱敏与 PHI-free egress ledger；ASR 以无文本 `audio-egress-v1` 记录状态，不声称音频已去标识化或已获同意。缺真实人声 ASR/TTS 质量、取消和浏览器播放端到端评测，以及统一 adapter 版本协商 |
| AI-06 | Privacy | security、harness safety | PHI/凭证、注入、诊断、红旗、自伤、免责声明 | 🚧 核心规则分散，缺独立完整模块 |
| AI-07 | MinerU Document | document module、上传 UI | PDF/Office/MD/TXT 真实解析、轮询、重试 | 🚧 Next.js BFF 已真实完成签名上传、轮询和 Markdown 下载；FastAPI 已登记加密会话文档，删除会话会级联擦除会话消息、文档、临床收集及会话绑定审批/检查点。上传资料按当前设计是当前会话的受控输入，**不作为私有向量知识库证据**；长文档受限上下文策略、跨会话保留、医生授权与病毒扫描待完成 |
| AI-08 | Provider capability/version | services/adapters | schema/version/能力协商与不兼容拒绝 | 🚧 AgentScope 版本固定，其他 adapter 合同未统一 |
| CLN-01 | CGA 后端闭环 | cga module/API/UI | 量表、答案、确定性计分、报告、历史 | 🚧 PHQ-9、SAS、PSQI 已具版本化 FastAPI 状态机、确定性计分、患者端真实 API、报告导出与本人历史；Mini-Cog/MMSE 的人工确认、医生授权与历史比较待完成 |
| CLN-02 | 五大处方后端闭环 | prescription module/API/UI | 模板 JSON、四重校验、证据、版本、审批、导出 | 🚧 真实、加密、版本化的最小信息收集与 MinerU 资料绑定已接入；没有医学审核的 JSON 模板、四重校验、证据、报告、导出或医生批准，页面不得生成处方建议 |
| CLN-03 | 用药审查规则 | medication module/API/UI | DDI/Beers/剂量/重复、版本和来源 | 🚧 真实、加密、版本化的用药信息收集已接入；没有经医学审核的 DDI/Beers/剂量/重复用药规则、来源版本、审查结论或医生批准 |
| CLN-04 | 健康画像产品 UI | memory API、RightPanel | 本人/授权医生读取、确认/退役、历史 | 🚧 当前访客可经受限 BFF 读取本人已确认事实，并确认/忽略待确认事实；账号、患者授权、医生跨患者读取与历史视图待完成 |
| CLN-05 | 临床规则版本 | cga/prescription/medication/safety | 报告保存规则/模板/证据版本 | 🚧 CGA 的量表定义与确定性计分已版本化；五大处方通用模板、证据规则、用药审查规则及其医学审核记录尚未提供，不能生成临床建议 |
| CLN-06 | 统一风险预警闭环 | alert rules/workflow/API/患者医生 UI | 红旗/CGA/慢病/用药事件分级、通知确认、升级和紧急就医 | 🚧 Chat 红旗、CGA 即时安全与高风险随访可真实、原子地创建加密且本人范围的告警，并支持版本围栏、幂等确认。患者端“我的安全提醒”已经受限 BFF 读取本人告警并可记录“已了解”（不解除风险）；浏览器实测无告警读取 200。尚缺慢病/用药来源、通知升级、医生队列，以及含合成告警的确认 E2E |
| CLN-07 | 慢病管理闭环 | chronic-care workflow/API/患者医生 UI | 疾病/目标/测量/用药/生活计划、趋势、依从性、提醒、异常升级 | 🚧 已有真实、加密且 tenant/actor 隔离的自述病情与测量账本，以及不含临床含义的数值方向；患者端“我的慢病记录”已通过受控 BFF 读写和展示。没有医学审核的目标/阈值、用药或生活计划、提醒、异常升级、患者/医生授权 |
| CLN-08 | 安全情感陪伴 | companion agent/privacy/safety/UI | 支持性对话、痛苦识别、禁依赖/禁冒充、危机和人工升级、可关闭记忆 | 🚧 `workflow=companion` 已接入真实 Chat Harness，禁用长期健康 Memory、RAG、联网、Skill 与上传资料，只保留加密的同会话短期上下文；红旗仍在模型前短路。患者端已有“暖心陪伴”入口，进入时新建会话并隐藏资料/Skill 控件；浏览器实测请求带 `workflow=companion` 且 Skill/资料数组为空。当前模型 provider 未就绪，只能验证安全失败态；仍缺用户可配置记忆偏好、人工升级与医生授权 |
| IAM-01 | 账号注册登录 | auth/account | 患者/医生注册登录、密码哈希、刷新/退出 | 🚧 已有本地患者/医生注册、登录、scrypt 密码哈希、refresh 轮换、登出、改密、服务端会话身份读取与 BFF HttpOnly cookie/CSRF；患者/医生登录注册入口已接入侧边栏，仍缺账号标识验证、找回、MFA、停用和风控策略 |
| IAM-02 | 租户/主体/角色隔离 | auth/repositories | 越权 403/404、跨租户不可见 | 🚧 核心资源隔离；服务端 JWT 账号角色已进入 Runtime，医生未获 patient proof；缺医生资质、患者授权和完整 RBAC |
| IAM-03 | 临床数据持久化加密 | DB/repositories | 文件、CGA、处方、审批、反馈、Bad Case | 🚧 会话/Memory/Skill/Trace 已有，其余缺表 |
| IAM-04 | 环境配置安全 | config、env templates | 生产拒绝 placeholder/缺 Key/不安全 URL | ✅ FastAPI 核心配置已验证 |
| IAM-05 | 患者授权生命周期 | consent/RBAC/cache | 授予/到期/撤回，缓存与链接失效 | ❌ 缺账号和授权模型 |
| IAM-06 | 管理/审计职责分离 | auth/RBAC | 无万能 scope；服务端角色校验 | ❌ 缺生产角色/RBAC |
| UI-01 | 三栏响应式布局 | MVP layout | 四断点浏览器证据 | 🚧 desktop 已有，完整断点 E2E 待补 |
| UI-02 | 多模态输入框 | ChatInput | 文本/语音/图片/10文件/Skill/处方/CGA/停止 | 🚧 文本、Skill、受限临床收集、CGA、FastAPI Voice Runtime BFF 与 MinerU BFF 已接入；图片多模态、Document Runtime adapter 与语音完整异常 E2E 待补 |
| UI-03 | Runtime 状态映射 | ChatArea/MessageBubble | 全 SSE 终态、错误恢复、HITL | 🚧 Chat/取消完成，缺 HITL/临床流程 |
| UI-04 | 适老化与无障碍 | globals/components | ≥18px/≥48px/AAA/ARIA/键盘/reduced-motion | 🚧 关键 Skill/免责声明通过，需全站审计 |
| UI-05 | 医疗安全呈现 | Message/clinical panels | 免责声明、引用、红旗、自伤、审批优先 | 🚧 Chat 已有，临床 mock 页面待统一 |
| UI-06 | 多格式导出 | export libs | PDF/Word/MD/TXT 内容与布局回归 | 🚧 前端能力已有，缺后端报告真数据和 TXT 一致性 |
| UI-07 | 兼容/恢复/审批/删除状态 | app UI | 不兼容、恢复、等待、撤回均可理解可操作 | ❌ 缺统一产品状态 |
| OPS-01 | Readiness | health service | DB/Redis/Qdrant/RAG generation/配置 503 | ✅ 真实依赖套件通过 |
| OPS-02 | metrics/feedback/eval/Bad Case | metrics/trace/feedback/eval | API、存储、回放、趋势 | 🚧 Trace/基础反馈与加密 Bad Case 已有；新增 6 个合成、人工审阅的确定性安全 golden case，禁止回放真实输入，已验证不调用模型/RAG。尚缺授权脱敏晋升、模型/RAG 评测、趋势与指标闭环 |
| OPS-03 | 测试覆盖门禁 | pytest/coverage | ≥80%，负向阈值 exit 1 | ✅ 80.02%，审阅者验证负向门禁 |
| OPS-04 | ≤10 并发 | integration/perf | 隔离、幂等、限流、取消、p50/p95 | 🚧 已有 Compose API 的 10 并发安全短路 SSE 报告（p50 153ms/p95 154ms、10/10 done、跨访客 404）；完整临床 workflow、取消/限流/幂等的统一负载仍待补齐 |
| OPS-05 | Docker 全栈 | Dockerfiles/compose | 空卷启动、迁移、health、重启、非 root | 🚧 基础 compose/Dockerfile 有，最终应用验收未做 |
| OPS-06 | 故障注入 | unit/integration/e2e | 断流/429/5xx/依赖中断/lost-ack/竞争/重启 | 🚧 RAG/Chat 有较强覆盖，临床/Document/HITL 缺失 |
| OPS-07 | 供应链/SBOM | locks/CI/images | 固定版本、audit、SBOM、许可证、升级策略 | 🚧 lock/audit/CI pin 有；`security` 可从实际 production API image 生成 Python runtime CycloneDX SBOM，许可证未知项显式报告。Debian/npm runtime 清单、法务复审与发布签名仍待最终交付阶段。 |
| OPS-08 | 千级扩展容量规划 | architecture/perf | 容量模型、背压、水平扩展、成本、压测计划 | ❌ 仅允许声明已验证的 10 并发范围 |
| SEC-01 | red-team 与安全 eval | security/eval/bad-case | 攻击语料、复现、回放、修复回归 | 🚧 多项对抗测试已有，缺统一语料与回放 |
| SEC-02 | 全出口泄露检测 | API/SSE/export/log/trace/vector | PHI/密钥 canary 在所有出口均不出现 | 🚧 核心日志/Trace/vector 已测，导出/临床未覆盖 |
| SEC-03 | 第三方/依赖/镜像威胁模型 | security/CI | 最小权限、固定版本、响应/替换策略 | 🚧 部分 pin/audit，缺完整威胁模型 |
| SEC-04 | 服务端安全边界 | auth/middleware/repos | scope/tenant/role/ownership/CSRF/CORS/SSRF/rate limit | 🚧 核心 scope/tenant/SSRF 已有，角色/CSRF 待补 |
| DATA-01 | 统一 schema/version/兼容 | domain/Zod/API | version、兼容窗口、迁移、unknown fields | 🚧 严格 schema 已有，缺统一版本兼容策略 |
| DATA-02 | 保留/导出/删除/备份 | privacy/storage | 各数据类别生命周期与可验证删除 | 🚧 会话拥有者现可删除空闲会话，数据库级级联实际擦除会话消息、解析文档、临床收集、会话审批与检查点；健康画像、CGA、慢病、Skill、账户、备份、TTL、导出和可验证删除报告仍未实现 |
| DATA-03 | PHI 外发最小化与透明度 | privacy/provider audit | 脱敏、目的、处理方、撤回后续处理 | 🚧 版本化 `privacy_redaction` 已真实拦截外部搜索 query、FastAPI TTS 正文/style，并在模型 Provider 调用前创建独立 `external_model_prompt` 内存投影；FastAPI TTS、ASR、`/search/query`、MinerU BFF 与每个逻辑模型槽位均有调用前的 PHI-free egress outcome audit。ASR、MinerU 不宣称已去标识化；模型/MinerU 用户同意、网页提取/AgentScope 内部搜索台账、撤回处理与用户透明度仍缺失 |
| DATA-04 | 字段级分类与敏感度 | schema registry/privacy policy | 字段分类绑定处理方、存储、日志、Trace/vector/export 和保留规则 | 🚧 已有 `privacy_redaction` 外发类别与 Runtime DataClass，尚缺统一字段注册表、存储/日志/导出规则绑定及全链路强制执行 |
| DATA-05 | 假名化与受控再识别 | identity vault/privacy/RBAC/audit | 可轮换 token、隔离映射、审批再识别、重识别风险评估 | 🚧 访客伪名主体已有；缺独立映射、审批与风险评估 |
| DATA-06 | 脱敏版本与误漏评测 | privacy/eval/bad-case | 规则/模型版本、canary/golden、FP/FN、跨文本/OCR/ASR/schema 回归 | 🚧 已有 4 条版本绑定、人工审阅的合成文本 canary，覆盖当前 search/TTS `1.1.0` 规则且不回显样例；缺 OCR/ASR/自由文本/结构化字段、检测模型、FP/FN 指标和发布阈值 |

## 发布规则

- 任何 `❌` 都阻止总目标完成。
- `🚧` 只有在对应 exec-plan 中列出明确缺口、负责人和验收命令时才允许存在于开发分支；发布前必须归零。
- 每次里程碑归档必须同步更新本矩阵，禁止仅修改 README 声称完成。
