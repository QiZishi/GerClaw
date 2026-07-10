# GerClaw × Trae Work体验对齐优化 - The Implementation Plan

> **开发规范要求**：每个Task完成后必须立即运行`npm run lint`和`npm run build`验证，通过后及时git commit；全部任务完成后更新`docs/长期规划.md`并做最终git提交。遵循agents.md的所有要求，小步提交，每个提交只做一件事。

## [x] Task 1: 停止生成彻底修复 + 基础交互优化
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修复API路由src/app/api/llm/chat/route.ts：将AbortSignal真正传递给上游fetch请求，点击停止后中止上游LLM调用
  - 修改ChatInput停止按钮图标为方形停止图标（Square），确保位置显眼
  - 修复自动滚动：在ChatArea中添加useEffect监听消息变化，当用户在底部时自动平滑滚动到底部；用户手动向上滚动时暂停自动跟随
  - 全局CSS添加统一过渡动画规范（200-250ms ease-out）
- **Acceptance Criteria Addressed**: AC-2, AC-3, AC-9
- **Test Requirements**:
  - `programmatic` TR-1.1: API路由接收signal参数并传递给上游fetch
  - `human-judgement` TR-1.2: 点击停止后立即停止输出，后端不再继续生成
  - `human-judgement` TR-1.3: 流式输出时自动滚动到底部，手动上滚后暂停跟随
  - `human-judgement` TR-1.4: 停止按钮图标清晰为方形停止
- **Notes**: 最小修改量最高收益，优先完成

## [x] Task 2: 真逐字流式打字效果 + 输入框自动高度
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 重构StreamingText组件：实现真正的逐字打字机效果——接收delta后放入队列，以自然节奏（约15-30ms每字符，有随机微波动）逐字符渲染，光标跟随最后一个字符
  - 修改ChatInput textarea：实现自动增高，初始1行，随内容增加增高，最大高度约200px后出现滚动条
  - 输入框聚焦时添加柔和边框高亮过渡效果
- **Acceptance Criteria Addressed**: AC-1, AC-9
- **Test Requirements**:
  - `human-judgement` TR-2.1: 文字逐字流畅显示，有打字机节奏感，不是整块蹦出
  - `human-judgement` TR-2.2: 光标在文字末尾闪烁
  - `human-judgement` TR-2.3: 输入框随内容自动增高，最大高度后滚动
  - `human-judgement` TR-2.4: 输入框聚焦有边框高亮过渡
- **Notes**: 打字速度不能太慢（不能让用户等），约50-100字符/秒的自然速度

## [x] Task 3: 真正OpenAI Function Calling架构重构
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 扩展src/services/llm/client.ts的streamChat：
    - 定义tools参数（web_search工具，包含query参数描述）
    - 在SSE流解析中正确处理tool_call / tool_calls delta事件（包括index/id/name/arguments的增量拼接）
    - 支持多轮工具调用循环：LLM返回tool_call → 执行工具 → 将tool结果作为tool角色消息回传 → 继续LLM流式
    - 回调中新增onToolCallStart/onToolCallDelta/onToolCallEnd供前端UI更新
  - 修改src/app/api/llm/chat/route.ts：支持tools参数传递给上游OpenAI兼容API
  - 彻底移除前端硬编码关键词触发搜索的逻辑（"搜索一下""帮我查"等关键词判断）
  - ChatArea中正确处理工具调用生命周期：收到onToolCallStart时插入tool_call block（状态running），工具执行完成后更新为done/error
- **Acceptance Criteria Addressed**: AC-4, AC-9
- **Test Requirements**:
  - `programmatic` TR-3.1: client.ts正确解析tool_call delta（支持流式拼接arguments）
  - `programmatic` TR-3.2: 支持多轮工具调用循环（LLM→tool→LLM→...→最终回答）
  - `human-judgement` TR-3.3: 无需关键词，LLM判断需要搜索时自动调用工具
  - `human-judgement` TR-3.4: 工具调用过程中ToolCallBlock实时更新状态
- **Notes**: 这是核心架构变更，影响最大。参考OpenAI Chat Completions API的function calling规范

## [x] Task 4: 联网搜索Function Calling重构 + 引用来源美观化结构化引用
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 将联网搜索改为通过Function Calling触发（web_search工具）
  - 搜索API调用后，将结果以结构化方式返回给LLM（包含title/url/snippet）
  - 实现结构化引用角标：在LLM最终输出流处理中，检测LLM输出中的引用标记并可靠渲染[1][2]角标；如果LLM不主动输出，则基于上下文相关性在后处理中添加引用角标
  - 搜索开始时立即在消息中插入ToolCallBlock显示"正在搜索..."，搜索结果返回后更新显示结果数量
  - 搜索结果自动同步到右侧面板引用列表
- **Acceptance Criteria Addressed**: AC-4, AC-9
- **Test Requirements**:
  - `human-judgement` TR-4.1: 搜索由LLM自主决定触发，无需关键词
  - `human-judgement` TR-4.2: 搜索过程实时显示，结果卡片/工具卡片状态正确
  - `human-judgement` TR-4.3: 引用角标[1][2]可靠显示，点击可查看来源
