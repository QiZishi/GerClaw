# 0006 UX打磨与Bug修复 - The Implementation Plan

## [x] Task 1: 修复SourceReferences组件button嵌套问题
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - SourceReferences.tsx中外层<button>（展开/收起整个引用列表）嵌套了内层<button>（"查看全部"），违反HTML规范
  - 修复方案：将外层容器改为<div>或<div role="button">，或者将"查看全部"按钮移到外层button外部，避免嵌套
  - 确保展开/收起和查看全部功能都正常
- **Acceptance Criteria Addressed**: AC-1, AC-6
- **Test Requirements**:
  - `programmatic` TR-1.1: 浏览器控制台无button嵌套错误
  - `human-judgement` TR-1.2: 点击展开/收起引用列表正常，点击"查看全部"打开右侧面板正常
- **Notes**: 参考Vercel Web Interface Guidelines: "`<button>` for actions, `<a>`/`<Link>` for navigation (not `<div onClick>`)"

## [x] Task 2: 优化web_search工具触发条件
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - route.ts中WEB_SEARCH_TOOL的description太宽泛，导致LLM对基础医学常识也触发搜索
  - 修改description明确：仅当需要最新医学指南、新近更新的药物信息、新闻事件、实时数据、用户询问具体医院/医生/药品信息时才搜索；基础医学常识、定义、标准值等直接回答
  - 在system prompt中也补充指引，告诉LLM不要过度使用搜索
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgement` TR-2.1: 问"老年人血压正常范围"不触发搜索，直接回答
  - `human-judgement` TR-2.2: 问"2024年最新高血压指南有什么变化"触发搜索
- **Notes**: 保持现有Function Calling架构不变，只优化description和prompt

## [x] Task 3: 修正默认角色和老年模式设置
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - appStore中默认role为"patient"且seniorMode默认为true，导致访客一进来就是老年模式大字号+自动TTS
  - 修改默认role为"visitor"（访客），访客模式默认seniorMode=false
  - 切换到patient模式时seniorMode自动开启（保持现有逻辑），用户可手动关闭
  - 确保RoleSwitcher组件能正确切换角色
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `programmatic` TR-3.1: 清除localStorage后首次访问，默认role=visitor，seniorMode=false
  - `human-judgement` TR-3.2: 切换到患者模式时自动开启老年模式（可手动关闭）
  - `human-judgement` TR-3.3: 访客模式下不会自动TTS朗读
- **Notes**: 对齐AGENTS.md"访客模式下所有功能可用"

## [x] Task 4: 确认CitationPopover引用渲染（无重复bug，三处[1]是正确多处引用）
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 浏览器测试发现3个重复的"查看引用1"按钮，说明TextWithCitations递归处理children时重复渲染了CitationPopover
  - 检查MarkdownRenderer中的TextWithCitations组件，修复递归逻辑，确保每个[id]角标只渲染一次popover
  - 验证inline code、列表项、段落等不同位置的引用都正确渲染
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `human-judgement` TR-4.1: 消息中[1]引用角标只出现一个可点击元素
  - `human-judgement` TR-4.2: 点击引用角标正确显示popover内容
- **Notes**: 检查React key是否正确，递归终止条件是否完善

## [x] Task 5: 优化ToolCallBlock搜索完成后的展示
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - 搜索完成后ToolCallBlock仍显示"展开详情"按钮，展开后是args/result的raw JSON，对用户无意义
  - 参考Trae Work：工具调用运行中显示紧凑状态卡片，完成后卡片自动收起，只留一个小的工具图标标识（或直接隐藏）
  - 修复方案：搜索工具完成后，默认不显示展开按钮（hasContent为false，因为result是原始数据不直接展示），或者将result中的有用信息（如结果数）显示但不提供raw JSON展开
  - 确保运行中的spinner状态正常
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-5.1: 搜索运行中显示"正在搜索「xxx」..."+spinner
  - `human-judgement` TR-5.2: 搜索完成后显示紧凑状态"已找到N个结果"，不默认显示展开按钮或显示为小标识
  - `human-judgement` TR-5.3: 不显示raw JSON给终端用户

## [x] Task 6: 简化思考块时间显示（对齐Trae Work）
- **Priority**: medium
- **Depends On**: None
- **Description**: 
  - ThinkingBlock显示"思考过程 · 16.7s"，这个时间实际包含了工具调用时间，不是纯LLM思考时间
  - 修复方案：在client.ts中正确统计thinking的start和end时间，不将工具调用耗时计入思考时长
  - 或者简化：思考块只显示"思考过程"不显示具体时长（Trae Work不显示思考时长）
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-6.1: 如果显示时长，仅包含LLM返回thinking delta的时间
  - `human-judgement` TR-6.2: 或者移除时长显示（更简洁，对齐Trae Work）
- **Notes**: 建议简化为不显示时长，Trae Work的思考块只显示"已思考"折叠状态，不显示具体秒数

## [x] Task 7: 全量回归测试+lint+build验证（含StreamingText渲染bug修复）
- **Priority**: high
- **Depends On**: Task 1,2,3,4,5,6
- **Description**: 
  - 运行npm run lint确保0错误0警告
  - 运行npm run build确保构建成功
  - 启动dev服务，浏览器实际测试：普通对话、需要搜索的问题、角色切换、老年模式、欢迎页、引用角标等
  - 检查控制台无错误
- **Acceptance Criteria Addressed**: AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-7.1: npm run lint 0错误0警告
  - `programmatic` TR-7.2: npm run build 成功
  - `human-judgement` TR-7.3: 浏览器测试核心流程顺畅
  - `programmatic` TR-7.4: 控制台无红色错误和warning
