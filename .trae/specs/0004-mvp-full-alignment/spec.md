# 0004-MVP全量功能对齐与上线 — Product Requirement Document

## Overview
- **Summary**: 在0001-0003已完成的UI壳子、真实API接入、Markdown导出、图片多模态基础上，修复核心架构问题（真流式输出替代伪造打字机）、补齐智能体执行过程七项可视化、实现五大处方/CGA语音交互（语音读题+语音答题全语音流程）、统一提示语为"GerClaw医学诊疗智能体"、补齐可靠性容错机制、完成UI细节对齐，通过全量测试验证，达到功能完整对齐的MVP标准。
- **Purpose**: 当前MVP存在几个致命缺陷：1)流式输出是等完整结果后setInterval逐字伪造，体验差；2)工具调用/思维链可视化完全缺失，不符合"工具调用透明可见"原则；3)五大处方/CGA没有语音交互，不适老；4)提示语自称"小Ger"不统一；5)可靠性机制不完整。本任务修复所有问题，全量对齐gerclaw设计要求.md，达到可演示可验证的MVP标准。
- **Target Users**: 老年患者、老年科医生、产品演示用户

## Goals
- 修复流式输出为真正的SSE delta逐块渲染（移除伪造的setInterval打字机）
- 实现完整的智能体执行过程七项可视化（思维链/工具调用/搜索结果/文档状态/流式文本为MVP重点；子智能体/决策时间线为MVP适配版）
- 实现CGA评估全语音交互：题目TTS语音朗读、语音ASR答题、切换题目自动朗读
- 实现五大处方语音引导：开场/追问自动TTS朗读，支持全语音交流
- 统一所有智能体提示语为"GerClaw医学诊疗智能体"，移除"小Ger"自称
- 补齐可靠性容错：React Error Boundary、网络断开检测、localStorage写满提示、主备降级用户提示、思考过程自动收起
- 补齐UI交互细节：引用角标[1][2]可点击、工具调用失败重试、右侧面板可拖拽调整宽度、欢迎页快捷入口
- 检查更新环境变量配置
- 通过全量lint+build测试
- 完成本地全量功能验证，所有核心流程可用

## Non-Goals (Out of Scope)
- PDF/DOCX导出（Markdown导出足够MVP）
- MinerU真实PDF/DOCX文档解析（入口已有，二阶段接入）
- 后端FastAPI + AgentScope架构（二阶段任务）
- 账号系统/健康画像持久化（访客模式localStorage足够MVP）
- 真实DDI/Beers规则引擎（LLM辅助+明确仅供参考标注足够MVP）
- AnySearch接入（Tavily足够MVP）
- 技能管理真实上传执行（UI已有，二阶段）
- Playwright E2E自动化测试（手动测试足够MVP）

## Background & Context
- 0001完成了完整前端UI壳子和三栏布局
- 0002完成了真实LLM/ASR/TTS/搜索API接入和localStorage持久化
- 0003完成了Markdown导出和图片多模态，但遗留部署任务
- 用户测试发现核心问题：流式输出是伪造的、工具可视化全无、语音交互缺失、提示语不统一
- 当前代码lint和build可通过，但核心体验不符合设计要求

## Functional Requirements
- **FR-1: 真流式输出修复**
  - 移除StreamingText组件中的setInterval伪造逐字逻辑
  - 修改流式处理：每收到SSE delta立即渲染，不等待fullText完整
  - 首token到达前显示Loader2旋转圆圈
  - 流式过程中显示光标闪烁，停止/重新生成可用
  - SSE连接中断保留已接收内容，提供重试按钮
  
- **FR-2: 思维链可视化（ThinkingBlock）**
  - 支持reasoning_content/thinking字段接收
  - 默认折叠，显示"思考中..."旋转动画
  - 点击展开查看完整思考过程
  - 思考完成后自动收起区块（可手动展开）
  - 低对比度浅灰背景，视觉层级低于正文
  
- **FR-3: 工具调用可视化（ToolCallBlock适配版）**
  - MVP阶段工具为：联网搜索、图片理解
  - 独立卡片组件：工具图标+名称+状态徽章
  - 状态：运行中（旋转Loader2）→ 完成（绿色✓）→ 失败（红色✗）
  - 默认折叠，点击展开显示输入参数+执行结果+耗时
  - 失败状态提供"重试"按钮
  - 搜索工具卡片与SearchResultCard联动
  
