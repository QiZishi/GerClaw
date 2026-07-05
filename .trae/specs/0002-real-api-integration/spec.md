# GerClaw 0002 — 真实 API 接入与 Mock 数据清理 - Product Requirement Document

## Overview
- **Summary**: 在已完成的前端 UI 壳子（计划 0001）基础上，删除所有 Mock 数据，搭建 API Client 基础设施层，配置环境变量，接入真实 LLM 流式对话、Mimo ASR/TTS 语音交互、联网搜索等核心能力，使 GerClaw MVP 从可交互 UI 原型升级为可真实使用的 AI 诊疗助手。
- **Purpose**: 0001 阶段完成了完整的 UI 交互壳子，但所有对话回复、功能流程均使用 setTimeout 模拟和硬编码文案，无法提供真实价值。本阶段目标是让核心功能"真的能用"——用户输入的文字能得到真实 LLM 的流式回复，语音按钮能真正录音识别，搜索能返回真实结果。
- **Target Users**: 老年患者、老年科医生（与 0001 一致）。

## Goals
- 删除 `src/data/mock/` 下所有 Mock 数据文件和所有 Mock 逻辑分支
- 搭建 `src/services/` API Client 层，统一封装外部 API 调用（超时/重试/降级/主备切换）
- 配置 Zod 校验的环境变量系统，搬运 `/Users/qizs/conclusion/gerclaw/.env.local` 到项目中
- 接入真实 LLM 流式对话（支持 OpenAI 协议主模型 + 备份模型自动降级）
- 接入 Mimo ASR 语音识别（MediaRecorder 录音 → Base64 → mimo-v2.5-asr）
- 接入 Mimo TTS 语音合成（mimo-v2.5-tts PCM16 流式播放，冰糖音色）
- 接入联网搜索（AnySearch 主 + Tavily 备）
- 五大处方/CGA/用药审查功能流程改为调用真实 LLM 驱动对话式信息收集和结果生成
- 医疗安全后处理：确定性诊断用语拦截、免责声明自动附加、高风险症状强提示保留
- 保持适老化无障碍规范不回退（18px 基础字号、48px 按钮、二次确认等）

## Non-Goals (Out of Scope)
- 二阶段全栈架构（FastAPI/AgentScope/PostgreSQL/Qdrant）——本阶段仍是纯前端 MVP
- 账号系统与健康画像持久化——健康画像仍为前端展示结构，无后端存储
- PDF/DOCX 真实导出——按钮保留，导出为 Markdown 文本（后续 0015 再做）
- MinerU 文档解析与文件上传真实解析——文件上传按钮保留，基础文件选择+标签展示，真实解析二阶段
- 技能管理真实上传/执行——技能面板仍展示预置技能列表，自定义技能上传二阶段
- DDI/Beers 规则引擎真实数据——用药审查使用 LLM 辅助审查（明确标注"AI 辅助仅供参考"），真实规则引擎二阶段
- CGA 量表真实计分与报告——CGA 流程由 LLM 柔性引导，结构化计分二阶段
- 嵌入/Rerank 模型接入（RAG 知识库）——全栈阶段功能

## Background & Context
- **已完成基础（0001）**: Next.js 16.2.10 + React 19 + TypeScript strict + Tailwind CSS 4 + shadcn/ui 40+ 组件，三栏布局、7 项可视化组件、适老化老年模式、角色差异化、CGA 三阶段 UI、五大处方信息收集 UI、消息操作按钮、高风险症状检测。
- **技术栈依赖已安装**: `ai` (Vercel AI SDK v7) + `@ai-sdk/openai` v4 已在 package.json 中，无需新增依赖。
- **环境变量**: 所有 API Key 已在 `/Users/qizs/conclusion/gerclaw/.env.local` 配置完毕，包含主模型（qwen3.7-plus, OpenAI 协议）、备份1（qwen3.6-flash, DashScope 协议）、备份2（intern-s2-preview, OpenAI 兼容）、Mimo ASR/TTS、AnySearch、Tavily、SiliconFlow Embedding/Rerank、MinerU。
- **架构约束（ARCHITECTURE.md）**:
  - 所有外部 API 调用必须通过 `src/services/` 层封装，禁止组件直接 fetch
  - 环境变量必须经 `lib/config.ts` Zod 校验，禁止直接 `process.env`
  - API Client 需为二阶段后端迁移预留适配层
  - 分层依赖：types → lib → services → stores → hooks → components → app
