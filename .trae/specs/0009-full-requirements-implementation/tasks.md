# 0009 新任务全量需求实现 - Implementation Plan

## [ ] Task 1: 紧急Bug修复（自动播放+加载动画+思考spinner）
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 移除ChatArea.tsx中所有autoReadIfSeniorMode/老年模式自动TTS逻辑
  - 普通聊天场景TTS默认不播放，仅用户点击播放按钮才播放
  - 修复ThinkingBlock：思考中保留Loader2 spinner动画，将animation-duration调至1.5s（适中速度），不要过快；折叠后显示"已思考"
  - 保留StreamingText空内容时的三点跳动动画（这是文字输出等待动画，不是思考动画）
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-1.1: 代码中搜索autoReadIfSeniorMode/autoRead/seniorAutoRead，确认普通聊天场景无自动播放逻辑
  - `programmatic` TR-1.2: ThinkingBlock使用Loader2+animate-spin，CSS中spinner速度为1.5s
  - `human-judgement` TR-1.3: 浏览器测试发送消息后不自动播放语音，思考时显示spinner（不是三点）
- **Notes**: 这是P0紧急修复，用户最不满的点

## [ ] Task 2: 消息操作按钮完整重构（豆包风格+三点菜单+全按钮功能）
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 重构MessageBubble按钮行，顺序为：赞|踩|分割线|复制|重新生成|播放|分享|三点菜单(⋯)
  - 赞/踩按钮：互斥状态，点击后弹出小反馈框（textarea+提交按钮），可输入文字也可直接提交空反馈，提交后按钮filled+toast
  - 复制按钮：点击复制AI回复纯文本到剪贴板，按钮显示checkmark 2秒后恢复原图标
  - 重新生成按钮：仅显示在最后一条AI消息（isLastMessage=true），点击后删除该AI消息并重新streamChat
  - 播放按钮：点击播放/暂停TTS（默认不自动播放），图标切换Volume2/VolumeX
  - 分享按钮：点击打开ExportDialog，默认选中当前问答对（用户消息+该AI回复），支持勾选其他消息，支持PNG/PDF/DOCX/MD格式
  - 三点菜单按钮：点击弹出DropdownMenu，包含"转为文档编辑"和"删除"两个选项
  - 删除功能：点击后打开DeleteConfirmDialog，默认选中当前问答对，支持勾选其他消息，有取消和确认删除按钮
  - 转为文档编辑功能：点击后在右侧栏打开新的"doc-editor"类型面板，实时MD编辑+实时渲染
  - 恢复ExportDialog和DeleteConfirmDialog组件（0008错误删除了）
  - 创建DocEditorPanel组件用于"转为文档编辑"
- **Acceptance Criteria Addressed**: AC-1, AC-12
- **Test Requirements**:
  - `human-judgement` TR-2.1: 每个按钮在浏览器中点击有真实响应
  - `human-judgement` TR-2.2: 分享对话框打开、可选择消息和格式、导出文件正确
  - `human-judgement` TR-2.3: 删除对话框打开、默认选中当前问答对、确认后删除
  - `human-judgement` TR-2.4: 转为文档编辑打开右侧栏，可编辑并实时渲染
  - `human-judgement` TR-2.5: 赞/踩可输入文字反馈
  - `programmatic` TR-2.6: 重新生成仅在最后一条AI消息显示
- **Notes**: 按钮样式使用豆包风格圆角pill容器（bg-muted/40 rounded-full border）

## [ ] Task 3: 搜索结果链接跳转修复+验证
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 检查ToolCallBlock搜索结果渲染，确认每条结果标题使用`<a target="_blank" rel="noopener noreferrer" href={url}>`
  - 实际浏览器测试：触发搜索后展开结果，点击链接验证新标签页打开
  - 如有问题（如href为undefined、点击事件被阻止、a标签被button包裹等），修复
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: 搜索结果链接a标签包含target="_blank"和rel="noopener noreferrer"
  - `human-judgement` TR-3.2: 浏览器中点击搜索结果标题在新标签页打开

