# 0011 严格需求合规实现 - The Implementation Plan (Decomposed and Prioritized Task List)

## [ ] Task 1: 紧急Bug修复 - 移除普通聊天自动TTS + 确认加载动画
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 彻底搜索代码，移除所有普通聊天场景（包括老年模式）的自动TTS播放逻辑
  - 确认ChatArea、MessageBubble等组件无autoRead/autoPlay相关调用
  - 调整thinking-spinner动画速率为1.5s（适中，不要太快）
  - 确认三点加载动画样式正确（typing-dot）
  - 确认停止按钮无animate-pulse类
- **Acceptance Criteria Addressed**: AC-3, AC-7
- **Test Requirements**:
  - `programmatic` TR-1.1: grep搜索代码无autoReadIfSeniorMode/autoPlay在普通聊天场景
  - `programmatic` TR-1.2: globals.css中thinking-spinner animation-duration为1.5s
  - `human-judgement` TR-1.3: 普通聊天AI回复完成后不自动播放语音
  - `human-judgement` TR-1.4: 思考转圈动画速率适中，文本三点动画速率适中
  - `human-judgement` TR-1.5: 停止按钮静态显示，无闪烁

## [ ] Task 2: 消息操作按钮完善 - 删除和分享默认选中逻辑
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改ChatArea.tsx中分享按钮处理逻辑：点击单条消息分享时，默认选中该AI消息+前面紧挨着的用户提问（一组问答）
  - 修改删除功能：点击三点菜单删除时，打开DeleteConfirmDialog，默认选中该AI消息+对应的用户提问，支持勾选/取消其他消息，有取消按钮
  - 检查DeleteConfirmDialog语法正确性（之前DialogClose render prop可能有问题）
  - 确保转为文档编辑按钮正确打开右侧栏doc-editor，内容为该条AI消息纯文本
  - 确保ExportDialog支持PNG/PDF/DOCX/MD四种格式（分享用）
  - 右侧栏编辑器导出只支持PDF/DOCX/MD三种格式
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-4, AC-5, AC-6, AC-8
- **Test Requirements**:
  - `human-judgement` TR-2.1: 点击单条AI消息分享，对话框默认勾选该AI+对应提问
  - `human-judgement` TR-2.2: 点击删除，确认框默认勾选该AI+对应提问，有取消按钮，确认后删除
  - `human-judgement` TR-2.3: 转为文档编辑后右侧栏显示Markdown编辑器，内容正确
  - `human-judgement` TR-2.4: 右侧栏导出按钮只有PDF/DOCX/MD三个选项
  - `programmatic` TR-2.5: DeleteConfirmDialog无语法错误，可正常渲染

## [ ] Task 3: 搜索结果链接跳转修复
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 检查SearchResultCard和ToolCallBlock组件
  - 确保所有搜索结果标题链接使用<a target="_blank" rel="noopener noreferrer">
  - 移除任何e.preventDefault()阻止默认跳转的代码
  - 检查CitationPopover中的"查看原文"按钮，确保window.open正确打开新标签
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `programmatic` TR-3.1: 搜索结果链接标签使用target="_blank" rel="noopener noreferrer"
  - `programmatic` TR-3.2: 代码中无e.preventDefault()在链接点击处
  - `human-judgement` TR-3.3: 点击搜索结果标题在新标签页打开网页

## [ ] Task 4: CGA量表功能完善 - 不自动跳题+播放状态记忆+音频逻辑
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 修改CGAConversation组件：选择选项（手动或语音识别）后不自动跳转下一题，用户需点击"下一题"按钮
  - 语音答题识别：支持识别"a"/"b"/"c"/"d"、"选项a"/"选项1"/数字1-4、选项文本
  - 播放状态记忆：用state或localStorage记录用户是否开启自动播放，切换题目时维持选择
  - 用户关闭播放后，后续题目不自动播放；用户打开播放后，后续题目自动播放
  - 返回量表选择页面时停止所有音频播放
  - 若没有预录音频文件，保持TTS实时生成但实现播放状态逻辑（预录音频功能预留接口）
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `human-judgement` TR-4.1: 选完选项后停留在当前题，需点下一题才进入下一题
  - `human-judgement` TR-4.2: 语音说"a"或"选项1"能正确选中对应选项
  - `human-judgement` TR-4.3: 点播放/停止按钮后，后续题目维持该播放状态
  - `human-judgement` TR-4.4: 返回量表选择页时音频停止

