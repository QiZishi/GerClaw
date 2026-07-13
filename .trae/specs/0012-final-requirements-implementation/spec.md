# 0012 最终需求完整实现 - Product Requirement Document

## Overview
- **Summary**: 严格按照新任务.md逐条实现所有剩余40项要求，包括P0紧急Bug修复、功能优化、CGA评估完善、五大处方流程、文件上传和导出统一。
- **Purpose**: 解决当前P0阻塞性问题（角色切换失败、流式输出中断、CGA语音逻辑错误），完善所有功能点，确保lint和build通过。
- **Target Users**: 老年患者、老年科医生、访客用户

## Goals
- 修复P0-1: 医生端/患者端切换失败问题，确保三端切换正常
- 修复P0-2: 流式输出/思考状态/中断恢复问题，包括动画优化
- 修复P0-3: CGA语音预录音频+播放状态机完整实现
- 完善功能优化1: 消息操作按钮完整功能
- 完善功能优化3: 联网搜索链接可跳转
- 完善功能优化6/7: CGA完成页+量表多选界面
- 完成功能优化8: 量表题数核查（已确认PHQ-9=9/GAD-7=7/PSQI=7/MMSE=30）
- 完善功能优化10: 五大处方生成流程
- 完善功能优化11/12: 文件上传10个+导出功能统一
- 其他修复：移除自动TTS、hydration mismatch、lint0错误0警告

## Non-Goals (Out of Scope)
- 不加载本地知识库436个文件（保持/api/knowledge/retrieve返回503维护中）
- 不添加用户未要求的额外功能
- 不修改医疗安全底线规则（免责声明、高风险提示）
- CGA音频无预录文件时不报错也不回退TTS，静默处理

## Background & Context
- 技术栈: React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui + Zustand
- 当前状态: P0聊天功能已恢复（API不崩溃），但存在角色切换白屏、流式中断、CGA语音仍用TTS等问题
- 约束: 适老化规范（≥18px字体、≥48px按钮、高对比度）、医疗安全底线

## Functional Requirements

### P0-1: 医生端/患者端切换失败
- **FR-1**: 访客→老年朋友→医生三端可正常切换，切换后状态重置正确
- **FR-2**: 医生端页面正常加载，无白屏
- **FR-3**: 用药审查和健康画像按钮仅医生模式可见

### P0-2: 流式输出/思考状态/中断恢复
- **FR-4**: ThinkingBlock点击只折叠/展开，不中断对话
- **FR-5**: 停止按钮中断后不留持久错误状态，下次发送正常工作
- **FR-6**: SSE流式处理：thinking delta正确渲染，text delta正确渲染
- **FR-7**: ThinkingBlock spinner转速1.5秒一圈
- **FR-8**: 输入区域加载动画用三点脉冲（1.2秒循环）

### P0-3: CGA语音预录音频+播放状态机
- **FR-9**: CGA评估禁止调用TTS，必须用预录音频 `/audio/scales/${scaleId}_${questionId}.mp3`
- **FR-10**: 播放状态机：进入默认自动播放→点停止切手动→后续不自动播放→点播放恢复自动
- **FR-11**: 返回量表选择页时停止所有音频
- **FR-12**: CGA语音识别支持a/b/c/d、选项a/第1个/数字1-4、选项文本；识别后高亮但不自动跳转
- **FR-13**: 预录音频不存在时静默处理，不报错不调用TTS

### 功能优化1: 消息操作按钮
- **FR-14**: 复制按钮：点击复制AI文本，toast"已复制"2秒
- **FR-15**: 语音播放：默认不播放；点击播放/停止切换图标
- **FR-16**: 导出按钮：弹出ExportDialog，默认勾选当前AI+对应提问，支持多选；格式PDF/DOCX/Markdown（PNG/JPG保留）
- **FR-17**: 点赞/点踩：toast"感谢反馈"即可，无需输入框
- **FR-18**: 重新生成：只在最后一条AI消息显示
- **FR-19**: 三点菜单：转为文档编辑+删除
- **FR-20**: 转为文档编辑：发送到右侧栏Markdown编辑器
- **FR-21**: 删除：确认框确认后删除

### 功能优化3: 联网搜索链接可跳转
- **FR-22**: ToolCallBlock搜索结果标题是<a>标签，target="_blank" rel="noopener noreferrer"
- **FR-23**: SourceReferences"查看原文"可打开链接

### 功能优化6/7: CGA完成页+量表选择
- **FR-24**: 完成页显示"作答完毕"+已完成量表名（逗号分隔）
- **FR-25**: 三个按钮：重新评估、继续作答其他量表、查看评估报告
- **FR-26**: 查看评估报告才打开右侧栏，不自动弹出
- **FR-27**: 继续作答返回选择页，已完成量表显示"已作答"badge且disabled
- **FR-28**: 量表选择支持多选，有全选按钮
- **FR-29**: 选中后所有题目按顺序合并一次性作答
- **FR-30**: 所有量表完成显示"所有量表已作答完毕"+生成报告按钮
- **FR-31**: localStorage保存作答进度

