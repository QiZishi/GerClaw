# GerClaw 0002 — 真实 API 接入与 Mock 数据清理 - The Implementation Plan

## Task Dependencies Overview
```
Task 1 (环境变量+Mock清理) → Task 2 (API Client基础设施) → Task 3 (LLM流式对话) → Task 4 (ASR语音输入)
                                                                                    ↓
                                                        Task 5 (TTS语音朗读) → Task 6 (联网搜索)
                                                                                    ↓
                                                        Task 7 (五大处方真实生成) → Task 8 (CGA评估AI解读)
                                                                                    ↓
                                                        Task 9 (用药审查AI辅助) → Task 10 (医疗安全后处理)
                                                                                    ↓
                                                        Task 11 (会话localStorage持久化) → Task 12 (构建+Lint+全量验证)
```

---

## [ ] Task 1: 环境变量配置与 Mock 数据清理
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 将 `/Users/qizs/conclusion/gerclaw/.env.local` 的内容复制到 `apps/mvp/.env.local`，变量名添加 `NEXT_PUBLIC_` 前缀适配 Next.js 静态导出（浏览器端可访问）
  - 注意：原 .env.local 中变量名（如 OPENAI_URL）需映射为 NEXT_PUBLIC_PRIMARY_URL 等与 config.ts schema 一致的名称
  - 更新 `lib/config.ts`：将空字符串默认值改为对必需变量严格校验；如果主模型 API Key/URL 未配置，启动时在控制台输出明确警告（但不阻塞启动以便开发）；更新 voiceConfig 以支持独立 ASR/TTS URL（原配置中 ASR_URL/TTS_URL 独立于 MIMO）
  - 创建 `apps/mvp/.env.example` 模板文件（不含真实 Key，仅占位符和注释说明）
  - 将 `src/data/mock/cga.ts` 中的量表定义（phq9/gad7/psqi/miniCog/mmse）提取到 `src/data/scales.ts` 作为正式静态医疗数据，删除 mockScaleResults/mockCGAReport 等假结果数据
  - 将 `src/data/mock/skills.ts` 中的预置技能列表提取到 `src/data/skills.ts` 作为正式静态配置数据
  - 删除 `src/data/mock/` 目录下其余纯 mock 文件：messages.ts, sessions.ts, prescription.ts, drug-review.ts, patients.ts, search-results.ts
  - 删除整个 `src/data/mock/` 目录
  - 修改 ChatArea.tsx：移除所有 mock 导入（mockMessagesBySession/mockSessions/mockScales）；将 mockScales 替换为从 `@/data/scales` 导入的正式 scales 数据；移除 useEffect 中加载 mock 消息到 store 的逻辑
  - 修改 Sidebar.tsx：移除对 mockSessions 的依赖，会话列表从 Zustand store 初始化（空数组开始）
  - 删除所有组件中使用 mock 数据的地方（Prescription/DrugReview/RightPanel 等组件中如有 mock 导入一并清理）
  - 全局搜索 "from @/data/mock" 确保零残留
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `programmatic` TR-1.1: 运行 `npm run build` 成功，TypeScript 无类型错误
  - `programmatic` TR-1.2: grep 搜索 "data/mock" 无匹配（除了可能的注释说明）
  - `programmatic` TR-1.3: `.env.local` 文件存在于 apps/mvp/ 下，包含所有 NEXT_PUBLIC_ 前缀变量
  - `programmatic` TR-1.4: `npm run lint` 通过，0 错误 0 警告
  - `human-judgment` TR-1.5: 启动 dev server 后首页可正常显示（无空白/报错），欢迎页可见，CGA 选量表页面仍能看到 5 个量表卡片
- **Notes**: 
  - ASR/TTS 配置项在 config.ts 中需增加 NEXT_PUBLIC_ASR_URL、NEXT_PUBLIC_TTS_URL（原设计要求文档 Mimo URL 是独立的，但实际环境变量中 ASR_URL 和 TTS_URL 相同）
  - CGA 量表是医疗知识数据而非 mock，必须保留
  - 删除 mock 后，首次进入页面会话列表为空是正确行为（后续 Task 11 加 localStorage 持久化）