- **FR-4: 搜索结果可视化完善**
  - 已有search_results block保留
  - AI正文引用[1][2]显示为蓝色上角标
  - 点击角标在右侧面板展开引用详情
  - 搜索结果卡片与ToolCallBlock状态联动
  
- **FR-5: 文档解析状态可视化**
  - 文件标签显示状态：上传中→解析中→完成/失败（图片多模态已实现）
  - 配套DocumentToolCard显示解析进度
  - 非图片文件（PDF/DOCX）显示"待MinerU接入"提示
  
- **FR-6: CGA全语音交互**
  - 进入答题时自动TTS朗读当前题目
  - 每题选项旁有"朗读题目"按钮
  - 支持语音答题：点击麦克风说话，ASR识别后自动匹配选项或允许手动选择
  - 切换上一题/下一题时自动朗读新题目
  - 老年模式下语音按钮更大更明显
  - 完成评估时TTS提示结果已生成
  
- **FR-7: 五大处方语音引导**
  - 开场消息自动TTS朗读（老年模式下默认开启）
  - AI追问自动TTS朗读
  - 支持语音回答，全语音流程可用
  - 提供"朗读回复"按钮（已有VoiceReadButton，需确保在处方流程中可用）
  
- **FR-8: 提示语统一**
  - 所有system prompt中智能体名称统一为"GerClaw医学诊疗智能体"
  - 移除"小Ger"等不统一自称
  - 患者端：亲切、温柔、易懂，像家人关心老人
  - 医生端：专业、简洁、循证，使用医学术语
  - 所有提示语明确医疗安全底线和免责声明
  
- **FR-9: 可靠性容错机制**
  - React Error Boundary捕获组件错误，显示友好错误页+重试按钮，不白屏
  - 网络断开检测：navigator.onLine+实际fetch测试，显示离线横幅，禁用发送
  - localStorage写满检测：try-catch写入失败时提示用户导出后清除历史
  - 主备模型切换：控制台日志记录，切换不打断对话，所有模型失败显示友好错误
  - API降级提示：ASR/TTS不可用时按钮禁用+hover提示原因
  - 流式中断处理：保留已接收内容，显示"回复中断，点击重试继续"
  
- **FR-10: UI交互细节对齐**
  - 右侧面板宽度可拖拽调整（320-500px，默认400px）
  - 引用角标[1][2]点击在右侧面板显示引用详情
  - 消息操作按钮（复制/重新生成/朗读/导出）悬停显示完整
  - 欢迎页功能快捷入口卡片完整可点击
  - 左侧边栏：系统标识+折叠按钮+新建对话（蓝色主按钮）+搜索+技能入口布局对齐设计
  - 思考区块思考完成自动收起
  - 工具调用失败显示重试按钮
  - 免责声明在所有医疗输出场景可见（消息底部+输入框底部）
  
- **FR-11: 环境变量检查与更新**
  - 核对.env.example完整性，补全缺失配置项
  - 验证当前.env.local配置有效性
  - 主备模型配置可正常切换
  - ASR/TTS/搜索配置检查

## Non-Functional Requirements
- **NFR-1: 性能**：首屏加载<3s，首token响应<5s（网络正常情况下），流式输出逐字显示无卡顿
- **NFR-2: 适老化**：老年模式正文≥18px、按钮≥48px、高对比度≥7:1（AAA）、二次确认、语音优先
- **NFR-3: 医疗安全**：无确定性诊断、所有医疗输出带免责声明、高风险症状红色紧急提示、自杀风险危机热线
- **NFR-4: 可靠性**：lint 0错误0警告、build成功、单服务故障不整体崩溃、错误提示用户友好无技术术语
- **NFR-5: 可访问性**：语义化HTML、键盘可导航、ARIA标签、屏幕阅读器支持

## Constraints
- **Technical**: Next.js 16 App Router静态导出、纯前端无Python后端、浏览器原生API优先（MediaRecorder/Web Audio/fetch）、现有技术栈（Zustand/Tailwind/shadcn/Lucide）、不引入不必要的新npm依赖
- **Business**: MVP定位可演示可体验、访客模式无需登录、快速上线收集反馈
- **Dependencies**: Mimo ASR/TTS服务可用、LLM API（主备）可用、Tavily搜索可用、IGA Pages部署平台

