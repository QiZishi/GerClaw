# ARCHITECTURE.md

> 系统架构总览 | 基于PRD.md生成

---

## 1. 系统目标

GerClaw是面向老年患者与老年科医生的Web端AI双向诊疗平台：
- **MVP阶段（一阶段）**：纯前端Next.js 15静态导出，部署在IGA Pages，核心功能闭环可演示可体验，所有外部API（LLM/ASR/TTS/搜索/MinerU）前端直连
- **二阶段（生产）**：平滑迁移到前后端分离架构（Next.js + FastAPI + AgentScope多智能体），Docker部署到ModelScope，支持企业级生产使用

核心价值：语音优先适老化交互、专业CGA老年综合评估、五大处方体系、医患双向诊疗、医疗安全底线保障。

## 2. 数据流图

### MVP阶段数据流（纯前端）

```
用户（老年患者/医生）
    ↓ (浏览器)
Next.js 15 前端 (App Router, 静态导出)
├── UI层 (app/ + components/shadcn/ui + Tailwind CSS 4)
├── 状态层 (Zustand + React Context, localStorage持久化)
├── Hooks层 (hooks/ - 封装可复用逻辑)
└── API Client层 (services/ - 统一封装外部API调用)
         ↓ (HTTPS)
    ┌────┼────────┬──────────┬─────────┐
    ↓    ↓        ↓          ↓         ↓
  LLM   ASR      TTS      Search    MinerU
(GPT-4o (Mimo   (Mimo   (AnySearch/ (文档解析
主模型, ASR)   TTS)   Tavily)   云API)
qwen等
备份模型)
```

### 二阶段数据流（全栈）

```
用户
    ↓
Next.js前端 (SSR/SSG)
    ↓ (HTTPS)
FastAPI后端
├── API Routes (routes/)
├── Service层 (services/ - 业务逻辑)
├── AgentScope多智能体编排
│   ├── 全科医生智能体
│   ├── 老年专科医生智能体（复核）
│   ├── 用药审查智能体（规则引擎+LLM）
│   └── CGA评估智能体（状态机骨架+LLM柔性层）
├── Repository层 (repositories/)
│   ├── PostgreSQL (用户/会话/健康档案)
│   ├── Redis (缓存/限流/会话)
│   └── Qdrant (RAG向量检索)
└── Providers层
    ├── LLM Provider (GPT-4o/qwen/claude)
    ├── Voice Provider (Mimo ASR/TTS)
    ├── Search Provider (AnySearch/Tavily)
    └── MinerU Provider (文档解析)
```

## 3. 推荐技术栈

### 3.1 MVP阶段（纯前端）

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|---------|
| 前端框架 | Next.js | 15 (App Router) | React生态成熟，支持SSG静态导出适配IGA Pages部署 |
| UI库 | React | 18+ | 组件化开发，生态丰富 |
| 样式 | Tailwind CSS | 4 | 原子化CSS，快速构建适老化UI，主题切换方便 |
| 组件库 | shadcn/ui | latest | 高质量基础组件，可定制，符合现代设计品味 |
| AI SDK | Vercel AI SDK | latest | 流式输出封装、多模型调用统一接口、SSE支持好 |
| 状态管理 | Zustand + React Context | latest | Zustand轻量适合会话/配置状态，Context适合跨组件主题/角色状态；localStorage持久化 |
| 类型校验 | Zod | latest | 运行时schema校验，API请求/响应、环境变量、表单验证 |
| 语音录制 | MediaRecorder API | 浏览器原生 | 麦克风录音WAV/MP3，无额外依赖 |
| 音频播放 | Web Audio API | 浏览器原生 | PCM16流式播放TTS |
| 文档导出 | jsPDF + docx.js | latest | 前端导出PDF/Word，无需后端 |
| 部署平台 | IGA Pages | - | 静态网站托管，支持环境变量注入API Key |

### 3.2 二阶段（全栈生产）

| 层级 | 技术 | 版本 | 选型理由 |
|------|------|------|---------|
| 前端 | Next.js | 15 | 同MVP，支持SSR/SSG |
| 后端 | FastAPI | latest | Python高性能异步API，与AgentScope同技术栈 |
| 智能体框架 | AgentScope | latest | 多智能体编排、工具调用、记忆管理、权限引擎，已有医疗参考实现 |
| 关系数据库 | PostgreSQL | 16 | 用户数据、会话记录、健康档案，JSONB支持灵活 schema |
| 缓存 | Redis | 7+ | 会话缓存、限流、热数据缓存、状态持久化 |
| 向量数据库 | Qdrant | latest | RAG知识库向量存储与检索 |
| 嵌入模型 | BAAI/bge-m3 | SiliconFlow API | 多语言文本向量化 |
| 重排模型 | BAAI/bge-reranker-v2-m3 | SiliconFlow API | 检索结果精排 |
| 部署 | Docker + ModelScope Studio | - | 容器化全栈部署，环境一致 |

