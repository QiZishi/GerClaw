# FRONTEND.md

> 前端规范 | 基于PRD.md第5节技术栈和gerclaw设计要求.md第2-3节生成

---

## 1. 技术栈

| 类别 | 技术选择 | 版本 | 说明 |
|------|---------|------|------|
| 框架 | Next.js | 16.2.10 (App Router) | React框架；当前使用动态 BFF Route Handler 连接 FastAPI |
| 语言 | TypeScript | 5.x | strict模式启用，全类型覆盖 |
| 样式方案 | Tailwind CSS | 4 | 原子化CSS，深色模式dark:前缀 |
| UI组件库 | shadcn/ui | latest | 基于Radix UI的高质量组件库，按需导入 |
| 图标 | Lucide React | latest | 一致风格的图标库 |
| 状态管理 | Zustand + React Context | latest | Zustand 管理会话/配置等可序列化状态，Context 管理主题/角色等跨组件状态；localStorage 持久化 |
| 路由 | Next.js App Router | 16.2.10 | 文件系统路由与同源 BFF Route Handler |
| 数据获取 | 同源 BFF + fetch + Zod | latest | FastAPI REST/SSE 经 `/api/gerclaw/*` 转发并在信任边界校验 |
| 表单处理 | React Hook Form + Zod | latest | 类型安全的表单验证（设置、技能上传等） |
| 音频处理 | Web Audio API + MediaRecorder | 浏览器原生 | 麦克风录音(WAV/MP3)、PCM16流式播放 |
| 文档导出 | jsPDF + docx + marked | latest | PDF导出、DOCX导出、Markdown渲染 |
| Markdown渲染 | react-markdown + remark-gfm + rehype-highlight | latest | Markdown渲染、GFM表格/任务列表、代码语法高亮 |
| 测试框架 | Vitest + React Testing Library + Playwright | latest | 单元测试/组件测试/E2E测试 |
| 构建工具 | Turbopack build + Webpack dev | Next.js 16.2.10 | 生产 build 使用 Turbopack；本机 dev 固定 Webpack，规避已复现的首次编译挂起 |
| 代码规范 | ESLint + Prettier | latest | Next.js默认ESLint配置 |

## 2. 目录结构

MVP阶段代码位于 `apps/mvp/`：

