# GerClaw × Trae Work体验对齐优化 - Product Requirement Document

## Overview
- **Summary**: 将GerClaw MVP的聊天交互、工具调用、过程可视化、UI设计全面对齐Trae Work的生产级体验，同时保留并强化老年医疗适老化特色，使产品成为"老年健康诊疗领域的Trae Work"
- **Purpose**: 当前实现存在toy级问题（硬编码关键词触发工具、无真正Function Calling、流式无逐字效果、停止不彻底、引用不可靠、无模型选择器、动画简陋），无法满足实际生产使用，需要对齐Trae的专业级交互体验
- **Target Users**: 老年患者（语音优先、适老化）、老年科医生（高效专业）

## Goals
1. **核心聊天体验对齐Trae**：逐字流式打字效果、自动滚动跟随、停止按钮明确、输入框自动高度、Markdown精致渲染（含代码高亮）
2. **工具调用生产级重构**：实现真正的OpenAI Function Calling协议，LLM自主决定何时调用工具，工具状态实时可视化，支持多轮工具调用
3. **联网搜索重构**：基于Function Calling实现搜索，搜索过程实时展示，结构化引用角标可靠生成，搜索结果卡片即时显示
4. **UI动画与视觉精致化**：统一过渡动画规范、右侧面板滑入/滑出、展开收起平滑动画、更精致的间距/圆角/阴影，保留适老化大字体大按钮
5. **模型选择与多模型支持**：UI添加模型选择器，主备切换对用户透明但可见，视觉模型自动选择
6. **停止生成彻底修复**：AbortSignal真正传递到上游LLM请求，停止后立即释放资源
7. **适老化保留**：所有优化不破坏老年模式≥18px字体、≥48px按钮、高对比度、语音优先等适老化要求

## Non-Goals (Out of Scope)
- 不做PDF/DOCX导出（二阶段）
- 不做MinerU文档解析（二阶段）
- 不做账号系统/登录（二阶段）
- 不做部署（按用户要求移除）
- 不照搬Trae的开发者导向紧凑布局（医疗场景需要宽松舒适）
- 不做深色主题为主（医疗产品默认浅色，深色可选）
- 不做AgentScope多智能体（二阶段）

## Background & Context
- 上一版本0004完成了MVP功能闭环，但存在核心体验问题：
  - 工具调用是前端硬编码关键词触发（"搜索一下"等关键词判断），不是LLM自主决策的Function Calling，属于toy实现
  - 流式输出是delta块直接追加，无逐字打字节奏，视觉生硬
  - 流式中不自动滚动到底部
  - 停止按钮只中断前端SSE，后端AbortSignal未传递给上游，继续浪费token
  - 引用角标依赖LLM自觉输出[1][2]标记然后前端正则匹配，不可靠
  - 无模型选择UI，主备降级用户无感知
  - 组件展开/收起、面板开关无平滑动画
  - Markdown渲染简陋（无代码高亮、表格样式差）
  - 消息操作按钮一直显示，视觉噪音大
  - 输入框高度固定
- Trae Work是字节跳动的AI助手产品，其交互体验是行业标杆，特别是在工具调用、流式输出、过程可视化方面
- GerClaw作为医疗产品，必须在专业体验上达到Trae级别，同时叠加适老化特色

## Functional Requirements
- **FR-1**: 实现平滑逐字打字效果（SSE接收delta后按自然节奏逐字渲染，有打字机节奏感）
- **FR-2**: 流式输出过程中自动平滑滚动到底部，始终跟随最新内容
- **FR-3**: 停止按钮图标清晰（方形停止图标），点击后真正中止上游LLM请求（AbortSignal传递）
- **FR-4**: 右侧面板打开/关闭有平滑滑入滑出动画
- **FR-5**: ThinkingBlock/ToolCallBlock展开/收起有平滑高度过渡动画
- **FR-6**: Markdown代码块添加shiki语法高亮，右上角有一键复制按钮
- **FR-7**: Markdown表格、列表、引用块样式优化，美观易读
- **FR-8**: 消息操作按钮默认隐藏，hover/focus时才显示
- **FR-9**: ChatInput textarea自动增高，有最大高度限制
- **FR-10**: 实现真正的OpenAI Function Calling协议：在SSE流中处理tool_call/tool_calls事件，LLM自主决定调用工具
- **FR-11**: 联网搜索改为Function Calling实现：当LLM决定搜索时，前端实时显示ToolCallBlock（搜索中→搜索完成），调用搜索API，将结果作为tool消息传回LLM继续生成
- **FR-12**: 引用角标结构化生成：基于搜索结果位置可靠生成[1][2]角标，不依赖LLM自觉
- **FR-13**: 添加模型选择器UI：在输入框区域或顶部显示当前模型，允许切换主备模型，视觉模型自动选择
- **FR-14**: 图片多模态流程优化：图片上传后自动选择支持视觉的模型
- **FR-15**: 全局统一过渡动画规范（200-250ms ease-out），所有交互元素有hover/focus/active反馈
- **FR-16**: 视觉风格优化：更柔和的阴影、更舒适的圆角（8px-12px）、更均匀的间距、更多留白，保留适老化
- **FR-17**: 输入框聚焦时有柔和边框高亮过渡
- **FR-18**: 会话列表hover/选中态反馈更明显