## 4. 目录结构

### MVP阶段目录结构

```
gerclaw-main/
├── apps/
│   └── mvp/                    # MVP前端应用（纯前端）
│       └── src/
│           ├── app/            # Next.js App Router (页面/路由/layout/loading/error)
│           │   ├── (patient)/  # 患者端路由组
│           │   ├── (doctor)/   # 医生端路由组
│           │   └── layout.tsx
│           ├── components/     # React组件（按功能模块组织）
│           │   ├── chat/       # 通用对话组件
│           │   ├── voice/      # 语音交互组件
│           │   ├── prescription/ # 五大处方组件
│           │   ├── cga/        # CGA评估组件
│           │   ├── drug-review/ # 用药审查组件
│           │   ├── search/     # 联网搜索组件
│           │   ├── skills/     # 技能管理组件
│           │   ├── document/   # 文档解析组件
│           │   ├── layout/     # 三栏布局/侧边栏/右侧面板
│           │   ├── theme/      # 主题切换
│           │   ├── role/       # 角色切换
│           │   └── ui/         # shadcn/ui基础组件
│           ├── hooks/          # 自定义React Hooks
│           ├── context/        # React Context (主题/角色/对话状态)
│           ├── services/       # API Client层（统一封装外部API）
│           │   ├── llm/        # LLM API封装（openai/dashscope/anthropic协议）
│           │   ├── voice/      # ASR/TTS API封装
│           │   ├── search/     # AnySearch/Tavily搜索封装
│           │   ├── document/   # MinerU文档解析封装
│           │   └── api-client.ts # 统一API客户端基类（超时/重试/降级/熔断）
│           ├── lib/            # 工具函数/常量/配置加载
│           │   ├── config.ts   # 环境变量加载与Zod校验
│           │   ├── storage.ts  # localStorage封装
│           │   └── utils.ts
│           ├── stores/         # Zustand状态 stores
│           ├── types/          # TypeScript类型定义（零依赖）
│           ├── data/           # 静态数据（量表题库、DDI规则、Beers标准等）
│           │   └── mock/       # Mock 数据（仅第一阶段使用，第二阶段删除）
│           └── styles/         # 全局样式/Tailwind配置
├── docs/                       # 文档体系
│   ├── product-specs/          # 产品功能规范
│   ├── design-docs/            # 技术设计文档
│   ├── references/             # 参考资料
│   ├── exec-plans/             # 执行计划
│   │   ├── active/
│   │   └── completed/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── RELIABILITY.md
│   └── ...
└── AGENTS.md
```

### 二阶段目录结构（演进方向）

```
gerclaw-main/
├── apps/
│   ├── mvp/                    # MVP代码归档保留（只读参考）
│   ├── web/                    # Next.js前端（SSR/SSG）
│   └── api/                    # FastAPI后端
│       └── src/
│           ├── routes/         # API路由
│           ├── services/       # 业务逻辑层
│           ├── agents/         # AgentScope智能体定义
│           ├── repositories/   # 数据访问层
│           ├── providers/      # 外部服务封装
│           └── types/
├── packages/                   # 共享包（类型定义、工具函数）
└── docs/
```

## 5. 分层依赖

严格依赖方向（MVP前端）：

```
types → lib(config/storage/utils) → services(API Client) → stores/context → hooks → components → app
data → services/components
```