---

## [ ] Task 2: API Client 基础设施搭建
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 创建 `src/services/` 目录结构
  - 创建 `src/services/api-client.ts`：
    - 定义标准化 API 错误类型（ApiError/NetworkError/TimeoutError/RateLimitError/AuthenticationError）
    - 实现 `fetchWithTimeout` 函数：支持 AbortSignal、超时（默认 30s）、fetch 包装
    - 实现 `withRetry` 函数：指数退避重试（最多 3 次，baseDelay 1s，maxDelay 10s），对幂等 GET 请求重试，非幂等 POST 默认不重试
    - 实现 Trace ID 生成（uuid 简短版），每个请求附 `X-Trace-Id` header
    - 定义统一的 API 响应类型，与 types/api.ts 对齐
  - 创建 `src/services/llm/client.ts`：
    - 定义 LLMMessage 类型（role: system/user/assistant, content: string）
    - 定义 LLMStreamCallbacks 接口（onText: (delta) => void, onThinking?: (delta) => void, onDone: () => void, onError: (err) => void）
    - 实现 `streamChat(messages, options, callbacks, abortSignal)` 函数：
      - 优先使用主模型，失败自动降级到备份1→备份2
      - 使用原生 fetch + ReadableStream 解析 SSE（优先验证 Vercel AI SDK 是否可用，若自定义 OpenAI 兼容端点不支持则用原生 fetch）
      - 支持 OpenAI 协议 SSE 格式（data: {...}\n\n）
      - 解析 choices[0].delta.content 为文本 delta
      - 模型切换逻辑：捕获网络错误/超时/HTTP 5xx/429 时尝试下一个备份模型
    - 实现系统 prompt 构建：根据角色（patient/doctor）生成不同的 system prompt，包含医疗安全指令、角色设定、输出格式要求
    - 患者端 system prompt 要点：亲切、易懂、短句、避免专业术语、鼓励就医、不做确定性诊断、附免责声明
    - 医生端 system prompt 要点：专业、简洁、循证、标注依据、不做最终诊断、建议进一步检查
  - 创建 `src/services/llm/index.ts`：导出公共 API
  - 定义医疗安全 system prompt 常量（确定性诊断禁止用语列表等）
- **Acceptance Criteria Addressed**: AC-1, AC-4
- **Test Requirements**:
  - `programmatic` TR-2.1: TypeScript 编译通过，services 层不依赖 React
  - `programmatic` TR-2.2: api-client 支持超时、重试、AbortController（可通过简单调用测试）
  - `human-judgment` TR-2.3: 代码 review：LLM client 实现了主备降级逻辑，有错误处理
- **Notes**:
  - Vercel AI SDK 的 createOpenAI 支持自定义 baseURL 和 apiKey，但需验证是否兼容非官方 OpenAI 端点（阿里云/字节跳动兼容模式）
  - 如果 Vercel AI SDK 对非官方端点兼容性差，直接用 fetch + ReadableStream 手写 SSE 解析，这是更可控的方案
  - DashScope 协议如果与 OpenAI SSE 格式不兼容，在 SSE 解析层做适配（MVP 阶段主模型是 OpenAI 兼容协议，DashScope 作为备份只做最简支持）

---