```
apps/mvp/
├── src/
│   ├── app/                    # Next.js App Router页面
│   │   ├── layout.tsx          # 根布局（三栏结构、主题Provider）
│   │   ├── page.tsx            # 主页面（角色路由分发）
│   │   ├── (patient)/          # 患者端路由组
│   │   │   └── page.tsx
│   │   └── (doctor)/           # 医生端路由组
│   │       └── page.tsx
│   ├── components/             # React组件
│   │   ├── ui/                 # shadcn/ui基础组件（Button/Input/Card/Dialog等）
│   │   ├── layout/             # 布局组件
│   │   │   ├── Sidebar.tsx     # 左侧边栏（导航、会话列表）
│   │   │   ├── ChatArea.tsx    # 中间主聊天区
│   │   │   └── RightPanel.tsx  # 右侧动态面板
│   │   ├── chat/               # 对话相关组件
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── ThinkingBlock.tsx
│   │   │   ├── ToolCallCard.tsx
│   │   │   └── ChatInput.tsx
│   │   ├── voice/              # 语音交互组件
│   │   │   ├── MicButton.tsx
│   │   │   ├── WaveformVisualizer.tsx
│   │   │   ├── AudioPlayer.tsx
│   │   │   └── TTSPlayer.tsx
│   │   ├── prescription/       # 五大处方组件
│   │   │   ├── PrescriptionPanel.tsx
│   │   │   ├── PrescriptionCard.tsx
│   │   │   └── PrescriptionExport.tsx
│   │   ├── cga/                # CGA评估组件
│   │   │   ├── ScaleSelector.tsx
│   │   │   ├── CGAConversation.tsx
│   │   │   ├── CGAReport.tsx
│   │   │   └── DoctorCGAWorkspace.tsx
│   │   ├── drug-review/        # 用药审查组件
│   │   │   ├── DrugInput.tsx
│   │   │   └── DrugReviewResult.tsx
│   │   ├── search/             # 联网搜索组件（工具可视化，无独立页面）
│   │   │   ├── SearchResultCard.tsx
│   │   │   └── CitationPopover.tsx
│   │   ├── skills/             # 技能管理组件
│   │   │   ├── SkillSelector.tsx
│   │   │   ├── SkillManager.tsx
│   │   │   └── SkillTag.tsx
│   │   ├── document/           # 文档解析组件（工具可视化，无独立页面）
│   │   │   ├── FileUpload.tsx
│   │   │   └── DocumentPreview.tsx
│   │   ├── theme/              # 主题切换
│   │   │   └── ThemeToggle.tsx
│   │   ├── role/               # 角色切换
│   │   │   └── RoleSwitcher.tsx
│   │   ├── settings/           # 设置（模型配置、API Key等）
│   │   │   └── SettingsPanel.tsx
│   │   └── export/             # 导出功能组件
│   │       └── ExportDialog.tsx
│   ├── hooks/                  # 自定义Hooks
│   │   ├── useChat.ts          # 对话逻辑（封装Vercel AI SDK useChat）
│   │   ├── useVoice.ts         # 录音/ASR/TTS语音逻辑
│   │   ├── useModelConfig.ts   # 模型配置管理（环境变量+运行时配置）
│   │   ├── useSession.ts       # localStorage会话管理
│   │   ├── useTheme.ts         # 主题切换
│   │   ├── useRole.ts          # 医生/患者角色状态
│   │   └── useSeniorMode.ts    # 老年模式状态
│   ├── services/               # API Client层（统一封装外部API）
│   │   ├── llm/                # LLM API封装（openai/dashscope/anthropic协议）
│   │   ├── voice/              # ASR/TTS API封装
│   │   ├── search/             # AnySearch/Tavily搜索封装
│   │   ├── document/           # MinerU文档解析封装
│   │   └── api-client.ts       # 统一API客户端基类（超时/重试/降级/熔断）
│   ├── lib/                    # 工具函数/常量/配置加载
│   │   ├── config.ts           # 环境变量加载与Zod校验
│   │   ├── storage.ts          # localStorage封装
│   │   ├── utils.ts            # 通用工具（cn等）
│   │   ├── audio.ts            # 音频处理（PCM解码、WAV编码、Web Audio播放）
│   │   ├── export.ts           # 导出PDF/DOCX/Markdown
│   │   ├── markdown.ts         # Markdown处理
│   │   ├── retry.ts            # 重试/熔断/降级逻辑
│   │   ├── format.ts           # 格式化（日期、文件大小等）
│   │   ├── security.ts         # 医疗安全工具函数
│   │   └── constants.ts        # 常量（尺寸、超时时间、默认值）
│   ├── context/                # React Context（主题/角色/老年模式等UI状态）
│   │   ├── ThemeProvider.tsx
│   │   └── AppProvider.tsx
│   ├── stores/                 # Zustand状态 stores（可序列化状态）
│   │   ├── appStore.ts         # 应用状态（侧边栏/右侧面板/角色/老年模式）
│   │   ├── chatStore.ts        # 对话状态（会话/消息）
│   │   └── sessionStore.ts     # 会话持久化（localStorage中间件）
│   ├── types/                  # TypeScript类型定义
│   │   ├── chat.ts             # 消息、会话、模型配置类型
│   │   ├── api.ts              # API请求/响应类型
│   │   ├── prescription.ts     # 五大处方类型
│   │   ├── cga.ts              # CGA量表、评估结果类型
│   │   ├── drug.ts             # 用药审查类型
│   │   └── voice.ts            # 音频/语音类型
│   ├── prompts/                # 系统Prompt模板
│   │   ├── system-doctor.md    # 老年专科医生系统prompt
│   │   ├── cga.md              # CGA评估prompt
│   │   ├── prescription.md     # 五大处方生成prompt
│   │   └── drug-review.md      # 用药审查prompt
│   ├── data/                   # 静态数据
│   │   ├── scales/             # CGA量表题目数据（5个量表JSON）
│   │   ├── skills/             # 预置技能定义
│   │   ├── beers-criteria.ts   # Beers标准数据（简化版内置）
│   │   └── mock/               # Mock数据（仅第一阶段使用，第二阶段删除）
│   └── styles/                 # 全局样式/Tailwind配置
├── public/                     # 静态文件
├── next.config.js              # Next.js配置（静态导出output: 'export'）
├── tailwind.config.ts          # Tailwind配置（主题色、老年模式字号）
├── tsconfig.json               # TypeScript配置
├── package.json                # 依赖和脚本
└── .env.example                # 环境变量模板
```

