# 0010 CGA评估系统重构与ChatArea集成 - Implementation Plan

## [ ] Task 1: 清理ChatArea旧CGA代码并修复导入
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 移除所有旧的CGA per-session状态变量（cgaSelectedScale、cgaCompleted、cgaAnswers as Record<sessionId,...>、cgaAutoAdvanceRef、cgaKeyboardCtxRef等）
  - 移除所有旧的CGA handler函数（handleSelectScale、handleAnswerQuestion、handlePrevQuestion、handleNextQuestion、handleCGAMicStart、handleCGARecordingCancel/Finish、handleRestartCurrentScale、handleReselectScale、stopTTS/playTTS等相关引用）
  - 移除旧的键盘事件处理useEffect（cgaKeyboardCtxRef）
  - 清理导入：移除未使用的lucide图标（X、Mic、Volume2、VolumeX、CheckCircle2等在CGAConversation中已使用的），添加Scale类型导入
  - 修复useEffect依赖数组中对cgaSelectedScale的引用
  - 保留新状态变量：cgaMode、cgaSelectedScaleIds、cgaCompletedScaleIds、cgaAnswers、cgaCurrentIndex、cgaResults、showExitConfirm、exitConfirmType
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-1.1: tsc --noEmit 中关于找不到cgaSelectedScale、cgaKeyboardCtxRef、cgaAutoAdvanceRef、stopTTS等旧变量的错误全部消失
  - `programmatic` TR-1.2: 不再有对per-session状态对象（Record<string,...>形式的cgaSelectedScale等）的引用
- **Notes**: CGAConversation组件内部自带音频、录音、语音识别功能，ChatArea不需要重复实现

## [ ] Task 2: 实现新的CGA handler函数和状态逻辑
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 添加handleStartCGA：从ScaleSelector的onStart调用，设置cgaMode='answering'
  - 添加handleCGAComplete(results: ScaleResult[])：从CGAConversation的onComplete调用，将完成的量表ID加入cgaCompletedScaleIds，保存results到cgaResults
  - 添加handleCGAContinue：从CGAConversation的onContinue调用，返回select模式，重置答题索引和答案（保留已完成量表状态）
  - 添加handleCGAGenerateReport：从onGenerateReport调用，触发LLM报告生成流程
  - 添加handleCGAExit：从CGAConversation的onExit和头部退出按钮调用，判断状态并显示退出确认
  - 添加handleSaveProgress(data)：从CGAConversation的onSaveProgress调用，更新cgaCurrentIndex和cgaAnswers
  - 添加handleRestartCGA：从"重新评估"流程重置所有状态
  - 修复localStorage的save/load逻辑，使用正确的扁平状态
  - 完善退出确认doExitCGA函数：根据exitConfirmType决定是否清除进度
  - 添加cgaReportGenerating状态用于报告加载
- **Acceptance Criteria Addressed**: AC-1, AC-6, AC-7
- **Test Requirements**:
  - `programmatic` TR-2.1: 所有handler函数类型正确，无implicit any错误
  - `human-judgement` TR-2.2: localStorage保存/恢复逻辑正确（刷新页面后进度不丢失）
- **Notes**: 注意"继续作答其他量表"时只重置当前选中量表的答题状态，不清除已完成的量表

## [ ] Task 3: 重写ChatArea中CGA相关的渲染逻辑
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 移除旧的内联CGA UI代码（showScaleSelector/showCgaQuiz/cgaFinished三段JSX，约1697-2010行）
  - 替换为：
    - cgaMode='select'时：渲染ScaleSelector组件（传入正确props）+ 免责声明
    - cgaMode='answering'时：渲染CGAConversation组件（传入选中的scales数组、initialAnswers、initialIndex、所有回调）
  - 修复头部标题逻辑：
    - cgaMode='select'："老年综合评估 — 选择量表"
    - cgaMode='answering'："老年综合评估"
    - 退出按钮在两个模式都显示
  - 修复ChatInput显示条件：cgaMode为select或answering时隐藏
  - 修复ScaleSelector的props调用（onStart而不是onSelect，传入mode等）
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: tsc编译无错误
  - `human-judgement` TR-3.2: 量表选择页正确显示全选按钮、量表列表、已完成badge
  - `human-judgement` TR-3.3: 答题页正确显示CGAConversation（进度条、题目、选项、音频、语音按钮等）
  - `human-judgement` TR-3.4: 完成页显示三按钮，右侧栏不自动弹出
- **Notes**: CGAConversation内部自己管理isCompleted状态和完成页渲染，ChatArea只需在answering模式下始终渲染它

## [ ] Task 4: 实现LLM报告生成和右侧栏展示
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 实现generateCGAReport函数：
    1. 收集所有已完成量表的结果（cgaResults）
    2. 构造系统提示和用户提示（区分患者/医生角色）
    3. 处理PHQ-9自杀风险特殊提示
    4. 调用streamChat流式生成报告
    5. 通过setRightPanel('cga')和setPanelContent/appendPanelContent实时更新右侧栏
    6. 生成完成后在对话中添加提示消息（带查看报告按钮）
    7. 错误时生成降级报告
  - 从ScaleSelector的onGenerateReport（所有量表完成时的大按钮）和CGAConversation的onGenerateReport都调用此函数
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `human-judgement` TR-4.1: 点击"查看已作答量表评估报告"后右侧栏打开并流式显示报告
  - `human-judgement` TR-4.2: 报告包含各量表得分、解读、建议
  - `programmatic` TR-4.3: tsc编译无错误
- **Notes**: 参考旧代码中的report generation逻辑（约1479-1560行），但改为支持多量表结果

## [ ] Task 5: TypeScript检查、Lint和Build验证
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 运行npx tsc --noEmit确保0错误
  - 运行npm run lint确保0错误0警告
  - 运行npm run build确保构建成功
  - 修复所有发现的问题
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `programmatic` TR-5.1: tsc --noEmit 输出为空（0错误）
  - `programmatic` TR-5.2: npm run lint 输出0 errors, 0 warnings
  - `programmatic` TR-5.3: npm run build 成功完成
- **Notes**: 必须实际运行命令，不能空谈"应该可以"