## [ ] Task 3: 真实 LLM 流式对话接入
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 修改 ChatArea.tsx 的 doSend 函数：
    - 移除所有 setTimeout 模拟 AI 回复的逻辑
    - 普通聊天模式下（chatAction === "none"）：调用 services/llm 的 streamChat
    - 构建消息历史数组（从 messagesBySession 获取当前会话的消息，转换为 LLMMessage 格式）
    - 在 addMessage 时创建一个空的 assistant 消息（包含一个 text block，content 为空，streaming: true）
    - 在 onText 回调中：增量更新 assistant 消息的 text block content
    - 在 onDone 回调中：标记消息 status 为 "done"，streaming 设为 false，追加免责声明，setGenerating(false)
    - 在 onError 回调中：标记消息 status 为 "error"，显示错误提示
    - 高风险症状检测保留：用户消息中检测到 HIGH_RISK_SYMPTOMS 时，先插入紧急就医卡片，**仍然调用 LLM** 但在 system prompt 中强调用户提到了高风险症状，需建议立即就医
  - 实现停止生成：onStop 调用 AbortController.abort()，标记当前 AI 消息 status 为 "stopped"
  - 实现重新生成：在 MessageBubble 的重新生成按钮中，移除最后一条 AI 消息，用相同的 user 消息重新调用 streamChat
  - 实现复制：MessageBubble 的复制按钮复制当前消息纯文本（用 navigator.clipboard.writeText）
  - 修改 MessageBubble 组件：确保流式文本（streaming: true）渲染时光标闪烁效果
  - 确保 MarkdownRenderer 正确渲染增量 Markdown（可考虑简单方案：每次更新都重新渲染完整 content，不做增量解析优化）
  - 处理消息历史长度限制：发送给 LLM 的消息最多保留最近 20 轮，避免超出上下文窗口
  - 会话首次创建时自动设置标题为用户第一条消息的前 20 个字符（通过 setTimeout 在首次 AI 回复完成后更新）
- **Acceptance Criteria Addressed**: AC-3, AC-4, AC-10
- **Test Requirements**:
  - `human-judgment` TR-3.1: 启动 dev server，输入"你好，我最近睡眠不好怎么办"，看到流式打字机效果输出
  - `human-judgment` TR-3.2: 流式输出过程中点击停止按钮，生成中断，消息显示为已停止状态
  - `human-judgment` TR-3.3: 点击重新生成按钮，AI 重新回复
  - `human-judgment` TR-3.4: 复制按钮可复制消息内容到剪贴板
  - `human-judgment` TR-3.5: AI 回复末尾有医疗免责声明
  - `human-judgment` TR-3.6: 输入"胸痛"，先看到红色紧急就医卡片，再看到 AI 回复
  - `programmatic` TR-3.7: `npm run build` + `npm run lint` 通过
- **Notes**:
  - 高风险症状检测保留在 LLM 调用前（插入红色卡片），但 LLM 仍需调用以给出建议
  - SSE 解析注意：不同模型提供商的 SSE 格式可能有细微差异（如 [DONE] 标记、usage 字段），解析需容错
  - 初始实现可先不展示 thinking 内容（因为 qwen3.7-plus 可能不支持 thinking 模式），ThinkingBlock 组件保留但不触发

---

## [ ] Task 4: Mimo ASR 语音输入实现
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 创建 `src/services/voice/asr.ts`：
    - 定义 `recognizeAudio(audioBlob, options)` 函数：接收 Blob（WAV/MP3），返回 Promise\<string\>（识别文本）
    - 实现：将 Blob 转为 Base64 → 调用 Mimo ASR API（OpenAI 兼容格式，POST {url}/chat/completions）
    - Header: `api-key: $MIMO_API_KEY`（注意：不是 Authorization: Bearer，是 `api-key` header）
    - 请求体：model=mimo-v2.5-asr, messages=[{role:"user",content:[{type:"input_audio",input_audio:{data:"data:audio/wav;base64,..."}}]}], asr_options:{language:"auto"}, stream:false（MVP 先做非流式识别，流式 ASR 后续优化）
    - 解析响应：choices[0].message.content 为识别文本
    - 错误处理：API 失败时抛出标准化错误
  - 创建 `src/hooks/useAudioRecorder.ts`：
    - 封装 MediaRecorder 录音逻辑
    - 状态：isRecording, recordingDuration, audioLevel（音量大小用于波形动画）, audioBlob（录音结果）
    - 方法：startRecording（请求麦克风权限，MediaRecorder.start）, stopRecording（MediaRecorder.stop 返回 Blob）
    - 使用 audioContext + analyser 获取实时音量值（requestAnimationFrame 轮询）
    - 录音时长计时器（每秒更新）
    - 权限拒绝处理：返回明确错误
  - 修改 ChatInput.tsx：
    - 移除麦克风按钮的 toast "功能开发中"
    - 集成 useAudioRecorder hook
    - 录音中 UI：麦克风图标变为停止图标（红色 Square），显示录音时长，按钮周围有脉冲动画
    - 简单音量指示：按钮旁显示 3-4 个横条随音量变化
    - 点击停止：调用 ASR API → 识别过程中按钮显示 loading 状态 → 识别完成后文本填入 textarea
    - ASR 错误处理：toast 提示"语音识别失败，请重试"
    - 老年模式下：按钮尺寸加大，状态文字更大更清晰
  - 老年模式适配：录音中大字提示"正在录音…（再次点击停止）"，识别中"正在识别…"