- **铁律提醒**: 禁止确定性诊断、所有医疗输出带免责声明、适老化规范、配置不硬编码、真实执行不空谈。

## Functional Requirements

### FR-1: 环境变量配置与 Zod 校验
- 从 `/Users/qizs/conclusion/gerclaw/.env.local` 复制到 `apps/mvp/.env.local`，变量名适配 Next.js 公开变量（`NEXT_PUBLIC_` 前缀）
- 更新 `lib/config.ts`，严格校验所有必需环境变量，缺失关键 LLM 配置时给出明确错误提示而非静默降级
- 创建 `.env.example` 模板文件，列出所有必需变量及说明

### FR-2: Mock 数据清理
- 删除 `src/data/mock/` 目录下所有 8 个 mock 文件（messages/sessions/prescription/cga/drug-review/patients/search-results/skills）
- 删除 `ChatArea.tsx` 中所有 mockMessagesBySession/mockSessions/mockScales 的导入和使用
- 删除 `Sidebar.tsx` 中对 mockSessions 的依赖，会话列表从 Zustand store 初始化
- 预置 CGA 量表数据保留为**静态医疗知识数据**（非 mock），迁移到 `src/data/` 下作为正式静态数据文件
- 预置技能列表数据保留为静态配置数据，迁移到 `src/data/` 下
- 所有 setTimeout 模拟 AI 回复的逻辑替换为真实 API 调用

### FR-3: API Client 基础设施
- 创建 `src/services/api-client.ts`：统一的 API 客户端基类
  - 请求超时控制（各服务独立超时配置）
  - 指数退避重试（最多 3 次，可配置）
  - 错误分类与标准化（网络错误/超时/HTTP 错误/限流/认证失败）
  - Trace ID 生成（用于日志排查）
  - AbortController 支持（用于停止生成）
- 创建 `src/services/llm/` 目录：LLM 服务封装
  - 支持 OpenAI 协议流式调用（主模型 + 备份模型）
  - 主备自动降级：主模型失败（超时/5xx/429/网络错误）自动切换备份1，再失败切换备份2
  - 使用 Vercel AI SDK (`ai` + `@ai-sdk/openai`) 的 `streamText` 实现流式输出
  - 支持多轮对话消息历史管理（messages 数组构建）
  - System prompt 根据角色（医生/患者）动态生成，包含医疗安全指令
- 创建 `src/services/voice/` 目录：ASR/TTS 服务封装
  - ASR：MediaRecorder 录音 → WAV/MP3 Blob → Base64 → mimo-v2.5-asr OpenAI 兼容接口
  - TTS：调用 mimo-v2.5-tts（冰糖音色），PCM16 流式 chunk 解码，通过 Web Audio API 实时播放
- 创建 `src/services/search/` 目录：联网搜索封装
  - AnySearch 主搜索，失败降级 Tavily
  - 搜索结果格式化（标题/snippet/url/favicon）

### FR-4: 真实 LLM 流式对话
- 普通聊天模式：用户发送文本 → 调用 LLM → 流式打字机效果渲染 Markdown
- 实现"思考过程"可视化：模型 thinking 内容折叠展示（若模型支持 thinking mode）
- 停止生成按钮：调用 AbortController 中断流式请求
- 重新生成按钮：重新发起上一条 AI 回复请求
- 消息操作：复制按钮（复制纯文本内容）

### FR-5: Mimo ASR 语音输入
- 点击麦克风按钮 → 请求麦克风权限 → MediaRecorder 开始录音
- 录音中状态：实时波形动画（简化版：音量指示条）+ 录音时长计时
- 再次点击停止录音 → 发送音频到 ASR API → 识别结果填入输入框
- 录音错误处理（权限拒绝、设备不可用、API 失败）给出适老化友好提示
- ASR 识别结果自动填入 textarea，用户可编辑后发送