- **types/**：纯TypeScript类型定义和interface，零依赖
- **lib/**：工具函数、配置加载、localStorage封装，依赖types
- **data/**：静态数据（量表、规则等），无依赖或仅依赖types
- **services/**：API Client层，依赖types+lib，封装所有外部API调用（超时/重试/降级/熔断逻辑在这里实现）
- **stores/ + context/**：状态管理层，依赖types+lib+services
- **hooks/**：自定义Hooks，依赖types+lib+services+stores
- **components/**：React组件，依赖types+lib+hooks+stores+services
- **app/**：Next.js页面路由，依赖components+context

**二阶段后端分层依赖**：
```
types → config → providers → repositories → services → agents → routes(FastAPI)
```

**禁止**：反向依赖、跨层直接依赖、循环依赖。components不能直接import app里的东西；services不能依赖components/hooks。

## 6. 数据边界

| 信任边界 | 校验要求 |
|---------|---------|
| 用户文本输入 | Zod schema校验、长度限制（单次≤4000字符）、XSS防护（React自动转义） |
| 用户文件上传 | 类型校验（PDF/Word/图片/文本）、大小限制（≤10MB）、MinerU解析结果加隔离标记 |
| 语音录音输入 | 格式校验（WAV/MP3）、时长限制、仅存内存不持久化 |
| 角色切换 | 纯前端UI切换，无后端权限（MVP阶段），二阶段后端校验RBAC |
| localStorage数据 | 读取时try-catch+schema校验，损坏时清除并提示用户 |
| 外部LLM输出 | 后处理检查：确定性诊断用语拦截、有害内容检测、免责声明附加、结构化输出schema验证 |
| 联网搜索结果 | 加隔离标记（BEGIN/END SEARCH RESULT包裹），剥离指令性文字，来源角标可追溯 |
| 技能内容(skill.md) | 加载前安全检查，禁止包含修改系统角色的指令 |
| 外部API响应 | Zod schema校验、超时处理、错误捕获、主备切换 |
| 环境变量 | 启动时Zod校验，缺失关键变量直接失败不启动 |

## 7. Agent-Legible Invariants

智能体必须保留的架构不变量：

1. **所有外部API调用通过services/层封装**：禁止组件直接fetch外部API，必须走统一API Client以统一实现超时/重试/降级/熔断/trace_id
2. **环境变量经lib/config.ts Zod校验后使用**：禁止直接读取process.env，必须从config模块导入类型安全的配置对象
3. **用药审查100%确定性规则引擎**：DDI/Beers/剂量检查必须用确定性规则（data/中的规则数据），不依赖LLM判断，LLM只负责结果解读和建议生成
4. **CGA/五大处方"状态机骨架+LLM柔性层"混合架构**：评估流程、量表计分、处方结构由代码状态机保证确定性，LLM只负责自然语言对话引导和内容生成
5. **所有医疗输出必经后处理**：输出前必须经过医疗安全检查（确定性诊断拦截+免责声明附加+循证引用检查）
6. **API Client层抽象适配**：services/层的API接口定义要为二阶段迁移后端预留，切换到FastAPI时只需替换实现不修改业务组件
7. **状态管理分层**：Zustand管理跨页面/需要持久化的可序列化状态（会话/配置/侧边栏/右侧面板），React Context管理主题/角色/老年模式等跨组件UI状态；Zustand stores只存可序列化数据，不存组件/函数引用
8. **组件按功能模块组织**：components/下按功能分子目录（chat/voice/prescription/...），不按类型放（buttons/forms/...）
9. **两阶段 Mock 策略**：UI 构建阶段（第一个计划）允许在 `src/data/mock/` 集中放置 Mock 数据用于交互调试；功能实现阶段（第二个计划起）必须删除所有 Mock 数据，所有外部 API 调用必须真实调用模型服务和工具服务

## 8. 关键决策

| 决策编号 | 决策内容 | 原因 | 替代方案 | 日期 |
|---------|---------|------|---------|------|
| ADR-001 | MVP纯前端Next.js静态导出，部署IGA Pages | IGA Pages不支持Python后端运行，纯前端可快速验证核心价值，部署简单 | 直接做全栈→开发周期长，无法快速演示；用其他支持Python的平台→与后续ModelScope部署路径不一致 | 2026-07-04 |
| ADR-002 | 主模型GPT-4o + 国内模型自动降级（qwen-plus等备份） | GPT-4o医疗能力最强，但存在数据出境和网络风险；模型配置完全环境变量化支持一键切换 | 只用国内模型→医疗能力可能不足；只用GPT-4o→网络不稳定风险高 | 2026-07-04 |
| ADR-003 | 语音使用Mimo ASR/TTS（mimo-v2.5-asr/tts，冰糖音色） | Mimo提供OpenAI兼容API，中文识别质量好，支持流式PCM16播放；冰糖音色适合老年用户 | 用OpenAI Whisper/TTS→中文方言支持弱；用其他国内厂商→API协议不统一增加复杂度 | 2026-07-04 |
| ADR-004 | 用药审查100%确定性规则引擎（DDI/Beers/剂量检查） | 用药安全是医疗安全底线，LLM存在幻觉风险不能用于药物相互作用判断；规则引擎结果100%可复现可审计 | 纯用LLM做用药审查→幻觉风险不可接受；规则+LLM各做一半→边界不清难以审计 | 2026-07-04 |
| ADR-005 | CGA评估/五大处方采用"状态机骨架+LLM柔性层"混合架构 | 量表计分、处方结构、评估流程需要确定性保证；自然语言对话引导、健康建议生成需要LLM柔性处理；两者结合兼顾安全和体验 | 纯状态机表单→老年用户体验差不会填表；纯LLM自由对话→计分和结构无法保证准确性 | 2026-07-04 |
| ADR-006 | 两阶段 Mock 策略（UI 阶段允许 mock，实现阶段禁止 mock） | 第一个计划需构建完整可交互 UI 壳子，真实 API 调用会阻塞 UI 开发；第二个计划起逐模块接入真实 API，必须用真实数据验证 | 全程禁止 Mock→UI 开发被 API 调试阻塞；全程允许 Mock→功能实现阶段无法验证真实能力 | 2026-07-05 |