- **Acceptance Criteria Addressed**: AC-5, AC-11
- **Test Requirements**:
  - `human-judgment` TR-4.1: 点击麦克风按钮，请求麦克风权限（允许），录音，停止后识别文本填入输入框
  - `human-judgment` TR-4.2: 录音中可见计时和录音状态指示
  - `human-judgment` TR-4.3: 识别到的文本可编辑，可发送
  - `human-judgment` TR-4.4: 麦克风权限被拒绝时，toast 提示用户如何开启权限
  - `human-judgment` TR-4.5: 老年模式下语音按钮尺寸和提示文字足够大
  - `programmatic` TR-4.6: `npm run build` + `npm run lint` 通过
- **Notes**:
  - MediaRecorder 在不同浏览器中 mimeType 支持不同，优先使用 audio/webm;codecs=opus，回退到 audio/wav 或默认格式
  - ASR API 的 audio format 可能需要根据录音格式调整（Data URL 格式更稳妥）
  - Mimo ASR 的具体 SSE 流式格式先做非流式（stream: false），降低复杂度

---

## [ ] Task 5: Mimo TTS 语音朗读实现
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 创建 `src/services/voice/tts.ts`：
    - 定义 `streamTTS(text, options, callbacks, abortSignal)` 函数
    - 调用 Mimo TTS API（OpenAI 兼容格式，POST {url}/chat/completions）
    - Header: `api-key: $MIMO_API_KEY`
    - 请求体：model=mimo-v2.5-tts, messages=[{role:"user",content:"用温柔体贴的语调，语速适中，像在关心一位老人的健康状况"},{role:"assistant",content:text}], audio:{format:"pcm16",voice:"冰糖"}, stream:true
    - 解析 SSE：每个 chunk 的 choices[0].delta.audio.data 为 Base64 PCM16 音频片段
    - onAudioChunk 回调返回 PCM 数据（Int16Array）
  - 创建 `src/hooks/useAudioPlayer.ts`：
    - 使用 Web Audio API (AudioContext) 播放 PCM16 流
    - 音频格式：24kHz, 单声道, PCM16LE（Int16）
    - 方法：play(), pause(), stop(), seek?（MVP 不做 seek）
    - 状态：isPlaying, isPaused, currentTime, duration（估算）
    - 实现流式缓冲队列：接收 PCM chunk 时加入队列，AudioBufferSourceNode 按序播放
    - 处理首包缓冲（积累 ~100ms 音频再开始播放以避免卡顿）
    - 冰糖音色设置在 TTS 请求中
  - 修改 VoiceReadButton（prescription/VoiceReadButton.tsx 和 MessageBubble 中的朗读按钮）：
    - 移除"功能开发中"toast
    - 集成 useAudioPlayer
    - 按钮状态：播放（播放图标）→ 播放中（暂停图标+旋转/高亮）→ 暂停（播放图标）
    - 播放完成自动恢复按钮状态
    - 错误处理：TTS 失败时 toast 提示"语音播放失败"
  - 老年模式：播放按钮更大，播放状态有明确视觉提示
