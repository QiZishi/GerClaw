# GerClaw CGA多选与功能修复 - Product Requirement Document

## Overview
- **Summary**: 修复老年综合评估(CGA)模块的单选问题，集成支持多量表选择、预录音频播放、完成页三按钮的CGAConversation组件；同时修复搜索链接跳转、消息操作按钮、导出功能、五大处方固定欢迎语、文件上传限制等功能问题。
- **Purpose**: 确保系统符合新任务.md中所有功能要求，用户可正常进行多量表CGA评估，所有消息操作按钮可用，搜索链接可跳转，文件上传支持10个文件。
- **Target Users**: 老年患者、老年科医生

## Goals
- CGA量表选择支持多选，已完成量表显示"已作答"badge且不可选
- CGA答题流程：第一题自动播放预录音频、停止后切换题目不自动播放、恢复后自动播放
- CGA完成页显示"作答完毕"和三个按钮（重新评估/继续作答其他量表/查看评估报告）
- 量表题数正确：PHQ-9=9题，GAD-7=7题，PSQI=7题，MMSE=30题
- 搜索结果链接可点击，新标签页打开
- 消息操作按钮完整：赞/踩/复制/重新生成/语音播放/导出/三点菜单
- 导出功能支持PDF/DOCX/Markdown格式
- 五大处方点击后立即显示固定欢迎语（不调用LLM）
- 文件上传最多支持10个文件
- 医生模式显示用药审查和健康画像按钮，患者模式不显示
- 所有医疗内容带免责声明
- npm run lint 0错误0警告，npm run build成功

## Non-Goals (Out of Scope)
- 不实现本地知识库加载（/api/knowledge/retrieve保持503）
- 不实现TTS实时语音生成（CGA使用预录音频）
- 普通聊天不自动播放TTS
- 不添加新任务.md以外的功能

## Background & Context
- 当前ChatArea.tsx中的CGA实现是单选模式（singleSelect=true），需要替换为多选模式
- 已存在CGAConversation.tsx组件，支持多选、预录音频、完成页三按钮，但未被ChatArea集成
- Sidebar下拉菜单已修复（DropdownMenuGroup包裹）
- 动画速度需要确认：thinking-spinner 1.5s，typing-pulse 1.2s

## Functional Requirements
- **FR-1**: CGA量表选择页支持多选+全选，已完成量表显示"已作答"badge且禁用
- **FR-2**: CGA进入答题后第一题自动播放预录音频，停止按钮切换为手动模式，播放按钮恢复自动模式
- **FR-3**: CGA选项点击后高亮，不自动跳转，需手动点"下一题"
- **FR-4**: CGA支持键盘数字1-4选择选项，语音识别a/b/c/d/数字逻辑存在
- **FR-5**: CGA完成页显示"作答完毕"+量表名+三个按钮
- **FR-6**: CGA返回量表选择页时停止音频播放
- **FR-7**: 所有量表答完显示"所有量表已作答完毕"+"生成评估报告"按钮
- **FR-8**: 搜索结果标题为可点击链接，新标签页打开
- **FR-9**: SourceReferences引用角标点击"查看原文"新标签页打开
- **FR-10**: 每条AI回复有操作按钮：赞/踩/复制/重新生成(仅最后一条)/语音播放/导出/三点菜单
- **FR-11**: 复制按钮点击后复制到剪贴板，显示"已复制"toast，2秒消失
- **FR-12**: 语音播放按钮默认不自动播放，点击播放/再次点击停止
- **FR-13**: 导出按钮弹出ExportDialog，默认勾选当前AI消息+对应用户提问，支持多选，支持PDF/DOCX/Markdown
- **FR-14**: 点赞/点踩显示"感谢反馈"toast
- **FR-15**: 三点菜单包含"转为文档编辑"和"删除"
- **FR-16**: "转为文档编辑"发送内容到右侧Markdown编辑器
- **FR-17**: "删除"弹出确认框，确认后删除消息
- **FR-18**: 五大处方点击后立即显示固定欢迎语，不调用LLM
- **FR-19**: 文件上传最多支持10个文件
- **FR-20**: 医生模式显示用药审查和健康画像按钮，患者模式不显示
- **FR-21**: 所有医疗内容带免责声明
- **FR-22**: 普通聊天不自动播放TTS，只有CGA内自动播放题目语音
- **FR-23**: CGA音频文件不存在时静默不播放，不调用TTS
- **FR-24**: 访客模式→患者老年模式→聊天正常，切换医生模式不白屏