当前可运行的 Web 前端以 `apps/mvp/` 为唯一实现入口，并通过同源 BFF 整合 `apps/api/`；`apps/web/` 仍为空的二阶段预留目录，未承载任何产品功能，禁止复制一套模拟页面到其中。

## 3. 组件规范

- 组件命名：PascalCase（如 `MessageBubble.tsx`、`PrescriptionCard.tsx`）
- 一个文件一个主组件
- Props使用TypeScript interface定义，导出interface
- 优先使用函数组件和Hooks，不使用class组件
- UI组件优先从shadcn/ui导入，不重复造基础轮子
- 业务组件通过组合shadcn/ui组件构建
- data-testid用于需要被测试/智能体访问的关键元素
- 组件props按：data props → callback props → ref/children 排序
- 复杂组件拆分子组件，单文件不超过250行
- 所有交互元素有hover/active/focus/disabled状态样式

## 4. 状态管理规范

- **服务器状态**：使用Vercel AI SDK的useChat/useCompletion管理流式对话状态，不手动缓存
- **客户端全局状态**：优先使用 Zustand 管理跨页面/需持久化的状态（会话/配置/侧边栏/右侧面板）
- **跨组件 UI 状态**：使用 React Context 管理主题/角色/老年模式等 UI 状态
- **局部状态**：useState/useReducer，不提升到全局
- **持久化状态**：Zustand stores 通过 localStorage 中间件持久化
- **表单状态**：React Hook Form + Zod schema 验证
- Zustand stores 只存可序列化数据，不存组件/函数引用

## 5. API调用规范

- 所有外部API调用封装在 `src/services/` 层，组件不直接调用fetch
- 请求/响应使用TypeScript类型定义
- 统一错误处理：services层抛出带类型的错误，hooks层catch后转换为用户友好消息
- 统一超时：每个API调用通过AbortController设置超时（见RELIABILITY.md超时策略）
- 重试逻辑：services层实现指数退避重试（可重试错误才重试）
- 主备切换：llm.ts实现主→备1→备2自动切换；search.ts实现AnySearch→Tavily兜底
- API Key从环境变量读取，经src/lib/config.ts校验后使用，不在组件中直接process.env
- 流式响应：使用Vercel AI SDK处理SSE流（LLM），手动处理ReadableStream（ASR/TTS）
- 关键操作添加AbortController支持；用户停止生成先走显式后端取消协议，AbortController 仅作为取消端点失败或页面卸载时的 transport 兜底。

### 5.1 当前生产链路（0019）