- **Acceptance Criteria Addressed**: AC-6, AC-11
- **Test Requirements**:
  - `human-judgment` TR-5.1: 点击 AI 消息朗读按钮，听到语音播放（中文女声，冰糖音色）
  - `human-judgment` TR-5.2: 播放中点击按钮可暂停
  - `human-judgment` TR-5.3: 播放完成按钮恢复初始状态
  - `human-judgment` TR-5.4: 老年模式下按钮和状态指示清晰可见
  - `programmatic` TR-5.5: `npm run build` + `npm run lint` 通过
- **Notes**:
  - PCM16 实时播放是技术难点，需仔细处理 AudioContext 的缓冲队列，避免 underflow（卡顿）
  - 如果 Web Audio API 流式播放过于复杂，可降级方案：先接收完整音频（非流式）再播放，但会牺牲响应速度
  - Mimo TTS 返回的是 PCM16 24kHz mono，需要正确设置 AudioBuffer 的 sampleRate

---

## [ ] Task 6: 联网搜索接入
- **Priority**: medium
- **Depends On**: Task 2
- **Description**:
  - 创建 `src/services/search/search-client.ts`：
    - 定义 SearchResult 类型（与 types/chat.ts 的 SearchResultItem 对齐）
    - 实现 `searchAnySearch(query)` 函数：调用 AnySearch API
    - 实现 `searchTavily(query)` 函数：调用 Tavily API（作为备份）
    - 实现 `search(query)` 聚合函数：先尝试 AnySearch，失败降级到 Tavily
    - AnySearch API 调用：根据 anysearch 技能文档实现（如使用 anysearch 技能中描述的接口）
    - 注意：AnySearch 可能通过已有 Skill 调用方式接入，或直接 HTTP API
    - 结果格式化：统一转为 SearchResultItem 数组，包含 title/url/snippet/source/favicon
  - 搜索触发逻辑（MVP 简化版）：
    - 在 LLM system prompt 中指示：当用户询问需要最新信息或具体医学知识时，在回复开头加入 `[需要搜索:关键词]` 标记
    - ChatArea 的 doSend 后检测 AI 流式输出，如果包含 `[需要搜索:xxx]`，则暂停文本流式，调用搜索 API，搜索结果以 SearchResultCard 展示，然后将搜索结果加入上下文重新请求 LLM 生成最终回复
    - 或者更简单的 MVP 方案：检测用户消息中是否包含"搜索"、"查一下"、"最新"等关键词，自动附加搜索结果给 LLM 作为上下文
    - 选择更简单可行的方案：在 system prompt 中让 LLM 自主决定是否需要搜索，输出特殊标记后前端拦截处理
  - 搜索结果展示：使用已有的 SearchResultCard 组件在消息流中展示
  - 角标引用：AI 回复中引用搜索结果时使用 [1][2] 上标
  - 点击角标展示引用详情（CitationPopover 组件）
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `human-judgment` TR-6.1: 问"最新的高血压指南是什么"，AI 回复中可见搜索结果卡片，有来源引用
  - `human-judgment` TR-6.2: 搜索结果可点击展开详情
  - `programmatic` TR-6.3: `npm run build` + `npm run lint` 通过
- **Notes**:
  - MVP 阶段搜索触发可以简化：用户消息含"搜索"关键词时自动搜索；否则不触发
  - 如果 AnySearch API CORS 有问题，优先使用 Tavily（Tavily 有官方 CORS 支持）
  - 此任务优先级标记为 medium，如果时间紧张可以简化为：联网搜索仅在五大处方等功能中作为 LLM 的补充信息，不单独做搜索触发UI

---

