# GerClaw 产品需求文档（生产版）

> 版本：v2.0 | 更新：2026-07-18 | 状态：交付基线
>
> 最高权威为 `docs/references/gerclaw设计要求.md`。本文只将其转成可实施、可测试的产品合同；发生冲突时以前者为准。

## 1. 产品目标

GerClaw 是面向老年患者与老年科医生的 Web 端 AI 双向诊疗平台。平台以老年专科医生智能体为核心，通过语音优先的适老化交互、CGA、五大处方、用药审查、循证检索与医生审批，提供可解释、可追踪、可安全失败的健康服务。

生产版必须同时满足：

1. 系统先展示登录页；使用者可不注册、不登录，选择匿名进入患者端。账号用户可持久化并按已验证角色进入患者端或医生端。
2. 所有医疗建议都基于可追溯证据，不给出确定性诊断，并强制显示免责声明与红旗症状就医提示。
3. 所有模型、工具、上传、存储和 API 响应都经过运行时 schema 与权限校验；失败不得伪装成成功。
4. Development Harness 让开发、验证、复现和审阅可重复；Runtime Agent Harness 让智能体执行、工具权限、Trace 和人机审批可审计。
5. 最终以 Docker 全栈运行，FastAPI 承担所有 Provider 调用和敏感数据处理，浏览器不接触服务密钥。

## 2. 用户与模式

| 用户 | 主要任务 | 默认体验 | 数据边界 |
|---|---|---|---|
| 访客 | 患者端健康咨询、语音、CGA、处方、文档等受限服务 | 从登录页主动选择匿名进入；固定患者端且默认老年模式 | 每次页面生命周期使用短期匿名主体；不恢复历史会话，运行记录仅用于受控 Trace/反馈/Bad Case |
| 老年患者 | 描述症状、完成评估、查看通俗建议和处方 | ≥18px 正文、≥48px 控件、高对比度、语音优先 | 只能访问本人数据 |
| 老年科医生 | 患者管理、CGA、用药审查、处方编辑与审批 | 专业高密度界面、完整证据和风险说明 | 只访问被授权患者和机构数据 |
| 审核/运维人员 | 处理 HITL、Trace、反馈、Bad Case、健康状态 | 审计视图 | 最小权限、不可见不必要 PHI |

## 3. 核心用户旅程

### 3.1 通用循证对话

输入文本/语音/图片/文档 → Privacy 输入过滤 → 会话、画像与已加载 Skill 组装 → 本地 RAG 优先 → 必要时联网搜索 → AgentScope ReAct → 输出安全后处理 → SSE 渲染 → 引用、免责声明、Trace、反馈。

验收：停止、超时、模型切换、工具失败、引用不可用均有明确终态；不能以无证据建议降级成“成功”。

### 3.2 CGA

选择一个或多个量表 → 题目/预录音频/语音答题 → 确定性计分 → 风险分级 → 循证解读 → 综合报告 → 医生端查看历史趋势。

验收：计分不交给 LLM；PHQ-9 自伤风险立即展示危机干预；答案与报告可恢复、可导出、可审计。

### 3.3 五大处方

对话采集信息 → 字段完整性检查 → 本地证据检索 → 生成严格 JSON → 格式、内容、医学安全、循证四重校验 → 右侧预览 → 医生编辑/批准/拒绝 → PDF/Word/Markdown/TXT 导出。

验收：结构严格匹配权威模板；药物调整属于高风险操作，未经医生审批不能标为可执行处方。

### 3.4 用药审查

录入药物及剂量 → 标准化 → DDI、Beers、剂量、重复用药确定性规则 → 证据与风险分级 → LLM 仅负责通俗解释 → 医生复核。

验收：规则命中、版本和来源可追踪；LLM 不得覆盖确定性规则结论。

### 3.5 文档与多模态

上传 → MIME/大小/恶意内容校验 → MinerU 任务 → 解析状态流 → Markdown schema 校验 → 作为会话文件上下文或进入知识库 → 失败重试/删除。

验收：不返回模拟解析结果；文件内容按 PHI 处理；浏览器只看到安全的任务状态和授权内容。

### 3.6 账号与医生审批

注册/登录 → 角色固定 → 会话/画像/报告持久化 → 高风险动作生成 ASK 决策 → 医生批准、修改或拒绝 → 审计记录与通知。