- 普通聊天、Skill CRUD/生成/上传、会话 Skill 选择统一走 `src/services/gerclaw/`，组件不得拼接 Skill prompt 或直连 Provider。
- `src/app/api/gerclaw/[...path]/route.ts` 只代理显式 allowlist 路径；访客 JWT 放在 HttpOnly/SameSite cookie，浏览器 JavaScript 不读取 token。
- 浏览器在任何 BFF 请求前同步生成并持久化 32 位 visitor ID，同时随请求头发送；BFF 首次响应再写 HttpOnly visitor/JWT cookie。并发首请求因此使用同一身份输入，不会各自产生 actor A/B。独立 `GERCLAW_GUEST_IDENTITY_SECRET` 只在 BFF/FastAPI 间签名并稳定派生后端 `actor_id`；短期 JWT 到期不改变访客身份。
- FastAPI SSE 必须出现 `done` 才视为成功；用户停止必须出现 `cancelled` 才视为服务端终态确认。连接提前结束、Schema 错误和工具失败均显式失败，不把部分输出包装成成功。
- 会话切换从后端读取 Skill 选择；仅显式新建且继承输入上下文的 session 才执行首次写入，切换已有空会话不得用当前标签覆盖其后端选择。刷新后点回会话会从真实 Skill 列表恢复中文名称。
- Skill 上传先调用只校验、不落库的 preview API；完整 `SKILL.md` 在可编辑源码/渲染预览中供用户审阅，明确确认后才注册。系统 Skill 可查看完整只读源码，自定义 Skill 使用 expected revision 编辑，禁止“上传即注册”。
- 用户点击停止后进入“正在安全停止”状态，发送 `POST /api/gerclaw/chat/{trace_id}/cancel` 并继续读取原 SSE；只有收到服务端 `cancelled` 后，正文才标为 `stopped` 并追加“未完成且未通过最终校验”警示，thinking 结束、所有 running 工具卡转为 cancelled，且不显示重新生成之外的完成态假象。
- 切换既有会话或退出当前会话时，输入框的未发送文字、图片、文档和进行中的录音/识别都会在切换前清理；浏览器撤销图片 Object URL，并用稳定文字说明资料不会自动带入新会话。首次发送自动创建会话时保留当前草稿，确保用户的明确发送意图不被清空。
- CGA 入口只显示服务端量表目录和 `CgaAssessment` 的真实状态机；评估期间隐藏聊天输入和重复标题，防止用户把自由文本误当作量表答案。目录通过受限 BFF 读取当前主体的服务端 active assessment，并将其 ID 写回本机作为恢复优化；进行中的量表明确显示“已保存进度”和“继续”，而不是误导为“开始”。接口不返回原始答案；清除浏览器存储后同一主体仍可恢复。评估进行中，退出操作明确显示“休息，稍后继续”与“保存并休息”，如实说明服务端已保存的断点；退出确认只保留带文字的取消与确认操作，患者老年模式下均为至少 48px 的可点击控件。
- “我的健康记录”从欢迎页和患者输入栏直接打开右侧面板，通过受限 BFF 读取当前 actor 的 `GET /memory/profile`。前端以 Zod 校验所有事实字段，只展示已确认事实；待确认事实使用其 revision 调用 `POST /memory/facts/{id}/decision`。该入口不支持跨患者读取，也不把健康资料写入 localStorage。
- 健康记录初次读取、刷新、空态和错误态均使用稳定文字状态；刷新已有数据时保留上次成功内容，不使用循环骨架、闪烁或跳动布局。患者老年模式的刷新、确认、忽略控制均至少 48px 并带文字标签。
- 风险提示依靠高对比色、清晰标题和明确行动项传达紧急程度，不使用持续脉冲或闪烁动画；若允许确认知晓，该操作始终保留不小于 48px 的文字按钮与可见键盘焦点。
- 对话中的阶段提示使用静态时钟/完成标记和明确“进行中”文字，不以循环脉冲或旋转图标反复吸引注意力；状态变化通过语义化 `aria-live` 传达给辅助技术。
- 技能工作台、技能选择器与技能编辑器的读取、选择保存和草稿生成采用固定布局与明确动作文字（如“正在读取技能”“正在保存”）；不使用循环骨架或旋转图标表达长等待。实际可用技能始终来自受校验的服务端列表，加载失败仍保留可恢复的重试入口。
- 语音识别提交后显示稳定的“正在识别语音”状态与“取消识别”文字按钮；取消会中止当前 ASR 请求，绝不把迟到的识别结果写回输入框。不得使用循环旋转图标替代等待或取消操作。
- 对话内信息补充卡的录音控件在老年模式下必须显示“语音输入 / 停止录音 / 识别中”文字；录音中使用静态高对比状态与“点击停止后开始识别”的说明，不得闪烁或脉冲。未展示声波的卡片不得每帧采样音量或触发 React 重渲染；麦克风启动失败必须清除录音态并给出可理解的权限/设备提示。
- 患者老年模式下，Skill 选择说明、已加载标签、显式“移除”按钮和完整 Markdown 预览正文均不低于 18px；所有操作目标不低于 48px。已有底部文字“关闭”时禁用弹窗右上角纯图标关闭按钮，避免重复且不合规的 35px 控件。
- 命中红旗症状时先显示本地就医卡，后端在 RAG/模型前返回固定急症响应；即使请求错误，已有 120/急诊提示也不得被通用错误文案覆盖。

