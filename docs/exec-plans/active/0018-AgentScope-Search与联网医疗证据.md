# 0018-AgentScope Search 与联网医疗证据 — 执行计划

> 任务编号：0018 | 创建日期：2026-07-15 | 优先级：P0 | 阶段：二（核心引擎）

## 1. 权威要求与现状

- 最高权威 `docs/references/gerclaw设计要求.md` §4.10、§10、§11、§12、§16.2 要求可替换的 `SearchModule`、AnySearch JSON-RPC 2.0 主通道、Tavily 自动降级、来源 URL/发布时间和“本地知识库 > 联网搜索 > 模型知识”的证据顺序。
- 产品规格要求 Agent 自主判断时效性问题并调用 `web_search`，搜索结果按独立卡片和引用展示；CGA 期间必须禁用联网搜索；网页内容必须视为不可信数据并防 prompt injection。
- 当前后端 `tools` 只有 Protocol，AgentScope Toolkit 只有 RAG/Memory；前端 Next Route 直接持有搜索密钥，AnySearch 还错误调用 `/v1/search`，没有租户权限、Trace、权威分级、PHI 脱敏或 SSRF 边界。
- 用户要求调试只使用仓库根 `.env` 中的真实 AnySearch/Tavily 服务，禁止 mock 成功路径。

## 2. 技术决策

1. 实现 async `ProductionSearchModule`，Provider 只负责强类型协议适配，路由层负责重试、主备切换、去重、权威分级和 D 级来源过滤；所有客户端可注入并可独立替换。
2. AnySearch 必须优先使用，严格按 `tools/call` 调用 `search`/`extract`；网络错误、超时、限流、服务端错误或响应 schema 失败最多重试一次，然后才降级 Tavily。无效凭证等不可重试错误直接降级。双通道失败必须 fail closed，不允许伪造结果或退回模型记忆冒充最新证据。
3. 搜索 query 在出边界前做确定性 PHI 脱敏；Provider、Trace、日志和指标只保存 query HMAC、长度、Provider、结果数、权威级别、URL host HMAC 等低敏元数据，不保存原始 query、snippet 或正文。
4. 搜索结果是“不可信的外部证据”，以结构化 DTO、显式 `<untrusted-web-evidence>` 隔离和稳定 `[W1]` 引用进入 AgentScope。网页中的指令永远不能升级为 system/tool 指令；临床事实仍必须优先由本地 RAG 支撑。
5. 来源权威等级按固定域名/机构 allowlist 归类：政府、WHO/FDA/NIH/PubMed 为 S；NICE/AHA/NCCN/权威学会和期刊为 A；专业平台为 B；通用站点为 C；广告、论坛和无法形成可追溯 HTTPS 来源的结果为 D 并过滤。分级是检索排序信号，不替代人工循证评价。
6. `extract_content` 只接受公网 HTTPS URL；解析前和每次重定向都阻断 loopback、private、link-local、multicast、保留地址和云 metadata，限制响应体/字符数，Provider 只收到已校验 URL，避免 SSRF 和资源耗尽。
7. `/api/v1/search` 使用独立 `search:read` scope、租户/用户限流、幂等 Trace 和稳定错误码；对话内 `web_search` 复用同一个模块，Trace 记录每次 Provider attempt 和最终结果，不旁路审计。
8. Search runtime 作为应用级无状态共享 async client，连接池有界并在 lifespan 关闭；不缓存包含搜索正文的数据。CGA context 不注册搜索工具，普通 Chat 才注册。
9. 前端移除直接外部搜索和浏览器密钥依赖，搜索卡片消费后端 SSE/结构化结果；根 `.env` 是唯一真实服务配置源，`.env.example` 只保留后端变量模板。

## 3. 实现范围

1. 增加 Search DTO/Protocol、AnySearch/Tavily provider、统一 router、PHI query sanitizer、authority classifier、SSRF URL validator 和 runtime lifecycle。
2. 提供 `search()` 与 `extract_content()` 生产实现，覆盖超时重试、降级、schema 校验、去重、限制和稳定错误分类。
3. 将 `web_search` 注册到 AgentScope Toolkit，加入时效性触发 prompt、结果隔离、引用捕获和 SSE 搜索卡片事件；维持本地 RAG 优先和 CGA 禁用约束。
4. 增加 `/api/v1/search/query` 与 `/api/v1/search/extract`，实现认证、权限、限流、Trace、指标、错误映射和无 PHI 日志。
5. 前端移除浏览器侧 Provider 配置；二阶段后端和 Agent 对话统一走 `SearchModule`，MVP 旧 Route 暂以 `server-only` 兼容适配器复用相同 AnySearch-first 协议，等待访客 JWT/BFF 接入后切换 GerClaw API；对话 UI 复用现有工具/结果卡片。
6. 增加单元、API、AgentScope、真实依赖和根 `.env` 外部测试，真实覆盖 AnySearch 主通道、Tavily 直连、强制 fallback 和内容提取。
7. 更新 Search/API/架构/安全/可靠性与环境模板文档，记录证据等级、隐私和故障边界。