## [ ] Task 4: CGA量表题数核查+修正
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 核查scales.ts中各量表的questionCount和questions数组长度
  - PHQ-9: 应为9题（现有应正确）
  - GAD-7: 应为7题（现有应正确）
  - Mini-Cog: 应为3题（现有核查）
  - MMSE: 应为30题（现有核查，如果不足需补全题目）
  - PSQI: 官方18个条目组成7个成分，核实现有实现
  - 修正questionCount与questions.length不匹配的情况
  - 补全缺失题目
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `programmatic` TR-4.1: 每个scale的questionCount === questions.length
  - `programmatic` TR-4.2: PHQ-9=9, GAD-7=7, Mini-Cog=3, MMSE=30
  - `human-judgement` TR-4.3: 浏览器中CGA答题题目数与量表标准一致

## [ ] Task 5: CGA预录音频生成与播放系统
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 创建脚本`scripts/generate-cga-audio.ts`或API route用于生成CGA音频
  - 首次访问CGA时检查public/audio/cga/目录，如音频文件不存在则调用TTS API批量生成
  - 为每个量表的每道题生成音频：朗读题目文本+"。"+依次朗读选项（如"1.完全不会 2.好几天 3.一半以上天数 4.几乎每天"）
  - 文件命名：`{scaleId}_q{index}.mp3`，放到apps/mvp/public/audio/cga/
  - 修改CGAConversation组件，使用`<audio>`标签播放预录mp3文件，不再实时调用TTS
  - 实现CGA音频全局开关状态（localStorage持久化），默认开启（自动播放）
  - 播放/暂停按钮切换：播放时显示Volume2，暂停时显示VolumeX
  - 进入新题目时：若开关开启则自动播放；关闭则不播放
  - 切换题目时停止当前音频，播放新题音频（若开关开）
  - 返回量表选择界面时停止播放
  - 移除老年模式600ms自动跳题逻辑（Task 6也需要）
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-5.1: 首次进入CGA自动播放题目音频
  - `human-judgement` TR-5.2: 点击暂停按钮后后续题目不自动播放
  - `human-judgement` TR-5.3: 重新开启后后续题目恢复自动播放
  - `human-judgement` TR-5.4: 返回量表选择页音频停止
  - `programmatic` TR-5.5: 音频文件存在于public/audio/cga/目录

## [ ] Task 6: CGA语音识别增强+不自动跳题
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 在matchAnswerByVoice中添加a/b/c/d选项识别：
    - 支持"A"、"a"、"选项A"、"选项a"、"诶"、"诶选项"、"第一个"（已有）等
    - 注意中文"a"的发音可能被识别为"诶"、"欸"、"ei"等同音变体
  - a=选项1（index 0），b=选项2（index 1），c=选项3（index 2），d=选项4（index 3）
  - **移除所有自动跳题逻辑**：
    - 键盘选完后不自动next
    - 语音识别选完后不自动next
    - 老年模式600ms延迟跳转移除
    - 用户必须手动点击"下一题"按钮
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-6.1: matchAnswerByVoice包含a/b/c/d映射
  - `human-judgement` TR-6.2: 语音说"a"选中第一个选项但不跳转
  - `human-judgement` TR-6.3: 键盘按"1"选中第一个选项但不跳转
  - `human-judgement` TR-6.4: 点击"下一题"才前进

## [ ] Task 7: CGA多量表选择+批量作答+完成页重构
- **Priority**: high
- **Depends On**: Task 6
- **Description**:
  - 重构ScaleSelector组件：
    - 添加"全选"按钮，点击勾选所有量表
    - 每个量表可独立勾选checkbox
    - 已作答题量显示"已作答"badge且checkbox disabled
    - 所有量表都已作答时显示"所有量表已作答完毕"提示和"生成评估报告"按钮
  - 重构CGA流程：
    - 点击"开始作答"后，将选中量表的所有questions按顺序flatten成一个数组
    - 进度条显示"第X/总题数题"
    - 中途无量表切换界面，连续作答
  - 重构CGA完成页：
    - **修复bug**：完成后右侧栏不自动弹出（移除openRightPanel调用）
    - 中间聊天区域显示："✅ 作答完毕" + 副标题"{已完成量表名}已作答完成"
    - 一行三个按钮：
      1. "重新评估"：清空当前作答answers，重置到第0题，重新开始
      2. "继续作答其他量表"：关闭CGA视图，返回量表选择界面，已作答题量disabled
      3. "查看已作答量表评估报告"：调用LLM生成综合报告，在右侧栏显示（可编辑+导出）
  - localStorage持久化：
    - 当前作答进度（currentQuestionIndex、answers、selectedScales）保存到localStorage
    - refresh页面后恢复作答进度
    - 退出CGA时根据是否有报告生成决定是否保存
  - 退出逻辑：
    - 无报告/未完成：确认框"退出后当前进度将不会保存，确认退出吗？"
    - 已有报告：确认框"您已完成量表评估，是否要退出？"
    - 历史对话进入时显示上次报告，提供继续/重新/查看选项