### FR-6: Mimo TTS 语音朗读
- AI 消息右上角播放按钮 → 调用 TTS API → PCM16 流式播放
- 播放中：按钮变为暂停图标，显示简单进度指示
- 暂停/继续、停止控制
- 老年模式下：可配置是否自动播放 AI 回复（默认开启可后续配置）
- 使用冰糖音色，语速适中、语气温柔体贴

### FR-7: 联网搜索
- LLM 决策需要搜索时（通过 function calling / tool use 或关键词触发），调用搜索 API
- 搜索结果以卡片形式展示（标题、来源 favicon、snippet、链接）
- AI 正文用 [1][2] 角标引用搜索结果
- 点击角标可展开引用详情
- MVP 阶段搜索触发方式：用户消息含搜索关键词或 LLM 主动判断（初期可先实现简单的"需要搜索"前缀触发，后续完善 tool use）

### FR-8: 五大处方真实生成
- 用户点击"五大处方生成" → 进入对话式信息收集流程
- AI 通过自然语言对话引导用户提供信息（年龄/性别/主诉/病史/用药/过敏），而非硬编码字段追问
- AI 从用户多轮输入中自动提取结构化信息
- 信息充分后 AI 生成五大处方内容（药物/运动/营养/心理/康复），流式输出
- 生成完毕后 AI 发送摘要回复 + "查看完整处方"按钮，点击展开右侧面板展示完整报告
- 所有输出附带医疗免责声明

### FR-9: CGA 老年综合评估（LLM 柔性引导）
- 保留三阶段 UI：选量表 → 答题（选项卡片） → 完成
- 量表题目使用静态数据（非 mock，正式量表知识数据）
- 答题完成后，将答题结果发送给 LLM 生成评估解读和建议（流式输出）
- 评估结果在右侧面板展示，附带免责声明
- 删除 mock 的 setTimeout 假完成逻辑

### FR-10: 用药审查（AI 辅助审查）
- 用户输入用药清单 → LLM 辅助分析潜在问题
- 明确标注"AI 辅助审查仅供参考，不替代专业药师/医生判断"
- 输出结构化：药物列表、潜在相互作用提示、Beers 标准相关提醒、建议
- 真实 DDI/Beers 规则引擎二阶段实现

### FR-11: 医疗安全后处理
- **确定性诊断拦截**：后处理检测 LLM 输出中的确定性诊断用语（如"你得了XX病"、"确诊为XX"），自动替换为可能性表述或附加"需医生确诊"提示
- **免责声明自动附加**：所有 AI 医疗回复末尾自动附加 `MEDICAL_DISCLAIMER`
- **高风险症状强提示**：保留 0001 已实现的 HIGH_RISK_SYMPTOMS 关键词检测，命中时在 AI 回复前插入红色紧急就医卡片（此检查在 LLM 调用前完成，优先于 LLM 回复）
- **循证引用标注**：使用搜索结果时，必须标注来源角标

### FR-12: 会话持久化（localStorage）
- 会话列表和消息历史保存到 localStorage（替代 mock 数据）
- 页面刷新后可恢复历史会话
- 提供清除会话的功能

## Non-Functional Requirements

### NFR-1: 性能
- LLM 首字响应时间（TTFT）：正常网络 < 5s，超时阈值 30s
- ASR 识别响应：录音停止后 < 5s 返回结果
- TTS 首包播放：点击后 < 3s 开始发声
- 流式输出帧率：保持 UI 流畅，Markdown 增量渲染无明显卡顿
- API 超时后自动降级到备份模型，用户无感知（除了响应稍慢）

### NFR-2: 可靠性
- 主模型失败时自动切换备份模型，成功率 > 95%
- 网络错误/API 错误给出友好错误提示，不白屏不崩溃
- 所有异步操作有 AbortController 支持，组件卸载时取消未完成请求
- localStorage 读取做 try-catch 防护，损坏数据自动清除