## [ ] Task 5: CGA完成页和量表选择逻辑重构
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 修复CGA完成后右侧栏自动弹出的bug：移除所有openRightPanel自动调用
  - 完成页中间栏显示："作答完毕"文字 + 已完成量表列表（多个则逗号分隔）
  - 三个按钮并列：「重新评估」、「继续作答其他量表」、「查看已作答量表评估报告」
  - 「重新评估」：清空当前作答，重新开始当前/选中量表
  - 「继续作答其他量表」：返回量表选择页，已完成量表标记为"已作答"且disabled不可勾选
  - 「查看已作答量表评估报告」：整合所有已完成量表结果，调用LLM生成报告，在右侧栏Markdown编辑器显示，可编辑/复制/导出
  - ScaleSelector组件：添加全选按钮；支持多选；已完成量表显示已作答状态禁用；所有量表完成后显示"所有量表已作答完毕"提示和生成报告按钮
  - 批量作答：选中多个量表后，将所有量表问题按顺序拼接，一次性作答，中途无量表切换界面
  - 进度保持：localStorage保存作答进度，不退出则不丢失
  - 退出逻辑：实现退出确认对话框，根据是否有作答/报告显示不同文案
- **Acceptance Criteria Addressed**: AC-11, AC-12
- **Test Requirements**:
  - `human-judgement` TR-5.1: 完成量表后右侧栏不自动弹出，中间显示三按钮
  - `human-judgement` TR-5.2: 继续作答其他量表返回选择页，已完成量表不可选
  - `human-judgement` TR-5.3: 量表选择页有全选按钮，支持多选
  - `human-judgement` TR-5.4: 选中多个量表后一次性答完所有题
  - `human-judgement` TR-5.5: 查看报告后右侧栏显示编辑器，可导出
  - `human-judgement` TR-5.6: 所有量表完成后显示提示和生成报告按钮

## [ ] Task 6: 文件上传修复 - 支持8个文件+MinerU API集成
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 检查FileUpload组件，修复只能上传5个文件的bug，支持最多8个
  - 实现/修复MinerU API解析接口（app/api/mineru/parse/route.ts）
  - 文件上传后调用MinerU解析，提取markdown内容
  - 若MinerU API未配置（环境变量为空），则降级：提示用户"文档解析服务未配置，将读取文件文本内容"，并直接读取文本类文件（md/txt），图片/PDF提示无法解析
  - 解析后的文件内容整合到用户信息中，作为上下文传给LLM
  - 检查文件上传后的展示标签（FileTag组件），显示正确文件名/大小/图标
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `human-judgement` TR-6.1: 可同时选择8个文件上传，全部显示
  - `programmatic` TR-6.2: MinerU API路由存在，可接受POST请求
  - `human-judgement` TR-6.3: 上传md文件后内容可被解析（降级模式下）
  - `programmatic` TR-6.4: 文件上传数量限制为8