## Assumptions
- 现有LLM API支持stream=true和reasoning_content（或thinking）字段
- Mimo ASR/TTS CORS在浏览器端可正常调用；若CORS失败需要在API route中做代理转发
- IGA Pages支持静态站点部署和环境变量注入
- 现有localStorage持久化可正常工作，用户数据不丢失
- 七项可视化中，子智能体树（SubAgentTree）和决策时间线（DecisionTimeline）在MVP纯前端阶段做适配简化：SubAgentTree仅显示单智能体状态，DecisionTimeline简化为步骤指示器（思考→搜索→回答）

## Acceptance Criteria

### AC-1: 真流式输出
- **Given**: 用户发送一条文本消息
- **When**: LLM API开始返回SSE流
- **Then**: 每收到delta立即渲染到页面，首token到达前显示旋转Loader，过程中显示闪烁光标，不等待完整结果再逐字伪造
- **Verification**: `programmatic` + `human-judgment`
- **Notes**: 移除StreamingText中的setInterval逻辑，直接实时渲染content

### AC-2: 思维链可视化
- **Given**: 模型返回reasoning_content
- **When**: 思考过程进行中
- **Then**: 显示"思考中..."可折叠区块，旋转动画；思考完成自动收起；点击展开查看完整内容
- **Verification**: `human-judgment`

### AC-3: 工具调用卡片
- **Given**: 触发联网搜索
- **When**: 搜索进行中
- **Then**: 显示ToolCallCard（运行中旋转→完成✓→失败✗），点击展开查看参数和结果，失败可重试
- **Verification**: `human-judgment`

### AC-4: CGA全语音交互
- **Given**: 患者端进入CGA答题
- **When**: 切换到新题目
- **Then**: 自动TTS朗读题目和选项，支持语音答题（麦克风说话识别选项），朗读按钮可点击重复朗读
- **Verification**: `human-judgment`
- **Notes**: 老年模式默认开启自动朗读

### AC-5: 提示语统一
- **Given**: 任何AI回复
- **When**: 查看AI自称
- **Then**: 统一为"GerClaw医学诊疗智能体"相关表述，无"小Ger"等不一致自称
- **Verification**: `programmatic` (grep检查system prompt) + `human-judgment`

### AC-6: 容错机制生效
- **Given**: 网络断开/API失败/localStorage满
- **When**: 异常发生
- **Then**: 显示用户友好的错误提示，提供重试按钮，不白屏不崩溃，不显示技术错误栈
- **Verification**: `human-judgment`

### AC-7: 构建质量
- **Given**: 完成所有代码修改
- **When**: 运行npm run lint和npm run build
- **Then**: lint 0错误0警告，build成功，静态页面完整生成
- **Verification**: `programmatic`

### AC-8: 本地全量功能验证
- **Given**: 启动npm run dev本地服务
- **When**: 走通所有核心流程
- **Then**: 页面可正常加载，核心流程（文本对话/语音对话/CGA评估/五大处方生成/导出Markdown）可完整走通
- **Verification**: `human-judgment`

### AC-9: 适老化合规
- **Given**: 开启老年模式（患者端默认开启）
- **When**: 浏览任意界面
- **Then**: 正文≥18px、按钮≥48px、高对比度、二次确认对话框、语音按钮明显
- **Verification**: `human-judgment`

### AC-10: 医疗安全合规
- **Given**: 任意AI医疗输出
- **When**: 查看消息内容
- **Then**: 无确定性诊断用语、消息底部可见免责声明、高风险症状红色紧急提示
- **Verification**: `human-judgment`

## Open Questions
- [ ] Mimo ASR/TTS在生产环境是否存在CORS问题？若有需要在Next.js API route中做代理转发（当前API route已有但ASR/TTS是否走代理？）
- [ ] 主模型当前配置是否支持reasoning_content/thinking字段？不支持的话思维链区块显示为简化版"思考中..."状态即可
- [ ] 右侧面板拖拽调整宽度是否需要持久化到localStorage？