## Non-Functional Requirements
- **NFR-1**: 适老化无障碍：老年模式正文字号≥18px，按钮≥48px，对比度≥7:1（AAA级），所有优化不得破坏这些要求
- **NFR-2**: 性能：逐字打字效果不能引入明显延迟，动画需流畅（60fps）
- **NFR-3**: 医疗安全：确定性诊断拦截、免责声明、高风险提示保持不变
- **NFR-4**: 构建稳定性：npm run lint 0错误0警告，npm run build成功
- **NFR-5**: 可维护性：遵循现有代码架构，不引入不必要的依赖
- **NFR-6**: 向后兼容：所有现有功能（CGA/五大处方/用药审查/语音交互/导出）继续正常工作

## Constraints
- **Technical**: Next.js 16 + React 19 + Tailwind CSS 4 + shadcn/ui，继续使用现有技术栈
- **Dependencies**: 代码高亮使用shiki（轻量），不引入重型动画库（使用CSS transition/fallback）
- **Medical**: 适老化和医疗安全是硬约束，任何体验优化不得违反
- **Architecture**: API Client层继续走services/层，不破坏现有分层

## Assumptions
- 当前配置的主模型（Doubao/DeepSeek等）支持OpenAI兼容的Function Calling协议
- shiki可以在Next.js中正常工作，支持客户端渲染
- CSS transition可以满足大部分动画需求，不需要framer-motion等额外库

## Acceptance Criteria

### AC-1: 逐字流式打字效果
- **Given**: 用户发送消息，LLM开始流式回复
- **When**: SSE持续接收delta内容
- **Then**: 文字以自然的打字机节奏逐字/逐小块显示，视觉流畅不生硬
- **Verification**: `human-judgment`

### AC-2: 自动滚动跟随
- **Given**: AI正在流式回复
- **When**: 新内容持续追加
- **Then**: 聊天区域自动平滑滚动到底部，用户始终能看到最新内容；如果用户手动向上滚动则暂停自动跟随，回到底部后恢复
- **Verification**: `human-judgment`

### AC-3: 停止生成真正生效
- **Given**: AI正在流式回复
- **When**: 用户点击停止按钮
- **Then**: SSE连接立即关闭，AbortSignal传递到上游API请求，后端停止生成，按钮立即变回发送状态，已接收内容保留
- **Verification**: `programmatic` + `human-judgment`

### AC-4: 真正Function Calling
- **Given**: 用户问需要最新信息的问题
- **When**: LLM判断需要搜索
- **Then**: LLM返回tool_call，前端自动调用搜索API，ToolCallBlock实时显示搜索状态，搜索结果传回LLM继续回答，全程无硬编码关键词触发
- **Verification**: `programmatic` + `human-judgment`

### AC-5: 右侧面板动画
- **Given**: 右侧面板关闭状态
- **When**: 触发打开面板（如查看引用/报告）
- **Then**: 面板从右侧平滑滑入（250ms ease-out），关闭时平滑滑出
- **Verification**: `human-judgment`

### AC-6: 代码块语法高亮
- **Given**: AI回复包含代码块
- **When**: 渲染Markdown内容
- **Then**: 代码有语法高亮着色，右上角显示复制按钮，点击复制成功有反馈
- **Verification**: `human-judgment`

### AC-7: 模型选择器
- **Given**: 聊天界面
- **When**: 用户查看/切换模型
- **Then**: 界面上有清晰的当前模型标识，点击可切换模型，切换后新对话使用新模型
- **Verification**: `human-judgment`

### AC-8: 适老化保留
- **Given**: 老年模式开启
- **When**: 使用所有功能
- **Then**: 正文字号≥18px，按钮≥48px，对比度足够，语音按钮显眼，无任何适老化回退
- **Verification**: `human-judgment` + `programmatic`

### AC-9: 构建通过
- **Given**: 所有修改完成
- **When**: 运行npm run lint和npm run build
- **Then**: lint 0错误0警告，build成功
- **Verification**: `programmatic`

## Open Questions
- [ ] 当前配置的主模型是否稳定支持Function Calling？如果不支持是否需要调整模型配置？
- [ ] 代码高亮是否需要支持医疗领域特定语言？还是通用语言即可？
- [ ] 模型选择器放在哪个位置最合适（输入框上方？侧边栏？顶部？）