## Non-Functional Requirements
- **NFR-1**: npm run lint 0错误0警告
- **NFR-2**: npm run build成功
- **NFR-3**: ThinkingBlock spinner动画1.5秒一圈
- **NFR-4**: 输入区域加载动画三点脉冲1.2秒循环
- **NFR-5**: 停止按钮静态显示，无脉冲动画
- **NFR-6**: 流式输出实时渲染，无人工延迟

## Constraints
- **Technical**: Next.js 16, React 19, TypeScript, Zustand, shadcn/ui, Tailwind CSS
- **Business**: 禁止加载localKB模块，CGA使用预录音频路径`/audio/scales/${scaleId}_${questionId}.mp3`
- **Dependencies**: 现有CGAConversation组件

## Assumptions
- CGAConversation组件已实现多选、音频控制、完成页等核心逻辑，只需集成到ChatArea
- 预录音频文件可能不存在，播放器error事件已处理（静默失败）
- 现有ExportDialog、MessageBubble组件基本可用，可能需要小修复

## Acceptance Criteria

### AC-1: CGA多量表选择
- **Given**: 用户在访客/患者/医生模式
- **When**: 点击"老年综合评估CGA"按钮
- **Then**: 显示量表选择页，支持多选+全选按钮，已完成量表显示"已作答"badge且不可选
- **Verification**: `human-judgment`

### AC-2: CGA答题音频控制
- **Given**: 用户选择PHQ-9+GAD-7并开始作答
- **When**: 进入答题
- **Then**: 第一题自动播放音频（文件存在时），点击停止后后续题目不自动播放，点击播放恢复自动模式
- **Verification**: `human-judgment`

### AC-3: CGA选项不自动跳转
- **Given**: 用户在CGA答题中
- **When**: 点击选项
- **Then**: 选项高亮，不自动跳转下一题，需手动点"下一题"
- **Verification**: `human-judgment`

### AC-4: CGA完成页
- **Given**: 用户答完所选量表题目
- **When**: 最后一题点击提交
- **Then**: 显示"作答完毕"+已完成量表名+三个按钮：重新评估/继续作答其他量表/查看评估报告
- **Verification**: `human-judgment`

### AC-5: 搜索链接可跳转
- **Given**: AI回复触发联网搜索
- **When**: 点击搜索结果标题或"查看原文"
- **Then**: 在新标签页打开对应网页
- **Verification**: `human-judgment`

### AC-6: 消息操作按钮完整
- **Given**: AI有回复消息
- **When**: 查看消息底部
- **Then**: 显示赞/踩/复制/语音播放/导出/三点菜单按钮，最后一条消息额外显示重新生成
- **Verification**: `human-judgment`

### AC-7: 五大处方固定欢迎语
- **Given**: 用户点击"五大处方生成"
- **When**: 进入五大处方模式
- **Then**: 立即显示固定欢迎语，不调用LLM
- **Verification**: `programmatic`

### AC-8: 文件上传限制
- **Given**: constants.ts配置
- **When**: 检查maxFileCount
- **Then**: 值为10
- **Verification**: `programmatic`

### AC-9: Lint和Build通过
- **Given**: 所有修复完成
- **When**: 运行npm run lint和npm run build
- **Then**: lint 0错误0警告，build成功
- **Verification**: `programmatic`

### AC-10: 医生/患者模式切换
- **Given**: 用户在老年患者模式
- **When**: 打开用户菜单切换到医生模式
- **Then**: 不白屏不崩溃，聊天正常，医生模式显示用药审查和健康画像按钮
- **Verification**: `human-judgment`

## Open Questions
- 无