## [ ] Task 7: 五大处方流程完整实现
- **Priority**: high
- **Depends On**: Task 6
- **Description**: 
  - 五大处方入口固定欢迎语：点击按钮后立即显示固定欢迎语（参照getOpeningMessage），不调用LLM
  - 实现信息收集逻辑：
    - 参照hzj_case.json定义输入模板字段
    - 用户上传文件+输入文本/语音后，先MinerU解析文件
    - 整合所有信息，对照模板判断缺失字段
    - 信息缺失时显示QuestionCard对话卡片（每轮最多4个问题），支持文本/语音回答
    - 每轮回答后更新信息，若仍缺失则发起下一轮，最多3轮
    - 超过3轮用已有信息生成
  - PII隐私脱敏：信息传给LLM前调用desensitizeForLLM脱敏
  - 生成流程：
    - 第一步：生成用户健康画像（先诊断）
    - 第二步：根据健康画像生成五大处方（运动/营养/心理/用药/戒烟限酒），做好用药审查（药物相互作用检查）
    - 第三步：优先检索本地知识库，找不到再联网搜索
  - 输出处理：
    - 参照五大处方报告模板，要求LLM输出JSON结构化结果
    - 用Zod schema校验JSON
    - 校验通过后转为Markdown格式
    - 在右侧栏Markdown编辑器显示，可编辑/复制/导出（PDF/DOCX/MD）
- **Acceptance Criteria Addressed**: AC-14
- **Test Requirements**:
  - `human-judgement` TR-7.1: 点击五大处方立即显示固定欢迎语，无加载
  - `human-judgement` TR-7.2: 信息缺失时显示对话卡片，每轮4题，最多3轮
  - `programmatic` TR-7.3: PII脱敏函数正常工作
  - `human-judgement` TR-7.4: 生成后右侧栏显示五大处方Markdown，可编辑导出
  - `programmatic` TR-7.5: 本地知识库检索函数存在

## [ ] Task 8: 右侧栏Markdown编辑器完善
- **Priority**: medium
- **Depends On**: Task 2, Task 5, Task 7
- **Description**: 
  - 检查RightPanel组件和MarkdownEditor组件
  - 确保编辑器右上角有复制按钮（复制全部内容到剪贴板）
  - 确保编辑器右上角有导出按钮，支持PDF/DOCX/MD三种格式
  - 编辑器实时编辑，预览同步更新
  - 转为文档编辑、CGA报告、五大处方都使用同一个编辑器组件
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-8.1: 右侧栏编辑器有复制按钮，点击复制内容
  - `human-judgement` TR-8.2: 右侧栏导出按钮有PDF/DOCX/MD三个选项
  - `human-judgement` TR-8.3: 编辑内容后预览实时更新

## [ ] Task 9: Lint和Build验证
- **Priority**: high
- **Depends On**: Task 2, Task 3, Task 5, Task 6, Task 7, Task 8
- **Description**: 
  - 运行npm run lint，修复所有错误和警告
  - 运行npm run build，确保Next.js build成功，TypeScript类型检查通过
  - 修复所有发现的问题
- **Acceptance Criteria Addressed**: AC-15
- **Test Requirements**:
  - `programmatic` TR-9.1: npm run lint输出0 errors, 0 warnings
  - `programmatic` TR-9.2: npm run build成功，无TypeScript错误

## [ ] Task 10: 浏览器全量核查+修复循环
- **Priority**: high
- **Depends On**: Task 9
- **Description**: 
  - 使用integrated_browser访问http://localhost:3000
  - 逐条对照新任务.md的12条需求（1/3/4/5/7/8/9/10/11/12/13/14）进行核查
  - 每条需求都要实际点击操作验证功能真实可用
  - 发现不符合的问题立即修复代码
  - 修复后重新运行lint+build，再重新核查
  - 直到所有需求都通过核查
- **Acceptance Criteria Addressed**: AC-16
- **Test Requirements**:
  - `human-judgement` TR-10.1: 每条需求都有核查记录和截图/操作结果
  - `human-judgement` TR-10.2: 所有需求验证通过
  - `programmatic` TR-10.3: 核查后lint和build仍通过

## [ ] Task 11: Git提交+长期规划更新
- **Priority**: high
- **Depends On**: Task 10
- **Description**: 
  - git add所有修改文件
  - git commit使用conventional commit格式，描述清楚所有修复和完善内容
  - 更新docs/长期规划.md，记录本次0011任务完成情况
- **Acceptance Criteria Addressed**: N/A
- **Test Requirements**:
  - `programmatic` TR-11.1: git commit成功
  - `programmatic` TR-11.2: 长期规划.md已更新记录