## [ ] Task 7: 五大处方真实 LLM 生成
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 修改 ChatArea.tsx 中五大处方（chatAction === "prescription"）的逻辑：
    - 移除硬编码的 PRESCRIPTION_FIELDS 字段追问和 setTimeout 模拟
    - 改为：调用 LLM 用专门的五大处方 system prompt 引导对话
    - 开场消息由 LLM 生成（在 system prompt 中指示："你是老年科医生助手，需要为老年患者生成五大处方（药物/运动/营养/心理/康复）。请通过亲切自然的对话了解患者的年龄、性别、主要不适、既往病史、当前用药、过敏史。不要一次性问太多问题，像聊天一样一次问1-2个问题。"）
    - 每轮用户回复后，调用 LLM 继续对话，由 LLM 判断信息是否充分
    - LLM 判断信息充分时，在输出末尾加入 `[生成处方]` 特殊标记
    - 前端检测到 `[生成处方]` 标记后：结束对话收集阶段，发送特殊 prompt 请求 LLM 生成结构化的五大处方报告
  - 处方生成阶段：
    - 在消息流中显示 GeneratingOverlay（生成中状态）
    - 调用 LLM 生成 Markdown 格式的完整处方报告（药物处方/运动处方/营养处方/心理处方/康复处方五个部分）
    - 流式输出到右侧面板（RightPanel prescription 面板）
    - 生成完成后：AI 发送摘要消息（简短总结）+ action block（"查看完整处方"按钮）
  - 右侧面板处方报告展示：使用已有的 PrescriptionReport 组件，内容改为 LLM 生成的真实 Markdown
  - 保留 5 轮上限保护：如果对话超过 5 轮仍未收集完信息，强制让 LLM 基于已有信息生成处方
  - 医生端/患者端差异化 system prompt：
    - 患者端：亲切、易懂、鼓励性语言
    - 医生端：专业、简洁、结构化、标注循证依据
- **Acceptance Criteria Addressed**: AC-7, AC-9
- **Test Requirements**:
  - `human-judgment` TR-7.1: 患者模式点击"五大处方生成"，AI 自然对话式询问信息（非硬编码追问）
  - `human-judgment` TR-7.2: 提供若干信息后，AI 生成五大处方内容并在右侧面板展示
  - `human-judgment` TR-7.3: 生成完成有摘要和"查看完整处方"按钮
  - `human-judgment` TR-7.4: 处方内容末尾有医疗免责声明
  - `human-judgment` TR-7.5: 医生端话术专业简洁，患者端话术亲切易懂
  - `programmatic` TR-7.6: `npm run build` + `npm run lint` 通过
- **Notes**:
  - 硬编码的字段列表可保留作为 LLM 提取信息的参考（传递给 LLM 作为需收集的信息点），但追问逻辑交给 LLM
  - 5 轮上限是安全保护，防止无限对话
  - 处方生成的 Markdown 格式要在 system prompt 中明确规定（标题结构、五个处方的分隔等）

---

## [ ] Task 8: CGA 评估完成后 AI 解读生成
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 保留 CGA 三阶段 UI（选量表→答题→完成），量表题目使用 Task 1 迁移的正式静态 scales 数据
  - 修改答题完成逻辑（cgaFinished 状态）：
    - 移除 mock 的 setTimeout 假完成
    - 用户点击"提交评估"后，将答题结果（每个题目的问题+选项+得分）构建为文本 prompt
    - 调用 LLM（流式）生成评估解读
    - 提示词结构：量表名称、各题回答、总分、对应分级（从 scale.grading.thresholds 计算得出），请求 LLM 给出：
      1. 评估结果概述（基于得分分级）
      2. 各维度详细解读
      3. 针对性建议
      4. 就医提示（如分数异常）
    - LLM 回复流式输出到右侧面板（cga panel）
  - 计算量表得分：根据选项 value 累加，对照 grading.thresholds 判断 level
  - 右侧面板 CGAReport 组件改造：内容改为 LLM 生成的解读 + 得分摘要
  - 答题过程中的导航、进度条、适老化细节保持不变
- **Acceptance Criteria Addressed**: AC-8, AC-11
- **Test Requirements**:
  - `human-judgment` TR-8.1: 选择一个量表（如 PHQ-9），逐题作答，提交后 AI 流式生成评估解读
  - `human-judgment` TR-8.2: 右侧面板显示评估结果，包含得分、分级、解读、建议
  - `human-judgment` TR-8.3: 结果末尾有免责声明
  - `human-judgment` TR-8.4: 老年模式下答题界面按钮和文字大小仍符合适老化标准
  - `programmatic` TR-8.5: `npm run build` + `npm run lint` 通过