- **Notes**: 引用角标尽量让LLM生成，后处理作为兜底

## [x] Task 5: Markdown精致渲染 + 代码块语法高亮
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 安装shiki依赖，实现Markdown代码块语法高亮
  - 重构MarkdownRenderer：
    - 代码块使用shiki高亮，右上角添加一键复制按钮，复制成功有toast反馈
    - 优化表格样式：边框、条纹、padding、圆角
    - 优化列表样式：缩进、项目符号/编号对齐
    - 优化引用块：左侧边框、背景色、斜体
    - 优化分隔线样式
    - 链接有hover下划线效果
    - 标题层级清晰
  - 代码块在老年模式下字号不小于16px
- **Acceptance Criteria Addressed**: AC-6, AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-5.1: shiki正确安装配置，无构建错误
  - `human-judgement` TR-5.2: 代码块有语法高亮着色，复制按钮可用
  - `human-judgement` TR-5.3: 表格/列表/引用样式美观易读
  - `human-judgement` TR-5.4: 老年模式下代码块字号清晰
- **Notes**: shiki使用客户端渲染，注意SSR兼容性

## [x] Task 6: UI动画与视觉精致化
- **Priority**: medium
- **Depends On**: Task 1
- **Description**:
  - 右侧面板RightPanel添加滑入滑出CSS transition动画（transform: translateX，250ms ease-out）
  - ThinkingBlock/ToolCallBlock展开收起添加平滑高度过渡动画（使用CSS transition或useAutoAnimate风格的hook）
  - 消息操作按钮（复制/重新生成/朗读/导出）改为默认opacity-0，group-hover/focus-within时opacity-100，添加过渡
  - 全局视觉优化：
    - 圆角统一：卡片rounded-lg(8px)，按钮rounded-md(6px)，大卡片rounded-xl(12px)
    - 阴影柔和：使用shadow-sm/shadow而非重阴影
    - 间距优化：消息之间间距、内边距更舒适
    - 留白适当增加
  - 会话列表Sidebar：hover背景色更明显，选中态有主色调侧边标识
  - 滚动条样式美化（细条，hover变粗，圆角）
- **Acceptance Criteria Addressed**: AC-5, AC-9
- **Test Requirements**:
  - `human-judgement` TR-6.1: 右侧面板滑入滑出动画流畅
  - `human-judgement` TR-6.2: 思考/工具区块展开收起有平滑动画
  - `human-judgement` TR-6.3: 消息操作按钮hover时才显示
  - `human-judgement` TR-6.4: 整体视觉更精致现代
- **Notes**: 保持适老化大按钮大字体，不做紧凑布局

## [x] Task 7: 模型选择器UI + 多模型支持完善
- **Priority**: medium
- **Depends On**: Task 3
- **Description**:
  - 在ChatInput区域上方或侧边栏添加模型选择器组件：
    - 显示当前使用的模型名称（精简显示，如"Doubao Pro"、"DeepSeek V3"）
    - 点击弹出下拉菜单，列出主模型和备用模型供选择
    - 切换模型后，新发送的消息使用新模型
  - appStore中添加selectedModel状态，持久化到localStorage
  - 当消息包含图片时，自动切换/提示需要视觉模型，如当前模型不支持vision给出提示
  - 主备自动降级发生时，显示一个短暂的toast提示"已切换到备用模型"（不打扰用户但可知晓）
- **Acceptance Criteria Addressed**: AC-7, AC-9
- **Test Requirements**:
  - `human-judgement` TR-7.1: 界面上清晰显示当前模型
  - `human-judgement` TR-7.2: 点击可切换模型，切换后新消息使用新模型
  - `human-judgement` TR-7.3: 主备降级时有轻量toast提示
  - `human-judgement` TR-7.4: 选择偏好持久化到localStorage
- **Notes**: 模型选择器位置放在输入框左下角比较合适（不占地方，易找到）

## [x] Task 8: 全量回归测试与适老化验证
- **Priority**: high
- **Depends On**: Task 4, Task 5, Task 6, Task 7
- **Description**:
  - 运行npm run lint修复所有警告/错误
  - 运行npm run build确保构建成功
  - 适老化验证：老年模式下所有按钮≥48px，字体≥18px，对比度足够
  - 全功能回归：
    - 普通对话真流式输出
    - 自动提问触发搜索（Function Calling）
    - 工具调用可视化
    - 思维链显示
    - CGA评估（含语音答题）
    - 五大处方流程
    - 用药审查
    - 语音输入/朗读
    - 图片上传多模态
    - Markdown导出
    - 停止/重新生成
    - 会话切换/新建/删除
    - 角色切换
    - 老年模式切换
    - 右侧面板拖拽
    - 代码块高亮
    - 模型切换
  - 修复发现的bug
  - 更新长期规划.md
  - git提交
- **Acceptance Criteria Addressed**: AC-8, AC-9
- **Test Requirements**:
  - `programmatic` TR-8.1: npm run lint 0错误0警告
  - `programmatic` TR-8.2: npm run build成功
  - `human-judgement` TR-8.3: 所有核心功能流程正常工作
  - `human-judgement` TR-8.4: 适老化规范无回退
- **Notes**: 启动dev服务让用户手动测试