### 功能优化10: 五大处方
- **FR-32**: 点击五大处方立即显示固定欢迎语，不调用LLM
- **FR-33**: 用户输入后调用LLM收集信息，InfoCollectionCard显示字段（年龄/性别/慢病/用药/吸烟/饮酒/运动/饮食/睡眠/情绪）
- **FR-34**: PII脱敏：姓名→[姓名]、身份证→[身份证]、医保→[医保]、手机→[手机]、地址→[地址]
- **FR-35**: 信息收集完成（或最多5轮）生成五大处方
- **FR-36**: 处方生成后在对话显示，右侧栏Markdown编辑器打开完整报告
- **FR-37**: 所有医疗内容带免责声明，高风险提示就医
- **FR-38**: 本地知识库返回503维护中，不加载436个文件

### 功能优化11/12: 文件上传+导出统一
- **FR-39**: 支持同时上传最多10个文件
- **FR-40**: MinerU API解析，未配置显示友好提示不崩溃
- **FR-41**: 所有导出按钮统一支持PDF/DOCX/Markdown
- **FR-42**: 消息导出、编辑器导出、报告导出、处方导出统一逻辑

### 其他
- **FR-43**: 彻底移除普通聊天（含老年模式）自动TTS，只有CGA内自动播放
- **FR-44**: 修复hydration mismatch，mounted=false时服务端客户端一致
- **FR-45**: npm run lint 0错误0警告

## Non-Functional Requirements
- **NFR-1**: 适老化: 老年模式≥18px正文、≥48px按钮、高对比度
- **NFR-2**: 医疗安全: 所有医疗输出带免责声明，高风险提示立即就医
- **NFR-3**: 性能: 流式输出实时渲染，无人工延迟
- **NFR-4**: 代码质量: lint 0错误0警告，TypeScript类型检查通过

## Constraints
- **Technical**: React 18 + TypeScript + Vite + Tailwind + shadcn/ui + Zustand
- **Business**: 访客模式所有功能可用无需登录
- **Dependencies**: MinerU API（可选）、LLM API、ASR API；预录音频文件可能不存在

## Assumptions
- CGA预录音频文件可能暂不存在，需静默处理
- MinerU API可能未配置，需降级方案
- 本地知识库暂不可用，返回维护中
- 量表题数已正确（PHQ-9=9, GAD-7=7, PSQI=7, MMSE=30）

## Acceptance Criteria

### AC-1: 角色切换正常
- **Given**: 用户在任意角色模式
- **When**: 切换角色（访客/患者/医生）
- **Then**: 页面正常加载无白屏，状态正确重置，医生模式显示用药审查和健康画像按钮
- **Verification**: `human-judgment`

### AC-2: 流式输出和中断恢复正常
- **Given**: 用户发送消息
- **When**: 模型生成回复
- **Then**: thinking内容正确显示，text内容正确流式渲染；点击ThinkingBlock只折叠不中断；点击停止后下次可正常发送
- **Verification**: `human-judgment`

### AC-3: 动画效果正确
- **Given**: 模型思考/加载中
- **When**: 显示动画
- **Then**: ThinkingBlock spinner 1.5s一圈；输入区域三点脉冲1.2s循环；停止按钮无闪烁
- **Verification**: `human-judgment`

### AC-4: CGA语音逻辑正确
- **Given**: 用户进入CGA评估
- **When**: 答题/点击播放停止
- **Then**: 使用预录音频无TTS调用；播放状态记忆；返回时停止音频；音频不存在静默处理；语音识别选中选项但不自动跳转
- **Verification**: `human-judgment` + `programmatic`

### AC-5: 消息操作按钮完整
- **Given**: 有AI回复消息
- **When**: 点击各操作按钮
- **Then**: 复制/播放/导出/点赞点踩/重新生成/三点菜单（转为文档+删除）功能正常
- **Verification**: `human-judgment`

### AC-6: 搜索链接可跳转
- **Given**: 有联网搜索结果
- **When**: 点击标题或查看原文
- **Then**: 新标签页打开对应网页
- **Verification**: `human-judgment`

### AC-7: CGA完成页和量表多选
- **Given**: CGA量表作答
- **When**: 完成/选择量表
- **Then**: 完成页显示三按钮不自动弹右侧栏；可多选量表一次性作答；已完成量表标记禁用；localStorage保存进度
- **Verification**: `human-judgment`

### AC-8: 五大处方流程
- **Given**: 点击五大处方按钮
- **When**: 输入信息生成处方
- **Then**: 立即显示欢迎语；InfoCollectionCard显示收集字段；PII脱敏；5轮内生成；右侧栏显示可编辑导出的报告
- **Verification**: `human-judgment`

### AC-9: 文件上传和导出
- **Given**: 上传文件/点击导出
- **When**: 操作文件上传/导出
- **Then**: 最多10个文件；MinerU解析或友好提示；所有导出支持PDF/DOCX/Markdown
- **Verification**: `human-judgment` + `programmatic`

### AC-10: 无自动TTS和hydration正确
- **Given**: 普通聊天（含老年模式）
- **When**: AI回复完成
- **Then**: 不自动播放TTS；hydration无mismatch
- **Verification**: `human-judgment` + `programmatic`

### AC-11: Lint和Build通过
- **Given**: 代码修改完成
- **When**: 运行npm run lint和npm run build
- **Then**: lint 0错误0警告，build成功TypeScript通过
- **Verification**: `programmatic`

## Open Questions
- 无
