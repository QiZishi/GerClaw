# GerClaw CGA多选与功能修复 - Implementation Plan

## [ ] Task 1: 集成CGAConversation组件到ChatArea，替换单选CGA逻辑
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修改ChatArea.tsx，将当前的单选ScaleSelector+内联答题UI替换为使用CGAConversation组件
  - CGAConversation支持多选量表、预录音频播放、音频状态持久化、完成页三按钮
  - 添加cgaSelectedScales状态（数组，支持多选）、cgaCompletedScales状态（记录已完成量表）
  - 集成CGAConversation的onComplete/onContinue/onGenerateReport/onExit回调
  - onContinue返回量表选择页，已完成量表标记为"已作答"不可选
  - onGenerateReport生成综合评估报告到右侧栏
  - 确保音频在退出/返回选择页时停止
  - 保留键盘快捷键支持和语音答题功能
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, FR-1~FR-7, FR-22, FR-23
- **Test Requirements**:
  - `human-judgment` TR-1.1: 点击CGA按钮显示多选量表页，有全选按钮
  - `human-judgment` TR-1.2: 选择PHQ-9+GAD-7后点击开始作答，进入答题
  - `human-judgment` TR-1.3: 第一题自动播放（文件存在时），停止后下一题不自动播放
  - `human-judgment` TR-1.4: 选项点击高亮，不自动跳转，需点下一题
  - `human-judgment` TR-1.5: 答完后显示完成页三按钮
  - `human-judgment` TR-1.6: 点击"继续作答其他量表"返回选择页，已完成量表显示"已作答"badge
  - `human-judgment` TR-1.7: 返回选择页时音频停止
- **Notes**: 需要移除ChatArea中原有的单量表CGA状态和UI（cgaSelectedScale单个string、内联答题JSX等），改用多量表状态+CGAConversation组件

## [ ] Task 2: 修复搜索结果链接可点击跳转（新标签页）
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 检查ToolCallBlock.tsx中搜索结果的渲染，确保标题是<a>标签且target="_blank" rel="noopener noreferrer"
  - 检查SourceReferences.tsx中"查看原文"链接，确保新标签页打开
- **Acceptance Criteria Addressed**: AC-5, FR-8, FR-9
- **Test Requirements**:
  - `human-judgment` TR-2.1: 搜索结果标题可点击，新标签页打开
  - `human-judgment` TR-2.2: SourceReferences角标点击"查看原文"新标签页打开

## [ ] Task 3: 验证消息操作按钮功能完整性
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 检查MessageBubble中的操作按钮行：赞/踩/复制/重新生成(仅最后一条)/语音播放/导出/三点菜单
  - 验证复制功能（navigator.clipboard + toast）
  - 验证语音播放（TTS播放/停止，默认不自动播放）
  - 验证导出按钮打开ExportDialog
  - 验证点赞/点踩toast反馈
  - 验证三点菜单包含"转为文档编辑"和"删除"
  - 验证"转为文档编辑"发送到右侧编辑器
  - 验证删除确认框
- **Acceptance Criteria Addressed**: AC-6, FR-10~FR-17
- **Test Requirements**:
  - `human-judgment` TR-3.1: 每条AI消息底部有操作按钮行
  - `human-judgment` TR-3.2: 复制按钮显示"已复制"toast
  - `human-judgment` TR-3.3: 语音播放按钮点击播放/停止
  - `human-judgment` TR-3.4: 导出按钮弹出ExportDialog
  - `human-judgment` TR-3.5: 点赞/点踩显示"感谢反馈"
  - `human-judgment` TR-3.6: 三点菜单包含"转为文档编辑"和"删除"

## [ ] Task 4: 验证五大处方固定欢迎语和文件上传限制
- **Priority**: medium
- **Depends On**: None
- **Description**:
  - 确认五大处方点击后显示固定欢迎语（不调用LLM）——代码中已有，但需验证
  - 确认constants.ts中maxFileCount=10
  - 确认医生模式显示用药审查和健康画像按钮，患者模式不显示
  - 确认动画速度：thinking-spinner 1.5s，typing-pulse 1.2s
- **Acceptance Criteria Addressed**: AC-7, AC-8, AC-10, FR-18~FR-21, NFR-3, NFR-4
- **Test Requirements**:
  - `programmatic` TR-4.1: constants.ts中maxFileCount=10
  - `human-judgment` TR-4.2: 五大处方立即显示欢迎语
  - `human-judgment` TR-4.3: 医生模式有用药审查/健康画像按钮，患者模式无
  - `programmatic` TR-4.4: CSS中thinking-spinner动画1.5s，typing-pulse 1.2s

## [ ] Task 5: 运行lint和build验证
- **Priority**: high
- **Depends On**: Task 1, Task 2, Task 3, Task 4
- **Description**:
  - 运行npm run lint，确保0错误0警告
  - 运行npm run build，确保编译成功
  - 如有错误修复后重新运行
- **Acceptance Criteria Addressed**: AC-9, NFR-1, NFR-2
- **Test Requirements**:
  - `programmatic` TR-5.1: npm run lint输出0错误0警告
  - `programmatic` TR-5.2: npm run build成功完成