验收：登录页始终是入口，访客可选择匿名进入患者端体验受限核心功能；账号模式不可切换越权角色；所有审批动作有 actor、时间、理由和版本。

## 4. 功能需求

### 4.1 Development Harness

- `DEV-01` 权威文档、exec-plan、迁移、格式、lint、类型、测试、覆盖率、安全扫描、构建和 Docker 门禁可由统一命令真实执行。
- `DEV-02` 测试分 unit/integration/external/e2e，外部付费调用显式 opt-in；真实依赖使用隔离数据库和 namespace。
- `DEV-03` 每个里程碑保留命令、版本、结果、浏览器证据和独立审阅结论；重复缺陷转为测试或规则。
- `DEV-04` 模块均具有 Protocol、生产实现、README、schema、失败语义和最小必要测试。
- `DEV-05` 每个里程碑和长任务明确 owner、审阅者、时间/调用/成本预算、checkpoint 与恢复入口；无 owner 的待办不能进入执行。

### 4.2 Runtime Agent Harness

- `RUN-01` AgentScope 驱动 ReAct/工具循环，支持上下文组装、模型主备、SSE、取消和原子终态。
- `RUN-02` PermissionEngine 对工具和高风险动作返回 ALLOW/DENY/ASK；ASK 必须进入可恢复的 HITL 状态。
- `RUN-03` 工具注册表只暴露 allowlist 中的 schema 化工具；参数、结果、超时、大小和引用均 fail closed。
- `RUN-04` Trace 覆盖输入、安全决策、模型、工具、Skill、引用、审批、输出、失败和耗时，不保存 Chain-of-Thought 或明文 PHI。
- `RUN-05` 支持普通模式和 CGA workflow；多智能体复核必须保留主回答与复核意见的责任边界。
- `RUN-06` 长任务保存版本化 checkpoint、幂等 key、已完成步骤和外部副作用凭证；重放不得重复工具、审批、消息或计费操作。
- `RUN-07` 每轮执行具有模型 token、工具次数、wall-clock、外部调用和输出大小预算；超限生成稳定失败 Trace，不靠进程无限等待。

### 4.3 智能能力模块

- `AI-01` RAG 对本地 436 份知识文档做增量索引、混合检索、重排、引用和 generation fencing。
- `AI-02` Memory 提供加密短期记忆、跨会话健康画像、用户证据约束、冲突/否定处理与无 PHI 向量 payload。
- `AI-03` Skill 支持四个内置 Skill、声明式自定义 Markdown/ZIP、自然语言草稿、版本、会话加载、AgentScope viewer 和安全策略。
- `AI-04` Search 以 AnySearch 为主、Tavily 兜底，支持搜索/批量/垂直/URL 提取，隔离不可信网页证据。
- `AI-05` Voice 提供真实 ASR/TTS service、格式校验、超时/取消、PCM16 流和浏览器权限降级。
- `AI-06` Privacy 提供 PHI/凭证脱敏、输入注入过滤、输出诊断/红旗/自伤策略和统一免责声明。
- `AI-07` Document 提供真实 MinerU 客户端、上传/URL 任务、状态轮询、Markdown 结果和会话绑定。
- `AI-08` 模型、embedding、rerank、ASR/TTS、Search 和 MinerU adapter 都声明 provider capability/version；不兼容响应不得静默兼容或降级为无校验 dict。

### 4.4 临床功能

- `CLN-01` CGA 量表、答案、计分、报告、历史与医生工作区全部由后端合同持久化；计分确定性。
- `CLN-02` 五大处方按权威模板输出结构化 JSON，完成信息采集、四重校验、证据、版本、导出和医生审批。
- `CLN-03` 用药审查覆盖 DDI、Beers、剂量和重复用药，规则集可版本化、可追踪、可测试。
- `CLN-04` 健康画像显示基本信息、过敏史、用药、疾病/重大事件、CGA 与处方历史，支持用户确认/退役事实。
- `CLN-05` 量表、处方模板、DDI/Beers/剂量和医疗安全规则均版本化，报告保存所用规则版本、证据日期和重新评估提示。
- `CLN-06` 风险预警统一接收红旗症状、CGA 自伤/跌倒/营养风险、慢病指标异常和用药高风险事件，按版本化规则分级、解释、通知、确认与升级；紧急事件立即就医，不由 LLM 自行降级。
- `CLN-07` 慢病管理提供经确认的疾病清单、个体化目标、测量/用药/生活方式计划、趋势、依从性、提醒和异常升级闭环；所有目标与建议有证据和医生责任边界，不以健康画像展示冒充管理。
- `CLN-08` 情感陪伴提供尊重、非欺骗的支持性对话和孤独/痛苦信号识别；禁止诱导依赖、冒充人类或替代专业关系，遇自伤/虐待/急性精神危机立即进入危机干预与人工升级，并允许用户关闭陪伴记忆。

