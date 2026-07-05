# FRONTEND.md

> 前端规范 | 基于PRD.md第5节技术栈和gerclaw设计要求.md第2-3节生成

---

## 1. 技术栈

| 类别 | 技术选择 | 版本 | 说明 |
|------|---------|------|------|
| 框架 | Next.js | 15 (App Router) | React框架，支持SSG静态导出(output: 'export')适配IGA Pages |
| 语言 | TypeScript | 5.x | strict模式启用，全类型覆盖 |
| 样式方案 | Tailwind CSS | 4 | 原子化CSS，深色模式dark:前缀 |
| UI组件库 | shadcn/ui | latest | 基于Radix UI的高质量组件库，按需导入 |
| 图标 | Lucide React | latest | 一致风格的图标库 |
| 状态管理 | Zustand + React Context | latest | Zustand 管理会话/配置等可序列化状态，Context 管理主题/角色等跨组件状态；localStorage 持久化 |
| 路由 | Next.js App Router | 15 | 文件系统路由，app/目录结构 |
| 数据获取 | Vercel AI SDK + fetch | latest | useChat/useCompletion处理流式对话，原生fetch处理REST API |
| 表单处理 | React Hook Form + Zod | latest | 类型安全的表单验证（设置、技能上传等） |
| 音频处理 | Web Audio API + MediaRecorder | 浏览器原生 | 麦克风录音(WAV/MP3)、PCM16流式播放 |
| 文档导出 | jsPDF + docx + marked | latest | PDF导出、DOCX导出、Markdown渲染 |
| Markdown渲染 | react-markdown + remark-gfm + rehype-highlight | latest | Markdown渲染、GFM表格/任务列表、代码语法高亮 |
| 测试框架 | Vitest + React Testing Library + Playwright | latest | 单元测试/组件测试/E2E测试 |
| 构建工具 | Next.js内置(Turbopack) | 15 | 零配置构建，静态导出 |
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

二阶段代码位于 `apps/web/`（前端）和 `apps/api/`（FastAPI后端），目录结构待MVP完成后定义。

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
- 关键操作添加AbortController支持（用户可停止生成/取消请求）

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

## 8. 环境变量规范

前端环境变量使用 `NEXT_PUBLIC_` 前缀：

```env
# === 主模型（OpenAI兼容）===
NEXT_PUBLIC_PRIMARY_URL=https://api.openai.com/v1
NEXT_PUBLIC_PRIMARY_API_KEY=
NEXT_PUBLIC_PRIMARY_MODEL=gpt-4o
NEXT_PUBLIC_PRIMARY_PROTOCOL=openai

# === 备份模型1（DashScope兼容）===
NEXT_PUBLIC_BACKUP1_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
NEXT_PUBLIC_BACKUP1_API_KEY=
NEXT_PUBLIC_BACKUP1_MODEL=qwen-plus
NEXT_PUBLIC_BACKUP1_PROTOCOL=openai

# === Mimo语音服务 ===
NEXT_PUBLIC_MIMO_API_KEY=
NEXT_PUBLIC_ASR_MODEL=mimo-v2.5-asr
NEXT_PUBLIC_TTS_MODEL=mimo-v2.5-tts
NEXT_PUBLIC_TTS_VOICE=冰糖

# === 联网搜索 ===
NEXT_PUBLIC_ANYSEARCH_API_KEY=
NEXT_PUBLIC_TAVILY_API_KEY=

# === MinerU文档解析 ===
NEXT_PUBLIC_MINERU_URL=
NEXT_PUBLIC_MINERU_API_KEY=
```

.env.example提交到仓库，真实.env*文件加入.gitignore。

## 9. 工具可视化规范

文档解析和联网搜索不单独设计页面，作为智能体执行过程中的工具可视化展示：

- **联网搜索结果**：在消息流中以独立卡片展示（标题+来源 favicon+摘要+链接），AI 正文用 [1][2] 角标引用，点击链接在右侧面板预览
- **文档解析状态**：文件标签+工具卡片双重反馈（上传中→解析中→完成/失败），解析完成自动作为上下文
- **所有工具调用遵循 gerclaw设计要求.md §4.2.3 的 7 项可视化规范**：
  1. 思维链（可折叠"思考过程"区块）
  2. 工具调用（独立卡片+状态徽章）
  3. 子智能体加载（折叠树形结构）
  4. 决策过程（垂直时间线）
  5. 联网搜索结果（卡片+角标引用）
  6. 文档解析状态（文件标签+工具卡片）
  7. 流式文本输出（打字机效果）