- **Acceptance Criteria Addressed**: AC-5, AC-6, AC-7
- **Test Requirements**:
  - `human-judgement` TR-7.1: 全选按钮勾选所有量表
  - `human-judgement` TR-7.2: 批量作答中途无切换，进度正确
  - `human-judgement` TR-7.3: 完成后右侧栏不弹出，显示三按钮
  - `human-judgement` TR-7.4: 已作答题量在选择界面disabled
  - `human-judgement` TR-7.5: refresh后恢复进度
  - `human-judgement` TR-7.6: 退出确认框文案正确

## [ ] Task 8: 文件上传修复+MinerU API集成+文件上下文传递
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 创建Next.js API route `apps/mvp/src/app/api/mineru/parse/route.ts`：
    - 接收上传文件（FormData）
    - 调用MinerU API（NEXT_PUBLIC_MINERU_URL + NEXT_PUBLIC_MINERU_API_KEY）解析
    - 返回解析后的markdown文本
  - 修复FileUpload组件8文件限制bug：
    - 检查MAX_FILES或类似常量，确保支持最多8个文件
    - 检查文件添加逻辑中是否有splice/slice只保留前5个的问题
  - 五大处方流程中，用户上传文件后：
    - 显示上传进度/解析中状态
    - 调用MinerU API解析所有上传文件
    - 将解析结果整合到patientData上下文
    - 文件内容后续传给LLM作为信息来源
  - 允许只传语音/文本不传文件（即文件可选）
- **Acceptance Criteria Addressed**: FR-6.2
- **Test Requirements**:
  - `programmatic` TR-8.1: API route存在且可POST文件
  - `human-judgement` TR-8.2: 上传8个文件全部加载成功
  - `human-judgement` TR-8.3: 文件解析内容在五大处方生成时被LLM引用（可通过thinking内容验证）
- **Notes**: MinerU API文档需先确认接口格式，如不确定先用fetch调用测试

## [ ] Task 9: 本地知识库检索集成
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 方案：将本地知识库md文件复制到apps/mvp/public/knowledge/目录下（构建时或首次启动时）
  - 创建lib/knowledge.ts：
    - 加载public/knowledge/下所有md文件内容
    - 实现简单关键词匹配检索（按关键词出现频率排序，返回top 3-5个相关片段）
  - 创建API route `apps/mvp/src/app/api/knowledge/search/route.ts`：
    - 接收query参数
    - 在知识库md中检索相关片段
    - 返回结果（标题、片段、来源文件名）
  - 五大处方生成流程中：
    - 先调用知识库API检索
    - 有相关结果则优先使用知识库内容
    - 知识库无相关结果时才调用web_search联网搜索
  - 在ToolCallBlock或思考过程中体现使用了知识库（显示"已检索本地知识库"标签）
- **Acceptance Criteria Addressed**: AC-11
- **Test Requirements**:
  - `human-judgement` TR-9.1: 五大处方生成时调用了本地知识库
  - `programmatic` TR-9.2: API route返回相关片段
  - `human-judgement` TR-9.3: 知识库有结果时不触发联网搜索（或仅补充搜索）
- **Notes**: 关键词检索为简易实现（二阶段可升级为向量检索），但必须可用

