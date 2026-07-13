# 0010 CGA评估系统重构与ChatArea集成 - Product Requirement Document

## Overview
- **Summary**: 完成CGA老年综合评估系统的重构，将已重构的ScaleSelector和CGAConversation组件正确集成到ChatArea中，实现多量表选择、批量作答、完成页三按钮、localStorage进度持久化、退出确认、报告生成等完整功能。
- **Purpose**: 当前ChatArea.tsx处于新旧代码混合状态，存在大量TypeScript错误（引用了不存在的旧状态变量和函数），无法编译运行。需要彻底清理旧CGA内联代码，使用新的自包含CGAConversation组件，完善状态管理和回调逻辑。
- **Target Users**: 老年患者、老年科医生

## Goals
1. 清理ChatArea.tsx中所有旧的CGA内联代码（旧状态变量、旧handler函数、旧渲染UI）
2. 正确集成已重构的ScaleSelector和CGAConversation组件
3. 实现完整的CGA流程：选量表→批量作答→完成页三按钮→生成报告
4. 实现localStorage进度持久化（页面刷新后恢复进度）
5. 实现退出确认对话框（区分无进度/有报告两种场景）
6. 实现报告生成LLM调用，结果在右侧栏展示
7. TypeScript 0错误，lint 0错误，build成功

## Non-Goals (Out of Scope)
- 不修改ScaleSelector.tsx和CGAConversation.tsx的已有功能（已实现多量表、音频、语音识别、完成页等）
- 不实现预录音频批量生成（CGAConversation当前使用/api/cga/audio端点动态生成，符合Task 5+6要求）
- 不实现Task 13的完整报告生成（本次只做按钮回调和基础LLM报告调用）
- 不修改五大处方、用药审查等其他功能

## Background & Context
- ScaleSelector.tsx已重构完成：支持全选、已完成badge、完成态显示、props接口正确
- CGAConversation.tsx已重构完成：支持多量表批量作答、内部管理答题状态、音频播放（/api/cga/audio）、语音识别（useAudioRecorder+ASR）、完成页三按钮（重新评估/继续作答/查看报告）、不自动弹出右侧栏
- ChatArea.tsx处于半重构状态：定义了新状态变量（cgaMode/cgaSelectedScaleIds等），但旧代码（per-session对象状态、TTS函数、录音refs等）未删除，导致60+个TS错误
- CGAConversation是自包含组件，内部处理：题目展示、选项选择、进度条、音频播放、语音录音识别、完成页展示

## Functional Requirements

### FR-1: ChatArea状态管理重构
- 使用扁平状态（非per-session对象）：cgaMode('select'|'answering')、cgaSelectedScaleIds、cgaCompletedScaleIds、cgaAnswers、cgaCurrentIndex、cgaResults
- 移除所有旧状态：cgaSelectedScale(Record)、cgaCompleted(Record)、cgaAnswers(Record per session)、cgaAutoAdvanceRef、cgaKeyboardCtxRef、所有TTS/录音相关状态和refs
- 初始化时从localStorage恢复进度

### FR-2: ScaleSelector正确集成
- cgaMode='select'时显示ScaleSelector
- 传入正确props：scales、selectedScaleIds、onSelectionChange、completedScaleIds、onStart、onGenerateReport、mode
- mode='continue'当有已完成量表时
- onStart：设置cgaMode='answering'
- onGenerateReport：触发报告生成流程

### FR-3: CGAConversation正确集成
- cgaMode='answering'时显示CGAConversation
- 传入正确props：scales（选中的量表数组）、initialAnswers、initialIndex、onComplete、onContinue、onGenerateReport、onExit、onSaveProgress
- 组件内部管理isCompleted状态和完成页展示
- onComplete：将结果添加到cgaCompletedScaleIds和cgaResults
- onContinue：返回select模式（保留已完成状态）
- onGenerateReport：触发报告生成
- onExit：显示退出确认对话框
- onSaveProgress：更新状态并保存到localStorage