## 4. 验收标准

- [x] `SearchModule.search` 和 `extract_content` 都有生产实现、严格 DTO、独立 provider 注入和失败路径测试，模块覆盖率不低于 80%。
- [x] AnySearch 使用 `/mcp` JSON-RPC 2.0 且永远优先；可重试失败只重试一次，随后自动切换 Tavily；双通道失败返回稳定 503，不产生伪成功。
- [x] 原始 query、搜索正文、用户标识和 Provider key 不进入 Trace、指标、日志或错误响应；明显 PHI 在发送外部服务前已脱敏。
- [x] 搜索结果有有效 HTTPS URL、来源、发布时间（缺失时明确为 `null`）、S/A/B/C 级和 provider；D 级、重复、无效 schema 结果被过滤。
- [x] `extract_content` 阻断 localhost、私网、云 metadata、DNS rebinding 和恶意 redirect，并限制响应体与正文长度。
- [x] AgentScope 对时效性/用户明确搜索请求可调用真实 `web_search`，工具结果被不可信边界隔离，SSE 提供可渲染搜索结果与 `[Wn]` 引用；CGA context 无法调用该工具。
- [x] 前端不再读取 `NEXT_PUBLIC_ANYSEARCH_API_KEY`/`NEXT_PUBLIC_TAVILY_API_KEY`，浏览器不直连 Provider，既有搜索卡片、引用和适老化交互继续工作。
- [x] 根 `.env` 的 AnySearch、Tavily 和真实 Agent 模型完成端到端测试，无 mock 成功路径；测试证据说明实际 provider、fallback 和响应 schema。
- [x] Ruff format/check、mypy、Bandit、pip-audit、全量 pytest、Docker build/health、MVP lint/build 全部通过。
- [ ] 独立审阅者复现权限、隐私、SSRF、fallback、AgentScope 真实工具调用和前端关键链路并给出 PASS 后提交归档。

## 5. 验收记录（2026-07-15）

- 后端静态与全量回归：Ruff format/check、mypy 均通过；`269 passed, 25 skipped`，总覆盖率 `81.52%`，Search 核心文件为 83%–100%。
- 真实基础设施集成：PostgreSQL/Redis/Qdrant 下 `285 passed, 9 deselected`，总覆盖率 `88.42%`；Search API 权限、Trace、PHI 脱敏和 SSRF 拒绝均落到真实数据库。
- 根 `.env` 外部服务：`9 passed`，真实执行 AnySearch search/extract、强制 AnySearch 故障后的 Tavily search/extract、AgentScope 模型自主 `web_search`、RAG、Memory 和模型降级链。
- 安全：Bandit 无发现；pip-audit 无已知漏洞（仅本地 `gerclaw-api` 包不在 PyPI，按工具规则跳过）；API 日志中未出现验收查询原文。
- Docker：初次两次因外部下载超时失败并如实保留；增加 BuildKit `uv` cache 与有界 timeout/retry 后镜像成功。迁移完成，容器 healthy，`/health/ready` 返回 Search AnySearch/Tavily ready、本地知识库 436 文档/39,837 chunks、AgentScope 2.0.4 全绿。
- Docker 真实 API：短期 `search:read` JWT 调用返回 HTTP 200、3 条 AnySearch 结果（S/C 级），Trace `completed` 且持久化 `search.query/succeeded` 事件。
- 前端：ESLint 与 Next production build 通过；构建只加载根 `.env` 的服务端变量，Search Route 请求边界使用 Zod，Provider key 未进入浏览器配置。

## 6. 明确不在本变更集内

- 不实现 CGA 业务状态机本身；本轮提供可显式关闭 Search Toolkit 的 context 开关，完整 CGA 在后续里程碑接入。
- 不实现 Search Redis 正文缓存、跨请求搜索结果持久化或通用网页浏览器；这些会扩大隐私和版权数据面。
- 不实现完整 Skill 注册中心、语音、文档解析、处方或用药审查；它们后续复用 SearchModule 和 Tool Policy。
- 不声称已达到万级并发；本轮保证 async、有界连接/重试/输出和无用户进程态，最终容量由系统级负载测试证明。