### NFR-3: 安全性
- API Key 通过 NEXT_PUBLIC_ 环境变量注入（MVP 纯前端阶段，部署时由 IGA Pages 注入；生产环境二阶段走后端代理）
- 不记录/不上传用户语音原始数据到除 ASR API 外的地方
- 用户输入做长度限制（≤4000字符），XSS 由 React 自动转义
- 所有医疗输出带免责声明，禁止确定性诊断

### NFR-4: 适老化无障碍（不回退）
- 基础字号保持 18px（老年模式 20px）
- 按钮最小尺寸保持 48×48px（老年模式）
- 高对比度配色（AAA 标准）
- 语音按钮足够大且位置明显
- 录音/播放状态有清晰视觉反馈
- 老年模式退出功能保留二次确认
- 错误提示使用大字体、清晰易懂的语言

### NFR-5: 代码质量
- TypeScript strict 模式无错误
- ESLint 0 错误 0 警告
- `npm run build` 静态导出成功
- 分层依赖严格遵守：services 层不依赖 React 组件/Hooks
- 所有服务接口使用 TypeScript 类型定义，Zod 校验外部 API 响应

## Constraints
- **Technical**: Next.js 16.2.10 静态导出（`output: "export"`），无服务端 API Routes；所有 API 调用浏览器直连外部服务；Vercel AI SDK v7 + @ai-sdk/openai v4 已安装
- **Business**: MVP 阶段无账号系统，访客模式全功能可用；部署到 IGA Pages 静态托管
- **Dependencies**: Vercel AI SDK 用于 LLM 流式；Web Audio API 用于 TTS PCM 播放；MediaRecorder API 用于录音；无需新增 npm 依赖
- **医疗合规**: 禁止确定性诊断、必须带免责声明、高风险症状必须强提示

## Assumptions
- `/Users/qizs/conclusion/gerclaw/.env.local` 中的 API Key 均有效且额度充足
- 主模型（qwen3.7-plus via OpenAI 兼容协议）支持流式输出和 Markdown 格式
- Mimo ASR/TTS API 可从浏览器端直接跨域调用（CORS 已配置），如遇 CORS 问题需提示用户或使用代理
- AnySearch/Tavily API 支持浏览器端直接调用
- 现有 UI 组件（ThinkingBlock/ToolCallBlock/StreamingText/MessageBubble 等）不需要重构，只需替换数据源为真实流式数据
- CGA 量表静态数据（mock/cga.ts 中的量表题目）作为正式医疗知识数据保留，仅删除其他 mock 文件

## Acceptance Criteria

### AC-1: 环境变量正确配置
- **Given**: 项目根目录 `apps/mvp/` 下存在 `.env.local` 文件（从 `/Users/qizs/conclusion/gerclaw/.env.local` 复制并适配 NEXT_PUBLIC_ 前缀）
- **When**: 应用启动（`npm run dev`）
- **Then**: `lib/config.ts` Zod 校验通过，无警告；`hasRealLLMConfig()` 返回 true；`npm run build` 成功
- **Verification**: `programmatic`
- **Notes**: 同时提供 `.env.example` 模板

### AC-2: 所有 Mock 数据删除
- **Given**: 代码库完成清理
- **When**: 全局搜索 "mock" 相关导入
- **Then**: `src/data/mock/` 目录不存在；ChatArea.tsx/Sidebar.tsx 等无 mock 导入；所有 setTimeout 模拟回复替换为真实 API 调用；预置量表/技能数据迁移到 `src/data/` 作为正式静态数据
- **Verification**: `programmatic`（grep 验证 + build 通过）

### AC-3: 普通对话真实流式回复
- **Given**: 用户在输入框输入文本（如"你好，我最近睡眠不好怎么办"）
- **When**: 点击发送
- **Then**: AI 消息以流式打字机效果逐字输出 Markdown 内容；停止按钮可中断生成；输出末尾有医疗免责声明；Markdown 渲染正确（加粗/列表/段落）
- **Verification**: `human-judgment`（手动测试 + 浏览器自动化验证流式文本出现）

### AC-4: 主备模型自动降级
- **Given**: 主模型 URL 故意配置错误
- **When**: 发送对话消息
- **Then**: 自动切换到 backup1 模型成功返回回复；控制台有降级日志；用户体验无明显中断
- **Verification**: `programmatic`（单元测试降级逻辑）+ `human-judgment`（错误配置测试）