## [ ] Task 10: 五大处方信息收集对话卡片增强（每轮4题+3轮上限+语音输入）
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  - 定义五大处方必需字段清单（参照hzj_case.json的basic_info核心字段）：年龄、性别、身高、体重、主要疾病/诊断、当前用药、主诉/主要健康问题
  - 增强InfoCollectionCard组件或创建PrescriptionInfoCard：
    - 每次显示最多4个待收集字段（问题）
    - 每个字段有label和输入区
    - 支持文本输入（input/textarea）
    - 支持语音输入（麦克风按钮，调用ASR识别后填入）
    - 有"提交"按钮
  - 对话流程：
    - 系统整合用户输入+文件解析结果
    - 判断缺失字段
    - 如缺失字段>0，发起卡片询问（每轮最多4个）
    - 用户回答后整合，仍有缺失则继续卡片（最多3轮）
    - 3轮后用已有信息生成
  - 信息收集期间已收集字段以InfoCollectionCard展示（绿色√）
  - 对话卡片样式参照Trae Work：圆角卡片、标题、表单字段、提交按钮
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `human-judgement` TR-10.1: 信息不全时弹出对话卡片
  - `human-judgement` TR-10.2: 每轮最多4个问题
  - `human-judgement` TR-10.3: 支持语音输入填写
  - `human-judgement` TR-10.4: 3轮后不再继续询问，用已有信息生成
- **Notes**: 不要一次弹出所有字段，分轮询问