### 4.5 账号、权限与数据

- `IAM-01` 支持访客、患者、医生账号的注册、登录、退出、密码变更和短期/刷新会话；密码使用强哈希。
- `IAM-02` tenant/actor/user/role/ownership 在数据库、缓存、向量库、API 和日志全链路隔离。
- `IAM-03` 会话、消息、文件、报告、审批、反馈、Trace 与 Bad Case 持久化；敏感列 AES-GCM 加密。
- `IAM-04` 所有外部 URL、Key、模型、协议、阈值由环境变量配置；生产配置拒绝 placeholder 和不安全默认值。
- `IAM-05` 患者授权支持授予、到期、撤回和医生最小范围访问；撤回后缓存、下载链接和后续查询立即失效。
- `IAM-06` 管理/审计能力与临床能力分离；生产不得存在万能 scope、前端声明角色或仅 UI 隐藏的授权控制。

### 4.6 前端体验

- `UI-01` 三栏可折叠布局覆盖 desktop/tablet/mobile；右侧面板承载 Skill、文档、引用、CGA、处方、用药和画像。
- `UI-02` 输入框支持文本、点击式语音、图片、最多 10 个文件、Skill、处方、评估、Enter/Shift+Enter 和停止。
- `UI-03` SSE 映射 thinking/tool/result/text/done/error/cancelled/HITL，所有运行态都有终态和恢复操作。
- `UI-04` 患者老年模式正文≥18px、控件≥48px、AAA 高对比、图标有文字/ARIA、reduced motion；医生端保持专业密度。
- `UI-05` 所有医疗输出常驻免责声明；引用可点击；红旗/自伤/高风险审批视觉优先级最高。
- `UI-06` 对话、CGA、处方支持 PDF、Word、Markdown、TXT，图片导出仅作为附加格式。
- `UI-07` API/schema 版本不兼容、checkpoint 恢复、审批等待、数据删除和授权撤回都提供明确用户状态，不允许白屏或无限 loading。

### 4.7 质量、可观测与交付

- `OPS-01` readiness 检查数据库、Redis、Qdrant、RAG generation 和必要模型配置；失败返回 503。
- `OPS-02` 结构化日志、Prometheus 指标、Trace 查询、用户赞踩/文字反馈、Bad Case 收集与 eval 回放可用。
- `OPS-03` unit 与 integration 覆盖率≥80%，关键医疗规则与安全边界 100% 分支覆盖；负向覆盖率门禁必须非零退出。
- `OPS-04` ≤10 并发下验证会话隔离、幂等、限流、取消、连接池和无竞争写入；报告 p50/p95/失败率。
- `OPS-05` Docker 镜像、compose migration、healthcheck、非 root、资源限制、持久卷和环境模板全部可运行。
- `OPS-06` 故障注入覆盖模型断流、Provider 429/5xx、Redis/DB/Qdrant/MinerU 中断、lost acknowledgement、取消竞争和重启恢复。
- `OPS-07` 锁文件、依赖扫描、镜像 digest、SBOM/许可证和高风险依赖升级策略可审计；CI action 与工具版本固定。
- `OPS-08` 提供从单机 10 并发到千级用户/请求规模的容量模型、瓶颈、水平扩展、队列/背压、成本和压测计划；无压测不得声明已支撑千级。

### 4.8 Security Evaluation 与数据生命周期