### AC-5: 语音输入真实识别
- **Given**: 用户允许麦克风权限
- **When**: 点击麦克风按钮，说"我今年70岁，血压有点高"，点击停止
- **Then**: 录音时有视觉反馈（计时/状态指示）；停止后 ASR 返回识别文本填入输入框；识别文本可编辑发送
- **Verification**: `human-judgment`（需真实麦克风测试）
- **Notes**: 权限拒绝时给出友好提示

### AC-6: 语音朗读真实播放
- **Given**: AI 已回复一条消息
- **When**: 点击消息上的播放按钮
- **Then**: TTS 流式播放语音（冰糖音色，中文女声）；播放中按钮变为暂停；播放完成按钮恢复；老年模式下可清晰听到
- **Verification**: `human-judgment`（需音频播放验证）

### AC-7: 五大处方真实生成
- **Given**: 患者模式，点击"五大处方生成"
- **When**: 通过对话提供年龄/性别/不适等信息
- **Then**: AI 自然对话引导（非硬编码追问）；信息充分后流式生成五大处方内容；生成后有摘要+查看按钮；右侧面板展示完整报告；内容带免责声明
- **Verification**: `human-judgment`

### AC-8: CGA 评估完成后生成 AI 解读
- **Given**: CGA 选量表 → 逐题作答 → 提交
- **When**: 答题完成
- **Then**: 调用 LLM 基于答题结果生成评估解读（流式）；右侧面板展示评估结果；带免责声明
- **Verification**: `human-judgment`

### AC-9: 医疗安全后处理生效
- **Given**: 用户消息含"胸痛"等高风险词
- **When**: 发送消息
- **Then**: 立即显示红色紧急就医卡片（在 LLM 回复之前）；所有 AI 回复末尾有"内容由 AI 生成，仅供参考。身体不适请及时就医。"
- **Verification**: `programmatic`（关键词检测单元测试）+ `human-judgment`

### AC-10: 构建与 Lint 通过
- **Given**: 所有代码完成
- **When**: 运行 `npm run lint` 和 `npm run build`
- **Then**: ESLint 0 错误 0 警告；Next.js build 成功，静态导出完成；TypeScript 类型检查通过
- **Verification**: `programmatic`

### AC-11: 适老化规范不回退
- **Given**: 切换到老年模式
- **When**: 浏览所有页面、使用语音/对话/功能按钮
- **Then**: 正文字号 ≥18px；按钮 ≥48×48px；高对比度；退出功能有二次确认；错误提示大字体清晰
- **Verification**: `human-judgment`

### AC-12: 会话 localStorage 持久化
- **Given**: 有几条对话历史
- **When**: 刷新页面
- **Then**: 会话列表和消息历史恢复；可继续之前的对话
- **Verification**: `human-judgment`

## Open Questions
- [ ] 浏览器端直连外部 LLM/ASR/TTS API 是否存在 CORS 限制？如果有，需要临时使用 CORS 代理还是调整部署方案？（先假设 CORS 已配置，如实际遇阻再处理）
- [ ] Vercel AI SDK v7 的 `streamText` 是否支持非 OpenAI 官方 endpoint（如阿里云 DashScope 兼容模式、Mimo OpenAI 兼容接口）？需验证，如不支持则手写 fetch + ReadableStream 解析
- [ ] PCM16 流式播放：24kHz 采样率在 Web Audio API 中的实时拼接是否会有卡顿？需要缓冲策略
- [ ] 联网搜索的触发机制：MVP 阶段是自动判断（LLM tool use）还是手动触发？本 PRD 倾向初期使用简单触发（用户消息含"搜索"、"查一下"等关键词，或功能按钮显式搜索），tool use 在对话流畅后增强
- [ ] 健康画像功能（患者端"我的健康画像"）：0001 阶段为 mock 展示，本阶段是否需要 LLM 从对话中提取信息构建简单画像结构？倾向是：基础版通过对话提取基本信息展示，持久化到 localStorage