- **Notes**:
  - 量表计分是确定性逻辑（代码计算），不由 LLM 判断，确保分数准确
  - LLM 仅负责解读和建议生成，符合"状态机骨架+LLM柔性层"架构（ADR-005）
  - PHQ-9 第9题（自杀念头）如果得分>0，必须在 AI 回复中强烈建议立即就医/联系心理危机干预热线

---

## [ ] Task 9: 用药审查 AI 辅助实现
- **Priority**: medium
- **Depends On**: Task 3
- **Description**:
  - 修改 ChatArea.tsx 中用药审查（chatAction === "drug-review"）逻辑：
    - 移除硬编码字段追问逻辑，改为 LLM 驱动对话收集用药信息
    - System prompt 指示 AI 收集：用药清单（药名/剂量/频次）、诊断/病情、不良反应
    - AI 收集信息后生成结构化的用药审查报告：
      1. 用药清单汇总
      2. 潜在药物相互作用提示（LLM 基于训练知识提示，明确标注"AI 辅助识别，需药师确认"）
      3. 老年人潜在不适当用药提醒（参考 Beers 标准要点）
      4. 剂量与频次合理性提示
      5. 建议（需咨询医生/药师的事项）
    - 报告开头必须有醒目标注："⚠️ AI 辅助用药审查仅供参考，不替代专业药师/医生判断。用药调整请遵医嘱。"
  - 右侧面板 drug-review 面板展示审查报告
  - 医生端 vs 患者端提示差异化
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgment` TR-9.1: 医生模式进入用药审查，输入几种药物后 AI 生成审查建议
  - `human-judgment` TR-9.2: 审查报告开头有明显的"仅供参考"提示
  - `programmatic` TR-9.3: `npm run build` + `npm run lint` 通过
- **Notes**:
  - 本任务仅做 LLM 辅助审查，真实 DDI/Beers 规则引擎是二阶段功能
  - 必须在 UI 和输出中反复强调 AI 审查的局限性

---

## [ ] Task 10: 医疗安全后处理强化
- **Priority**: high
- **Depends On**: Task 3, Task 7, Task 8, Task 9
- **Description**:
  - 创建 `src/lib/security-postprocess.ts`：
    - 实现 `postprocessMedicalText(text, options)` 函数：
      - **免责声明附加**：检查文本末尾是否已有 MEDICAL_DISCLAIMER，如无则追加
      - **确定性诊断拦截**：检测确定性诊断用语（"确诊为"、"你得了XX病"、"肯定是XX"、"一定是XX"等），替换为可能性表述（"可能是XX，建议就医确诊"、"提示XX可能性，需医生进一步检查"）
      - **高风险词二次检查**：在输出中扫描 HIGH_RISK_SYMPTOMS，如果相关症状被提及但未提示就医，强补就医提示
    - 定义确定性诊断用语正则模式列表
  - 在所有 LLM 流式输出完成后（onDone 回调中）调用 postprocessMedicalText，对最终文本进行后处理
  - 确保高风险症状的红色紧急卡片逻辑（Task 3 中已保留）始终优先展示
  - 自杀风险提示：如果 CGA PHQ-9 第9题得分>0，或用户消息中提到自杀/不想活等关键词，在 AI 回复中附加强烈提示："如果您有伤害自己的想法，请立即拨打心理危机干预热线：北京 010-82951332，全国 24 小时热线：400-161-9995。请告诉您的家人或医生。"
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-10.1: 单元测试：postprocessMedicalText 正确拦截"你得了糖尿病"等确定性表述
  - `programmatic` TR-10.2: 单元测试：postprocessMedicalText 自动追加免责声明
  - `human-judgment` TR-10.3: 对话中 AI 回复不出现确定性诊断用语，所有医疗建议带免责声明
  - `human-judgment` TR-10.4: 提到自杀相关内容时出现危机干预热线提示
  - `programmatic` TR-10.5: `npm run build` + `npm run lint` 通过
- **Notes**:
  - 医疗安全是铁律，后处理是最后一道防线
  - 拦截是补充性的，主要通过 system prompt 约束 LLM 不输出确定性诊断

---

## [ ] Task 11: 会话 localStorage 持久化
- **Priority**: medium
- **Depends On**: Task 3
- **Description**:
  - 修改 chatStore.ts：
    - 在 addMessage/updateMessage/addSession/removeSession 等所有修改操作后，自动持久化到 localStorage（key: "gerclaw_sessions" 和 "gerclaw_messages"）
    - 初始化时（store 创建时）尝试从 localStorage 读取历史数据
    - 使用 try-catch 包裹所有 localStorage 操作，损坏数据自动清除并重置
    - 注意 localStorage 容量限制（约 5MB），消息过多时自动截断最早的消息（保留最近 50 条/会话）
  - 修改 storage.ts（已有文件）：增加会话相关的存取函数，如无则补充
  - 会话列表按 updatedAt 排序（最近的在前）
  - 新会话的第一条用户消息发送后，自动用消息前 20 字符作为会话标题
  - 删除会话时同步删除对应的消息记录
- **Acceptance Criteria Addressed**: AC-12
- **Test Requirements**:
  - `human-judgment` TR-11.1: 创建对话、发送几条消息后刷新页面，会话列表和消息历史恢复
  - `human-judgment` TR-11.2: 删除会话后刷新，会话不再出现
  - `human-judgment` TR-11.3: 新建对话后标题自动更新
  - `programmatic` TR-11.4: `npm run build` + `npm run lint` 通过
- **Notes**:
  - Message 类型中含有 createdAt 等时间戳，JSON 序列化/反序列化无问题
  - 序列化时注意 Map/Set 等类型要转为数组（当前 store 中都是普通对象和数组，应该没问题）

---

## [ ] Task 12: 全量构建验证 + 缺陷修复
- **Priority**: high
- **Depends On**: Task 1 through Task 11
- **Description**:
  - 运行 `npm run lint`：修复所有 ESLint 错误和警告
  - 运行 `npm run build`：确保 Next.js 静态导出成功，TypeScript 类型检查通过
  - 启动 dev server（npm run dev），执行端到端手动验证：
    - 患者模式/医生模式切换
    - 普通对话流式回复（含停止、重新生成、复制）
    - 高风险症状检测（胸痛、呼吸困难等）
    - 老年模式切换（字体大小、按钮尺寸、二次确认）
    - 五大处方流程（患者端亲切对话→生成→右侧面板查看）
    - CGA 评估（选量表→答题→提交→AI解读）
    - 用药审查流程（医生端）
    - 语音输入（如麦克风可用）
    - 语音朗读（TTS 播放）
    - 会话持久化（刷新页面）
    - 侧边栏折叠/展开
    - 右侧面板展开/收起/可编辑
  - 修复所有发现的缺陷
  - 适老化回归检查：所有核心页面字体≥18px（普通模式已设置18px基础），按钮≥48px（老年模式），高对比度
  - 撰写 Playwright 自动化测试脚本覆盖核心路径：
    - 发送文本消息并验证 AI 流式回复出现
    - 验证高风险症状紧急卡片出现
    - 验证五大处方按钮点击进入流程
    - 验证 CGA 量表选择和答题流程
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-12
- **Test Requirements**:
  - `programmatic` TR-12.1: `npm run lint` 0 错误 0 警告
  - `programmatic` TR-12.2: `npm run build` 成功，静态导出完成
  - `programmatic` TR-12.3: Playwright 自动化测试核心路径通过（PASS ≥ 20 项）
  - `human-judgment` TR-12.4: dev server 可访问，核心功能手动测试通过
  - `human-judgment` TR-12.5: 适老化规范不回退（字体、按钮尺寸、对比度、二次确认）
- **Notes**:
  - 此任务是最终验收关口，所有前置任务的缺陷在此修复
  - 自动化测试脚本使用 webapp-testing 指令的 Playwright 模式
  - 测试覆盖优先保证核心对话流程和医疗安全功能