### FR-4: localStorage进度持久化
- key: "gerclaw-cga-progress-v2"
- 保存：selectedScaleIds、completedScaleIds、currentQuestionIndex、answers、savedAt
- 组件初始化时检查localStorage，有未完成进度则恢复
- 进度变化时自动保存
- 退出确认后清除/保留进度

### FR-5: 退出确认逻辑
- 点击退出按钮时：
  - 无已完成量表且无报告：弹出"退出后当前进度将不会保存，确认退出吗？"，确认后清除localStorage并退出
  - 有已完成量表或有报告：弹出"您已完成量表评估，是否要退出？"，确认后保存进度并退出
- 使用现有Dialog组件
- 适老化：确认按钮≥48px

### FR-6: 报告生成
- "查看已作答量表评估报告"和"生成评估报告"按钮点击后：
  - 调用LLM生成综合报告（基于所有已完成量表的结果）
  - 打开右侧栏cga面板
  - 流式输出报告内容到右侧栏
  - 完成后在对话中添加提示消息
- 报告生成中显示loading状态
- 有错误时显示降级报告
- PHQ-9自杀风险特殊处理

### FR-7: 头部标题和输入框控制
- cgaMode='select'时头部显示"老年综合评估 — 选择量表"
- cgaMode='answering'时头部显示"老年综合评估"和退出按钮
- CGA流程中隐藏ChatInput

## Non-Functional Requirements
- **NFR-1**: TypeScript 0错误
- **NFR-2**: npm run lint 0错误0警告
- **NFR-3**: npm run build成功
- **NFR-4**: 适老化：老年模式按钮≥48px，文字≥18px
- **NFR-5**: 医疗安全：报告带免责声明，高风险提示就医
- **NFR-6**: 保留Task 5+6的音频和语音识别功能（CGAConversation内部已实现）

## Constraints
- **Technical**: Next.js + React + TypeScript + shadcn/ui + Zustand
- **Dependencies**: CGAConversation和ScaleSelector组件已存在且功能完整
- **Key Constraint**: 不修改CGAConversation和ScaleSelector的内部逻辑，只做集成

## Assumptions
- CGAConversation组件已正确实现所有答题UI逻辑（音频、语音识别、完成页等）
- /api/cga/audio端点可正常工作
- recognizeAudio和useAudioRecorder已正确实现
- 一次只有一个CGA流程（不需要per-session状态隔离）

## Acceptance Criteria

### AC-1: TypeScript编译通过
- **Given**: 所有代码修改完成
- **When**: 运行npx tsc --noEmit
- **Then**: 0错误
- **Verification**: `programmatic`

### AC-2: Lint检查通过
- **Given**: 所有代码修改完成
- **When**: 运行npm run lint
- **Then**: 0错误0警告
- **Verification**: `programmatic`

### AC-3: Build成功
- **Given**: 所有代码修改完成
- **When**: 运行npm run build
- **Then**: 构建成功
- **Verification**: `programmatic`

### AC-4: 多量表选择流程
- **Given**: 用户进入CGA
- **When**: 在量表选择页勾选多个量表点击开始作答
- **Then**: 进入批量答题流程，进度条显示总题数，CGAConversation正常渲染
- **Verification**: `human-judgment`

### AC-5: 完成页三按钮
- **Given**: 用户答完所有题目
- **When**: 答题完成
- **Then**: 中间栏显示完成页（绿色对勾、"作答完毕"、量表名列表、三个按钮），右侧栏不自动弹出
- **Verification**: `human-judgment`

### AC-6: 退出确认
- **Given**: 用户在答题过程中点击退出
- **When**: 无已完成量表
- **Then**: 弹出确认对话框提示进度不保存
- **Verification**: `human-judgment`

### AC-7: localStorage持久化
- **Given**: 用户答题中途刷新页面
- **When**: 页面重新加载
- **Then**: 恢复到之前的答题进度
- **Verification**: `human-judgment`

### AC-8: 报告生成
- **Given**: 用户点击"查看已作答量表评估报告"
- **When**: LLM报告生成完成
- **Then**: 右侧栏打开显示报告内容
- **Verification**: `human-judgment`

## Open Questions
- 无