- `SEC-01` 发布前执行 prompt injection、越权、SSRF、上传炸弹、恶意文档/网页/Skill、PHI 泄露和医疗误导 red-team，并将复现样本进入 eval/Bad Case。
- `SEC-02` 安全评测同时覆盖模型输入、工具参数、工具结果、SSE、导出文件、日志、Trace、metrics、错误响应、缓存和向量 payload 的外泄检测。
- `SEC-03` 第三方 Provider、Python/npm 依赖、容器基础镜像和 GitHub Actions 有威胁模型、最小权限、版本固定、漏洞响应和替换策略。
- `SEC-04` 身份、scope、tenant、actor、role、ownership、CSRF/CORS/SSRF 和 rate-limit 必须在服务端边界验证；UI 或 prompt 不能承担安全控制。
- `DATA-01` 所有跨模块合同使用统一 Pydantic/Zod schema，包含稳定错误码、schema version、兼容窗口、迁移策略和 unknown-field 策略。
- `DATA-02` 每类会话、PHI、文件、音频、报告、Trace、反馈和 Bad Case 定义保留期、用户导出、删除/匿名化、legal hold 和备份清除策略。
- `DATA-03` PHI 外发遵循目的限制与最小化：发送 Provider 前脱敏并记录类别/目的/处理方，不记录原文；用户可查看数据用途与撤回后续处理。
- `DATA-04` 建立字段级数据分类注册表，至少区分公开、内部、标识符、PHI、凭证和高敏临床数据；每个 schema 字段绑定敏感度、允许处理方、存储/日志/Trace/vector/export 规则和保留策略。
- `DATA-05` 跨服务主体使用可轮换假名或 token；真实身份映射单独加密、最小授权、双人/审批式受控再识别并留审计，匿名化数据必须通过重识别风险评估。
- `DATA-06` 脱敏规则、检测模型、allowlist 和例外均版本化；以含中英文、OCR、音频转写、自由文本和结构化字段的 canary/golden 集评测误报、漏报和回归，漏检高敏数据阻止发布。

## 5. 非功能指标

| 维度 | 发布要求 |
|---|---|
| 可用性 | 核心依赖不可用时明确 503/稳定错误码；无静默降级或假成功 |
| 延迟 | 本地非模型 API p95≤500ms；RAG 检索 p95≤3s；模型首事件有可见反馈；具体基线记录在性能报告 |
| 并发 | 单机至少通过 10 并发验收；更大容量只在压测证据存在时声明 |
| 安全 | JWT 固定算法、最小 scope、CSRF/CORS/SSRF/上传防护、密钥不入包、PHI 加密与脱敏 |
| 无障碍 | 键盘路径、语义标签、焦点可见、患者模式 WCAG AAA 目标、reduced motion |
| 兼容性 | 当前 Chrome/Edge/Safari；desktop/tablet/mobile 核心旅程可用 |
| 可维护性 | Python strict mypy/Ruff；TypeScript strict/ESLint；边界 Pydantic/Zod；迁移可升级和回滚 |

## 6. 数据与信任边界

浏览器、上传内容、模型输出、搜索网页、MinerU、向量库 payload、缓存和所有外部 API 都是不可信边界。任何数据进入业务层前必须：认证/授权 → 大小/格式限制 → schema → 内容安全 → 归属校验。任何数据离开业务层前必须：最小披露 → PHI/密钥脱敏 → 输出 schema → 医疗安全 → 审计。

禁止存储或展示模型隐藏 Chain-of-Thought；只展示简短 reasoning summary、工具状态和证据。

## 7. 发布验收

发布必须同时满足：

1. [需求矩阵](REQUIREMENTS_MATRIX.md) 无 `未实现` 或无证据的 `部分实现`。
2. Ruff format/check、mypy、pytest、覆盖率、安全扫描、Alembic、MVP lint/build、浏览器 E2E 全部通过。
3. 真实 LLM/ASR/TTS/Embedding/Rerank/Search/MinerU 至少各有一次成功和一次故障语义证据，未配置服务有清晰降级。
4. Docker 从空卷启动、迁移、索引/readiness、核心旅程、重启持久化全部通过。
5. 独立审阅者复现医疗安全、权限隔离、适老化、≤10 并发和核心 E2E 后给出 PASS。

## 8. 当前事实基线

截至 2026-07-15，Agent Harness、RAG、Memory、Search、Skill、Trace、访客 BFF 已有生产实现和真实证据；CGA、五大处方、用药审查、Document、Voice 后端、账号/RBAC/HITL、反馈/eval/Bad Case 和最终 Docker 联调仍有缺口。旧前端中的 `mock` 文案或本地模拟不得作为完成证据。准确状态只见需求矩阵和活跃 exec-plan。
