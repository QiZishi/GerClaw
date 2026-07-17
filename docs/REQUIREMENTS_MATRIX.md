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
| RUN-05 | workflow 与多智能体复核 | harness、workflows | standard/CGA；全科→老年专科复核 | 🚧 `modules/workflows` 已以版本、owner、允许上下文和 workflow 风险档案注册标准咨询/CGA/陪伴，并实际在 Chat 前 fail closed、写入 Trace；仍缺生产多智能体复核、临床副作用恢复/补偿与批准后执行 |
| RUN-06 | 长任务 checkpoint/replay | runtime、repositories | 重启恢复且副作用不重复 | 🚧 加密 checkpoint、状态指纹和版本 fail-closed 已实现；副作用 replay executor 待临床模块接入 |
| RUN-07 | 执行预算 | harness、config | token/tool/time/call/output 超限稳定失败 | ✅ 统一 RuntimeBudgetTracker 已在 Agent Harness 计量 model/tool/step/token/output/wall-clock |
| AI-01 | 本地 RAG | `modules/rag` | 436 文档、39,837 chunks、混合检索/重排/引用、`local-rag-evidence-v1` provenance、显式 opt-in 合成评测 | 🚧 当前生产镜像 readiness 已核验语料/索引一致；2026-07-18 的真实 embedding/rerank/Qdrant 回归以绑定索引版本完成 6/6（五个命中文档、一个无本地证据为空），且每条返回 chunk 都通过同一 provenance 契约。Chat 在本地、上传和联网证据均不可用时不会伪造引用或直接报错，而会保存一条不调用模型的补充信息提示。仍需扩大人工审核的医学正例/反例集并完成临床有效性评测 |
| AI-02 | Memory/健康画像引擎 | `modules/memory` | 加密、跨会话、冲突、无 PHI vector | ✅ 2026-07-17 隔离 external/integration 用例实测模型抽取、跨会话召回、数据库密文与 Qdrant PHI-free payload；医生授权和生命周期属于后续 IAM/DATA 闭环 |
| AI-03 | Skill 生命周期 | `modules/skill`、Skill UI | 注册/版本/隔离/viewer/自然语言生成与受控迭代/安全/真实模型 | ✅ 2026-07-17 隔离 external/integration 用例实测模型草稿、复核注册、会话加载、AgentScope 查看器、本地证据事件与 Trace；另有 BFF 接通的“生成待审阅修订”：仅自定义 Skill、revision 匹配、同 ID 且更高版本，结果不会自动保存或启用。医疗业务发布审核和持续质量评测仍属临床闭环 |
| AI-04 | AnySearch→Tavily | `modules/search` | provider failover、网页隔离、引用 | ✅ 0018 独立 PASS |
| AI-05 | Voice 后端 | `modules/input_output` 或 voice | ASR/TTS schema、PCM16 流、取消、故障 | 🚧 浏览器现在仅经受限 `/api/gerclaw/voice/*` BFF 调用 FastAPI Voice Runtime；旧的直接 Provider BFF 已删除。TTS 的 24kHz 单声道 PCM16 在浏览器内封装为 WAV，因此消息播放器仍完整提供暂停、继续、停止与进度控制；ASR 有专用的受限 base64 音频请求体上限。2026-07-17 实际 BFF→FastAPI TTS 返回 `200 audio/L16;rate=24000;channels=1`；将该 PCM 封装为 WAV 后通过同一 BFF 调用 ASR，`200` 返回原句，两个 route 都记录 trace。CGA 版本绑定预录制音频的浏览器回归已实际验证朗读→暂停→继续→停止并恢复为可重播，控制台无业务错误；低风险真实 AI 回复的动态 TTS 也已实际验证播放→暂停→继续，控制台无业务错误。FastAPI 仍执行受限 ASR、文本/style 脱敏与 PHI-free egress ledger；ASR 以无文本 `audio-egress-v1` 记录状态，不声称音频已去标识化或已获同意。缺真实人声 ASR/TTS 质量、取消和浏览器播放端到端评测，以及统一 adapter 版本协商 |
| AI-06 | Privacy | security、harness safety | PHI/凭证、注入、诊断、红旗、自伤、免责声明 | 🚧 核心规则分散，缺独立完整模块 |
| AI-07 | MinerU Document | document module、上传 UI | PDF/Office/MD/TXT 真实解析、轮询、重试 | 🚧 Next.js BFF 已真实完成签名上传、轮询和 Markdown 下载；2026-07-17 对用户指定的既有病例 PDF 实测返回 HTTP 200 与 4,698 字符 Markdown，随后登记为 `mineru` 会话输入、撤销资料并删除临时会话均返回 200。FastAPI 已登记加密会话文档，删除会话会级联擦除会话消息、文档、临床收集及会话绑定审批/检查点。五大处方会把同会话、已解析上传资料作为可追溯的患者资料证据；它们仍**不进入私有向量知识库**，也不伪装为本地医学知识库来源。长文档受限上下文策略、跨会话保留、医生授权与病毒扫描待完成 |
| AI-08 | Provider capability/version | services/adapters | schema/version/能力协商与不兼容拒绝 | 🚧 AgentScope 版本固定，其他 adapter 合同未统一 |
| CLN-01 | CGA 后端闭环 | cga module/API/UI | 量表、答案、确定性计分、报告、历史 | 🚧 PHQ-9、SAS、PSQI、Mini-Cog、MMSE 均具版本化 FastAPI 状态机、确定性计分、患者端真实 API、本人历史和 Markdown/PDF/可编辑 DOCX 报告导出；同一用户/量表/版本的相邻完成结果可作数值对照，版本不同明确拒绝比较且不作临床解释。Mini-Cog/MMSE 明确是基于本人作答的筛查，不自动核验绘图/动作/书写/阅读；医生跨账号查看与授权仍待完成 |
| CLN-02 | 五大处方后端闭环 | prescription module/API/UI | 模板 JSON、四重校验、证据、版本、审批、导出 | 🚧 真实、加密、版本化对话收集、MinerU 资料绑定、结构化模型、本地 RAG、真实校验联网检索和同会话上传资料证据已接入；来源在报告中区分，草案历史与 Markdown/PDF/Word 导出可用。模型的药物开始、停用、替换和剂量调整仅可作为证据绑定的临床复核候选；若模型引用未知 evidence ID 或将正向指令置于无引用自由字段，则改为可审阅的循证基线，而非返回 503；报告末尾统一提示风险。2026-07-18 的聊天入口可显示低频运行状态与精确耗时，并可经 owner-scoped BFF/API 安全停止；服务端持久化 cancelled Trace，取消后不写草案。仍缺医学审核/批准和患者授权；不得将草案发布为处方建议 |
| CLN-03 | 用药审查规则 | medication module/API/UI/evals | DDI/Beers/剂量/重复、版本和来源 | 🚧 已接入真实、加密、版本化信息收集及确定性 `medication-rules-v3`：30 条安装的本地可追溯 DDI、4 条精确日剂量阈值、通用名重复与多重用药待复核事实，规则来源、定位和语料指纹随结果返回；禁忌/严重命中会原子创建不含药物详情的本人安全提醒。六个 `medication-rule-case-v1` 合成回归分别约束高风险命中、剂量、年龄门槛、来源和未知药物无伪命中。另有一个只在≥65 岁明确命中苯二氮卓类时触发、且不推定适应证的 Beers 相关本地来源核对信号。有限规则待临床治理批准，未覆盖完整 Beers、全量 DDI/剂量/重复成分，且没有医生批准/患者发布闭环 |
| CLN-04 | 健康画像产品 UI | memory API、RightPanel | 本人/授权医生读取、确认/退役、历史 | 🚧 当前访客可经受限 BFF 读取本人已确认事实，并确认/忽略待确认事实；可在每条已确认事实中查看本人不可变变更历史。账号、患者授权与医生跨患者读取仍待完成 |
| CLN-05 | 临床规则版本 | cga/prescription/medication/safety | 报告保存规则/模板/证据版本 | 🚧 CGA 的量表定义与确定性计分已版本化；五大处方有版本化模板和证据绑定草案，药物审查有来源可追溯但待临床治理批准的有限规则集。完整 DDI/Beers/剂量规则、医学审核记录和医生批准链路仍未提供，不能将结果发布为可执行临床建议 |
| CLN-06 | 统一风险预警闭环 | alert rules/workflow/API/患者医生 UI | 红旗/CGA/慢病/用药事件分级、通知确认、升级和紧急就医 | 🚧 Chat 红旗、CGA 即时安全与高风险随访、以及确定性用药审查的禁忌/严重命中可真实、原子地创建加密且本人范围的告警，并支持版本围栏、幂等确认；active critical 会优先展示。患者端“我的安全提醒”已经受限 BFF 读取本人告警并可记录“已了解”（不解除风险）；2026-07-17 Compose 浏览器实测用药审查→患者提醒。尚缺慢病来源、通知升级、医生队列，以及正式授权后的跨主体闭环 |
| CLN-07 | 慢病管理闭环 | chronic-care workflow/API/患者医生 UI | 疾病/目标/测量/用药/生活计划、趋势、依从性、提醒、异常升级 | 🚧 已有真实、加密且 tenant/actor 隔离的自述病情与测量账本，以及不含临床含义的数值方向；患者端“我的慢病记录”已通过受控 BFF 读写和展示。没有医学审核的目标/阈值、用药或生活计划、提醒、异常升级、患者/医生授权 |
| CLN-08 | 安全情感陪伴 | companion agent/privacy/safety/UI | 支持性对话、痛苦识别、禁依赖/禁冒充、危机和人工升级、可关闭记忆 | 🚧 `workflow=companion` 已接入真实 Chat Harness，禁用长期健康 Memory、RAG、联网、Skill 与上传资料，只保留加密的同会话短期上下文；红旗仍在模型前短路。患者端已有“暖心陪伴”入口，进入时新建会话并隐藏资料/Skill 控件；浏览器实测请求带 `workflow=companion` 且 Skill/资料数组为空。当前模型 provider 未就绪，只能验证安全失败态；仍缺用户可配置记忆偏好、人工升级与医生授权 |
| IAM-01 | 账号注册登录 | auth/account | 患者/医生注册登录、密码哈希、刷新/退出 | 🚧 已有本地患者/医生注册、登录、scrypt 密码哈希、refresh 轮换、登出、改密、本人停用与服务端会话身份读取，并通过 BFF HttpOnly cookie/CSRF 接入。无账号访问先进入登录页，可选择匿名进入患者端；匿名会话不恢复历史，数据仍由服务端保留用于 Bad Case。仍缺账号标识验证、找回、MFA 与风控策略 |
| IAM-02 | 租户/主体/角色隔离 | auth/repositories | 越权 403/404、跨租户不可见 | 🚧 核心资源隔离；2026-07-18 Trace 读取已从仅 tenant 范围收敛为本人范围，患者/医生/游客读取他人 Trace 一律得到 404，只有持有服务端 `account:admin` 的管理员可作 tenant 内运营审阅。医生未获 patient proof；仍缺医生资质、患者授权和完整 RBAC |
| IAM-03 | 临床数据持久化加密 | DB/repositories | 文件、CGA、处方、审批、反馈、Bad Case | 🚧 会话/Memory/Skill/Trace 已有，其余缺表 |
| IAM-04 | 环境配置安全 | config、env templates | 生产拒绝 placeholder/缺 Key/不安全 URL | ✅ FastAPI 核心配置已验证 |
| IAM-05 | 患者授权生命周期 | consent/RBAC/cache | 授予/到期/撤回，缓存与链接失效 | ❌ 缺账号和授权模型 |
| IAM-06 | 管理/审计职责分离 | auth/RBAC | 无万能 scope；服务端角色校验 | 🚧 管理员账号可经服务端 `account:admin` scope 管理同 tenant 的患者/医生账号状态与角色，并可在管理控制台、患者端和医生端之间往返；前端入口不授予权限，所有管理请求仍由服务端角色校验。患者和医生账号不能自行切换角色，游客固定为患者端。仍缺医生资质、患者授权、细粒度临床 RBAC 和完整审计保留策略 |
| UI-01 | 三栏响应式布局 | MVP layout | 四断点浏览器证据 | 🚧 desktop 已有，完整断点 E2E 待补 |
| UI-02 | 多模态输入框 | ChatInput | 文本/语音/图片/10文件/Skill/处方/CGA/停止 | 🚧 文本、Skill、受限临床收集、CGA、FastAPI Voice Runtime BFF、MinerU BFF 与图片多模态链路已接入。2026-07-18 Compose 浏览器实测上传 PNG 后，模型识读图中 CGA 量表内容，SSE `done` 返回上传图片 evidence_id；图片 base64 作为私有 Trace 输入保存。Document Runtime adapter 与语音异常/取消的完整 E2E 待补 |
| UI-03 | Runtime 状态映射 | ChatArea/MessageBubble | 全 SSE 终态、错误恢复、HITL | 🚧 Chat/取消完成；2026-07-18 已修复 Next.js BFF 反向代理会使上游误判断流、返回空 200 SSE 的问题，并以真实图片流验证 `agent_start`、`text_delta`、`done`、执行时长和终态引用。仍缺 HITL/临床流程 |
| UI-04 | 适老化与无障碍 | globals/components | ≥18px/≥48px/AAA/ARIA/键盘/reduced-motion | 🚧 关键 Skill/免责声明通过，需全站审计 |
| UI-05 | 医疗安全呈现 | Message/clinical panels | 免责声明、引用、红旗、自伤、审批优先 | 🚧 Chat 已有，临床 mock 页面待统一 |
| UI-06 | 多格式导出 | export libs | PDF/Word/MD/TXT 内容与布局回归 | 🚧 CGA 已从真实服务端报告导出 Markdown/PDF/Word；2026-07-17 浏览器实际下载 DOCX 并通过 Office 包完整性及免责声明内容检查。普通对话现支持 Markdown/PDF/DOCX/TXT（图片为补充格式），四种文本类导出均使用同一条医疗免责声明；2026-07-18 真实访客患者会话已实际下载 TXT，核验含原始紧急分流内容且不再出现“空消息”。五大处方与各格式的统一内容/布局回归仍缺 |
| UI-07 | 兼容/恢复/审批/删除状态 | app UI | 不兼容、恢复、等待、撤回均可理解可操作 | ❌ 缺统一产品状态 |
| OPS-01 | Readiness | health service | DB/Redis/Qdrant/RAG generation/配置 503 | ✅ 真实依赖套件通过 |
| OPS-02 | metrics/feedback/eval/Bad Case | metrics/trace/feedback/eval | API、存储、回放、趋势 | 🚧 Trace/基础反馈与加密 Bad Case 已有；2026-07-18 管理员可通过 `account:admin` 读取 PHI-free 队列元数据并更新处置状态，管理员前端已实际接入，API/BFF 均不暴露 snapshot/评论/原始输入。队列查询显式不加载加密 snapshot，历史密钥不可读时仍可读取和处置。19 个合成安全/输出安全/隐私/用药规则 policy case 不回放真实输入；test image 的显式 opt-in RAG 评测对五个本地老年医学主题命中和一个无证据例均为 6/6。尚缺授权脱敏晋升、模型/临床评测、趋势与指标闭环 |
| OPS-03 | 测试覆盖门禁 | pytest/coverage | ≥80%，负向阈值 exit 1 | ✅ 80.02%，审阅者验证负向门禁 |
| OPS-04 | ≤10 并发 | integration/perf | 隔离、幂等、限流、取消、p50/p95 | 🚧 2026-07-18 当前 Compose API 的 10 并发安全短路 SSE 为 10/10 done、失败率 0、p50 99ms/p95 100ms、10 个唯一 completed Trace、访客 history 10/10 为 403、跨访客 Trace 为 404；完整临床 workflow、取消/限流/幂等的统一负载仍待补齐 |
| OPS-05 | Docker 全栈 | Dockerfiles/compose | 空卷启动、迁移、health、重启、非 root | ✅ 2026-07-18 `docker-smoke` 在独立项目、全新临时卷中实际通过：迁移、3 份受控代表性 RAG 文档的真实 embedding/index、`live`/`ready`、非 root API 与重启后 readiness；完成后容器、网络、卷均自动清理。它不外推为临床 workflow E2E 或容量验收 |
| OPS-06 | 故障注入 | unit/integration/e2e | 断流/429/5xx/依赖中断/lost-ack/竞争/重启 | 🚧 RAG/Chat 有较强覆盖，临床/Document/HITL 缺失 |
| OPS-07 | 供应链/SBOM | locks/CI/images | 固定版本、audit、SBOM、许可证、升级策略 | 🚧 lock/audit/CI pin 有；`security` 可从实际 production API image 生成 Python runtime CycloneDX SBOM，许可证未知项显式报告。Debian/npm runtime 清单、法务复审与发布签名仍待最终交付阶段。 |
| OPS-08 | 千级扩展容量规划 | architecture/perf | 容量模型、背压、水平扩展、成本、压测计划 | 🚧 已有可审计的 1,000 活跃连接设计基线：无状态 BFF/API、SSE owner lease、有界队列、分 lane 准入、资源预算、分阶段压测/故障注入/放量门槛见 `docs/design-docs/容量与扩展计划.md`；实际只验证了 10 并发确定性安全短路，尚未验证模型/RAG/临床 workflow 或千级负载 |
| SEC-01 | red-team 与安全 eval | security-evaluation/eval/bad-case | 攻击语料、可执行风险档案、复现、回放、修复回归 | 🚧 Chat 的 `search_knowledge`、`search_memory`、`web_search` 已在 Runtime 注册/构建时经过版本、风险、网络、数据类别与必需控制的 fail-closed 档案门禁；外网工具还需服务端脱敏证明。`standard`、`cga`、`companion` workflow 也已在 Chat 前核验精确风险档案。其余 Agent/Skill/Memory/RAG-source 尚未接入生产档案门禁，统一攻击语料与回放仍缺 |
| SEC-02 | 全出口泄露检测 | API/SSE/export/log/trace/vector | PHI/密钥 canary 在所有出口均不出现 | 🚧 核心日志/Trace/vector 已测，导出/临床未覆盖 |
| SEC-03 | 第三方/依赖/镜像威胁模型 | security/CI | 最小权限、固定版本、响应/替换策略 | 🚧 部分 pin/audit，缺完整威胁模型 |
| SEC-04 | 服务端安全边界 | auth/middleware/repos | scope/tenant/role/ownership/CSRF/CORS/SSRF/rate limit | 🚧 核心 scope/tenant/SSRF 已有，角色/CSRF 待补 |
| DATA-01 | 统一 schema/version/兼容 | domain/Zod/API/validation | version、兼容窗口、迁移、unknown fields | 🚧 `modules/validation` 已以 `public-chat-sse-v1` 实际接管 Harness→Chat Service→浏览器 SSE 的事件级严格校验；`local-rag-evidence-v1` 已在 Hybrid RAG 产出、AgentScope adapter、引用投影和 RAG Eval 复用，未知或不完整 provenance 不能被默认位置补写。五大处方生成/聊天式信息提取、Memory 抽取及 Skill 生成/修订已接入共享版本化模型输出验证，各自只接受显式 schema version。ASR 的严格 JSON 与 TTS PCM16 响应已分别声明 `voice-asr-response-v1`/`voice-tts-pcm16-v1`，BFF 仅转发该契约 header，浏览器严格核验。HTTP、工具与 export 仍需按风险逐步迁移，尚无跨边界统一兼容窗口 |
| DATA-02 | 保留/导出/删除/备份 | privacy/storage | 各数据类别生命周期与可验证删除 | 🚧 会话拥有者现可删除空闲会话，数据库级级联实际擦除会话消息、解析文档、临床收集、会话审批与检查点；健康画像、CGA、慢病、Skill、账户、备份、TTL、导出和可验证删除报告仍未实现 |
| DATA-03 | PHI 外发最小化与透明度 | privacy/provider audit | 脱敏、目的、处理方、撤回后续处理 | 🚧 版本化 `privacy_redaction` 已真实拦截外部搜索 query、FastAPI TTS 正文/style，并在模型 Provider 调用前创建独立 `external_model_prompt` 内存投影；FastAPI TTS、ASR、`/search/query`、MinerU BFF 与每个逻辑模型槽位均有调用前的 PHI-free egress outcome audit。ASR、MinerU 不宣称已去标识化；模型/MinerU 用户同意、网页提取/AgentScope 内部搜索台账、撤回处理与用户透明度仍缺失 |
| DATA-04 | 字段级分类与敏感度 | schema registry/privacy policy | 字段分类绑定处理方、存储、日志、Trace/vector/export 和保留规则 | 🚧 已有 `privacy_redaction` 外发类别与 Runtime DataClass，尚缺统一字段注册表、存储/日志/导出规则绑定及全链路强制执行 |
| DATA-05 | 假名化与受控再识别 | identity vault/privacy/RBAC/audit | 可轮换 token、隔离映射、审批再识别、重识别风险评估 | 🚧 访客伪名主体已有；缺独立映射、审批与风险评估 |
| DATA-06 | 脱敏版本与误漏评测 | privacy/eval/bad-case | 规则/模型版本、canary/golden、FP/FN、跨文本/OCR/ASR/schema 回归 | 🚧 已有 6 条版本绑定、人工审阅的合成文本 canary：4 条覆盖 search/TTS `1.1.0`，2 条覆盖 model prompt `1.0.0`（含 Markdown 保留），且不回显样例；非文本 ASR/文档 purpose 会被 runner 拒绝，不能误称文本脱敏覆盖；仍缺 OCR/ASR/自由文本/结构化字段、检测模型、FP/FN 指标和发布阈值 |

## 发布规则

- 任何 `❌` 都阻止总目标完成。
- `🚧` 只有在对应 exec-plan 中列出明确缺口、负责人和验收命令时才允许存在于开发分支；发布前必须归零。
- 每次里程碑归档必须同步更新本矩阵，禁止仅修改 README 声称完成。