## [ ] Task 11: 五大处方生成流程（健康画像→处方→JSON校验→Markdown）
- **Priority**: high
- **Depends On**: Task 9, Task 10
- **Description**:
  - 定义五大处方Zod Schema（参照五大处方报告模板.md）：
    - HealthProfile（健康画像）：basic_info、疾病史、用药史、评估结果总结
    - FivePrescriptions：medication_prescription（药物）、exercise_prescription（运动）、nutrition_prescription（营养）、psychological_prescription（心理）、rehabilitation_prescription（康复）
    - 每个prescription包含：具体建议、注意事项、循证来源
  - 修改system prompt，要求LLM输出JSON（先用```json块包裹，最终提取JSON）
  - 生成顺序：
    - Step 1: 根据收集的信息生成健康画像（先诊断）
    - Step 2: 根据健康画像生成五大处方（再开方）
    - Step 3: 用药审查（检查药物相互作用）
  - JSON校验：
    - 用Zod safeParse校验LLM输出
    - 校验失败则让LLM重试（最多2次）
    - 校验通过后将JSON转为Markdown格式
  - PII脱敏：确保在发送给LLM前调用desensitizeForLLM
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-11.1: Zod schema定义完整
  - `programmatic` TR-11.2: JSON校验失败触发重试
  - `human-judgement` TR-11.3: 最终Markdown包含五个处方板块
  - `programmatic` TR-11.4: 发送给LLM的文本中敏感信息已脱敏
- **Notes**: 生成过程中使用ToolCallBlock或thinking block显示进度

## [ ] Task 12: 右侧栏实时MD编辑器（实时编辑+实时渲染+导出）
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 创建MarkdownEditor组件：
    - 左右分栏布局（桌面端）/上下分栏（移动端）
    - 左侧/上：textarea编辑区（等宽字体，行号可选）
    - 右侧/下：MarkdownRenderer实时预览区
    - 使用useDeferredValue或debounce优化渲染性能（避免每次按键都立即重渲染）
  - 修改RightPanel：
    - 新增"doc-editor"面板类型（用于"转为文档编辑"）
    - 修改"prescription"、"cga"、"drug-review"面板内容区为MarkdownEditor
    - 头部工具栏保留ExportButton，添加复制按钮（复制渲染后的纯文本/Markdown）
    - 当用户编辑时，更新panelContent状态
    - 导出按钮使用编辑后的最新内容
  - ExportButton组件确认支持PDF/DOCX/MD三种格式
- **Acceptance Criteria Addressed**: AC-12
- **Test Requirements**:
  - `human-judgement` TR-12.1: 在编辑区输入Markdown，预览区实时渲染
  - `human-judgement` TR-12.2: 复制按钮复制内容到剪贴板
  - `human-judgement` TR-12.3: 导出按钮使用编辑后的内容导出PDF/DOCX/MD
  - `programmatic` TR-12.4: 编辑延迟使用debounce/throttle优化
- **Notes**: 不要用contentEditable的纯文本编辑，必须textarea源码+Markdown渲染预览分离

## [ ] Task 13: CGA评估报告生成（右侧栏可编辑+导出）
- **Priority**: medium
- **Depends On**: Task 7, Task 12
- **Description**:
  - "查看已作答量表评估报告"按钮逻辑：
    - 收集所有已完成量表的answers和计分结果
    - 构建CGA报告prompt（包含所有量表得分和解读）
    - 调用LLM生成综合评估报告Markdown
    - 生成过程显示thinking/tool_call进度
    - 完成后在右侧栏打开"cga"面板显示报告（使用MarkdownEditor可编辑）
  - "所有量表已作答完毕→生成评估报告"按钮逻辑同上
  - 报告包含：各量表得分、临床意义、综合评估、建议
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-13.1: 点击查看报告后右侧栏显示AI生成的综合报告
  - `human-judgement` TR-13.2: 报告可编辑并导出

## [ ] Task 14: Lint+Build+Agent逐条浏览器核查+修复循环+Git提交+长期规划更新
- **Priority**: high
- **Depends On**: Task 1-13
- **Description**:
  - 运行npm run lint，修复所有错误和警告
  - 运行npm run build，确认构建成功
  - 启动开发服务器（npm run dev）
  - **Agent必须自行使用浏览器工具，严格对照新任务.md的14条要求逐条核查**（不是泛泛测试，是逐条check）：
    1. 核查FR-1消息按钮：复制✓、语音播放（手动点击才播，不自动播）✓、分享弹ExportDialog（PNG/PDF/DOCX/MD+选范围）✓、点赞（含文字反馈）✓、点踩（含文字反馈）✓、重新生成（仅最后一条AI消息）✓、三点菜单（转为文档编辑+删除）✓、删除弹DeleteConfirmDialog（选范围+取消+确认）✓、转为文档编辑右侧栏实时MD✓
    2. 核查FR-2禁止自动播放：普通聊天（含老年模式）AI回复后不自动播放TTS；仅CGA内自动播放✓
    3. 核查FR-3加载动画：思考中spinner转圈（速率适中）；输出等待三点跳动✓
    4. 核查FR-4搜索链接：搜索结果标题点击后在新标签页打开真实网页✓
    5. 核查FR-5.1 CGA音频：预录mp3播放、默认自动播放、暂停后后续不播、返回选择页停止、开关持久化✓
    6. 核查FR-5.2语音识别：a/b/c/d/1/2/3/中文数字/选项文本都能识别；识别后不自动跳题✓
    7. 核查FR-5.3多选+批量作答：全选按钮、勾选多个、批量作答无切换、进度正确✓
    8. 核查FR-5.4完成页：右侧栏不自动弹出、中间栏显示三按钮✓
    9. 核查FR-5.5退出保存：无报告退出确认文案、有报告退出确认文案、localStorage恢复✓
    10. 核查FR-5.6全量表完成：所有量表答完显示"所有量表已作答完毕"+生成报告按钮✓
    11. 核查FR-5.7题数：PHQ-9=9、GAD-7=7、Mini-Cog=3、MMSE=30✓
    12. 核查FR-6.2 MinerU+文件上传：上传8个文件全部成功、MinerU解析调用、内容传给LLM✓
    13. 核查FR-6.3信息卡片：每轮最多4题、支持语音/文本、3轮上限✓
    14. 核查FR-6.4-6.6知识库+JSON+生成顺序：本地知识库优先检索、Zod校验JSON、健康画像→处方顺序、PII脱敏✓
    15. 核查FR-6.7右侧栏编辑器：textarea源码+实时渲染预览、复制按钮、PDF/DOCX/MD导出✓
    16. 核查FR-7导出：所有导出按钮支持PDF/DOCX/MD✓
  - **发现不符合的问题必须立即修改代码，修改后重新核查，直到所有条目全部通过**
  - 核查不通过不能提交代码
  - git add所有修改文件
  - git commit使用conventional commits格式
  - 更新docs/长期规划.md，记录0009交付
- **Acceptance Criteria Addressed**: AC-1 through AC-14
- **Test Requirements**:
  - `programmatic` TR-14.1: npm run lint 0错误
  - `programmatic` TR-14.2: npm run build成功
  - `human-judgement` TR-14.3: Agent浏览器逐条核查新任务.md 14条全部通过，不通过的修复后重测
  - `human-judgement` TR-14.4: checklist.md全部checkpoint打勾
- **Notes**: 这是最终验收环节，必须agent亲自操作浏览器逐条对照新任务.md验证，不能靠"应该可以"蒙混过关