## 6. 样式规范

- 优先使用Tailwind CSS utility classes
- 颜色使用CSS变量/Tailwind主题配置，不硬编码色值
- 响应式：mobile-first，使用sm:/md:/lg:/xl:前缀
- 深色模式：使用dark:前缀，浅色为默认
- 老年模式：使用senior:变体或条件class，字体大小/按钮尺寸/间距动态调整
- 不使用inline style（动态transform/width等计算值除外）
- 动画使用Tailwind transition/animate类，尊重prefers-reduced-motion
- z-index管理：使用预定义层级（modal: 50, overlay: 40, dropdown: 30, sticky: 20, default: 0）

## 7. 测试规范

- 单元测试：utils/（音频处理、重试逻辑、格式化、导出功能）
- 组件测试：关键交互组件（ChatInput、MicButton、MessageBubble、RoleSwitcher）使用React Testing Library
- Hook测试：useChat/useVoice/useModelConfig核心逻辑
- E2E测试：核心用户旅程（发送文本消息→AI回复→播放TTS→导出PDF）使用Playwright
- 测试文件命名：`[name].test.ts(x)` 与源文件同目录
- 每个测试覆盖主路径（成功）+至少1条错误路径（失败/超时/降级）
- 不追求100%覆盖率，但核心流程必须有测试
- npm run test:unit运行单元测试，npm run test:e2e运行E2E测试
- `npm run test:audio` 验证全局朗读协调：启动新的消息/CGA 朗读会停止旧播放器，工作流退出可停止实际活跃播放器且停止操作幂等。

## 8. 环境变量规范

浏览器 bundle 只允许 `NEXT_PUBLIC_APP_NAME` 与 `NEXT_PUBLIC_APP_VERSION` 两个显示配置；其他有值的 `NEXT_PUBLIC_*` 在 MVP 启动时 fail closed。模型、语音、搜索、文档服务和签名密钥均为服务端变量：

```env
# Next.js server runtime only；apps/mvp 的 dev/build/start 脚本从仓库根 .env 注入
GERCLAW_API_URL=http://127.0.0.1:8000
# GERCLAW_GUEST_IDENTITY_SECRET 由 Secret Manager 注入，至少32字符

# 完整模型/RAG/Voice/Search/MinerU 配置见根 .env.example；真实 MinerU 还必须配置
# MINERU_URL、MINERU_API_KEY 与 MINERU_ALLOWED_HOSTS（严格 HTTPS host allowlist）
# GERCLAW_AUTH_JWT_SECRET 由 Secret Manager 注入，至少32字符
```

.env.example提交到仓库，真实.env*文件加入.gitignore。

## 9. 工具可视化规范

文档解析和联网搜索不单独设计页面，作为智能体执行过程中的工具可视化展示：

- **联网搜索结果**：在消息流中以独立卡片展示（标题+来源 favicon+摘要+链接），AI 正文用 [1][2] 角标引用，点击链接在右侧面板预览
- **文档解析状态**：文件标签+工具卡片双重反馈（上传中→解析中→完成/失败）。解析后明确显示“请提问后发送”或“已加入本次对话”；浏览器不会为了发送文档伪造问题，前端只交给 BFF/服务层登记及传递 UUID，禁止直接拼接 Markdown。后端负责所有权、会话、撤销和 Harness 隔离。
- **所有工具调用遵循 gerclaw设计要求.md §4.2.3 的 7 项可视化规范**：
  1. 思维链（可折叠"思考过程"区块）
  2. 工具调用（独立卡片+状态徽章）
  3. 子智能体加载（折叠树形结构）
  4. 决策过程（垂直时间线）
  5. 联网搜索结果（卡片+角标引用）
  6. 文档解析状态（文件标签+工具卡片）
  7. 流式文本输出（打字机效果）
