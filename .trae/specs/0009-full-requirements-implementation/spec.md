# 0009 新任务全量需求实现 - Product Requirement Document

## Overview
- **Summary**: 严格按照新任务.md的14条需求，全面修复和完善GerClaw系统。包括：消息操作按钮完整功能（含三点菜单、导出对话框、删除对话框、转为文档编辑）、禁止自动播放TTS（仅CGA内自动播放）、加载动画区分（思考保留spinner、输出用三点）、搜索链接可跳转、CGA预录音频+多选量表+完成页三按钮+语音识别a/b/c/d+不自动跳题、五大处方MinerU文件解析+本地知识库检索+JSON结构化输出+右侧栏实时MD编辑、文件上传8个限制修复、赞/踩文字反馈等。
- **Purpose**: 上一轮0008实现严重偏离需求，存在自动播放TTS违规、按钮功能缺失、CGA完成页bug、五大处方核心功能未实现等问题。本轮必须严格按新任务.md逐条实现，不偷工减料，不做toy实现。
- **Target Users**: 老年患者、老年科医生、访客用户

## Goals
1. 消息操作按钮行对齐豆包：复制、语音播放（默认不自动播放）、分享（多格式+选范围对话框）、点赞（含文字反馈）、点踩（含文字反馈）、重新生成、三点菜单（转为文档编辑、删除），所有按钮真实可用
2. 严格禁止非CGA场景的TTS自动播放（包括老年模式普通聊天）；CGA内自动播放但记住用户开关偏好
3. 加载动画区分：思考中用spinner（速率适中），文字输出等待用三点跳动动画
4. 搜索结果链接真实可跳转
5. CGA全面重构：多量表勾选+全选、批量作答中途无切换、完成页三按钮（重新评估/继续作答/查看报告）、完成后右侧栏不自动弹出、预录音频文件（TTS生成缓存）、语音识别支持a/b/c/d、选完不自动跳题、退出进度保存、历史对话恢复报告
6. 五大处方全面实现：MinerU API文件解析、文件上传8个限制修复、文件内容传给模型上下文、本地知识库检索优先+联网搜索补充、InfoCollectionCard对话卡片每轮4题最多3轮、JSON结构化输出+Zod校验、健康画像→五大处方顺序、右侧栏实时编辑+实时渲染MD、PII脱敏
7. 所有导出按钮支持PDF/DOCX/Markdown三种格式
8. 核查并修正量表题目数量

## Non-Goals (Out of Scope)
- 不做二阶段AgentScope多智能体
- 不做账号系统/登录
- 不做Docker部署
- 不改变整体UI框架布局
- 预录音频不要求真人录音，使用TTS API批量生成后缓存到public/audio/目录

## Background & Context
- 上一轮0008存在的严重问题：
  1. 老年模式普通聊天自动播放TTS（用户明确禁止，用了6个感叹号）
  2. ThinkingBlock错误地改为三点动画（应保留spinner，仅输出等待用三点）
  3. ExportDialog和DeleteConfirmDialog被删除，分享按钮直接下载MD而非弹对话框
  4. 三点菜单、转为文档编辑、赞/踩文字反馈完全缺失
  5. CGA完成后右侧栏自动弹出的bug未修复
  6. CGA无多量表多选、完成页三按钮、语音a/b/c/d识别、不自动跳题
  7. 五大处方MinerU未调用、本地知识库未检索、JSON输出未实现、右侧栏实时渲染未做
  8. 文件上传8个限制bug未修复
- MinerU API已配置在.env中：NEXT_PUBLIC_MINERU_URL和NEXT_PUBLIC_MINERU_API_KEY
- 本地知识库位于/Users/qizs/conclusion/gerclaw/本地知识库/md/
- hzj_case.json提供输入模板字段参考
- 五大处方报告模板.md提供输出格式参考

## Functional Requirements

### FR-1: 消息操作按钮完整功能
- 每条AI回复下方按钮行包含：👍点赞、👎点踩、|分隔线、📋复制、🔄重新生成（仅最后一条AI消息）、🔊语音播放、↗️分享、⋯三点菜单
- 三点菜单展开小菜单，包含：📝转为文档编辑、🗑️删除
- 复制按钮：点击后将AI回复纯文本复制到剪贴板，按钮变为✓checkmark 2秒后恢复
- 语音播放按钮：点击播放TTS，再次点击暂停；默认**不自动播放**（任何模式下普通聊天都不自动播放）；播放时按钮显示Volume2，暂停时显示VolumeX
- 分享按钮：弹出ExportDialog对话框，默认勾选当前问答对（用户消息+AI回复），用户可勾选/取消其他消息，支持PNG/PDF/DOCX/MD四种格式选择
- 点赞/点踩按钮：互斥状态，点击后弹出反馈输入框（可输入文字评价也可直接提交），提交后按钮变为filled图标+toast提示
- 重新生成按钮：仅在最后一条AI消息上显示，点击后删除该AI消息并重新请求生成
- 删除按钮（三点菜单内）：弹出DeleteConfirmDialog，默认勾选当前问答对，用户可勾选/取消其他消息，有"取消"和"确认删除"按钮
- 转为文档编辑按钮（三点菜单内）：将该AI回复内容渲染到右侧栏，右侧栏提供实时MD编辑+实时预览，右上角有复制按钮和导出按钮（PDF/DOCX/MD）

### FR-2: TTS自动播放严格控制
- **所有聊天回复（包括老年模式）默认不自动播放TTS**，用户必须手动点击播放按钮
- 仅CGA老年综合评估内才允许自动播放（且需记住用户开关偏好）
- 移除ChatArea.tsx中所有autoReadIfSeniorMode相关逻辑

### FR-3: 加载动画区分
- 模型思考中（ThinkingBlock）：使用转圈spinner动画（Loader2 animate-spin），旋转速率适中（animation-duration: 1.5s，不要过快）
- 文字输出等待（StreamingText空内容时）：使用三点跳动动画（...），三个点跳动速率适中
- 思考中的spinner在有思考内容后折叠显示"已思考"，不再转圈

### FR-4: 搜索结果链接可跳转
- ToolCallBlock搜索结果展开列表中，每条结果标题是可点击链接
- 链接必须使用`<a target="_blank" rel="noopener noreferrer">`，点击后在新标签页打开对应网页
- 实际浏览器测试验证可跳转

### FR-5: CGA全面重构

#### FR-5.1: 预录音频文件
- 系统启动时/构建时检查public/audio/cga/目录下是否有音频文件
- 如果音频文件不存在，使用TTS API为每个量表的题目+选项生成mp3音频文件，缓存到public/audio/cga/目录
- 文件命名：`{scaleId}_q{questionIndex}.mp3`（例如phq9_q0.mp3为PHQ-9第1题音频，包含题目+所有选项朗读）
- 用户点击播放按钮时直接播放预录音频文件，不再实时调用TTS
- CGA内默认自动播放（CGA场景是唯一允许自动播放的地方）
- 播放按钮显示正常（播放中显示Volume2/暂停中显示VolumeX）
- 用户关闭/打开播放后，在后续题目中维持用户选择（全局CGA音频开关状态持久化）
- 用户切换题目时：若未关闭播放则自动播放新题音频；若已关闭则不播放
- 用户返回到量表选择界面时停止播放

#### FR-5.2: 语音识别增强
- 语音答题除了识别选项文本和数字（1-9），还要识别a/b/c/d选项（包括中文"选项a"、"a"、"诶"等同音变体）
- 识别成功并选中选项后，**不自动进入下一题**，让用户确认，用户手动点击"下一题"按钮
- 自动跳转下一题的逻辑全部移除

#### FR-5.3: 多量表选择与批量作答
- 量表选择界面提供"全选"按钮，点击全选所有量表
- 用户可勾选一个或多个量表
- 点击"开始作答"后，系统按量表顺序串联所有题目，一次性做完所有选中量表的所有题目，中途无量表切换界面
- 作答过程中进度条显示总进度（例如"第3/25题"）

#### FR-5.4: CGA完成页（修复右侧栏自动弹出bug）
- 完成量表评估后，**右侧栏不自动弹出**
- 中间聊天栏显示"作答完毕"标题+"xxx量表已作答完成"（多个量表用顿号分隔）
- 一行并列三个按钮：
  1. **重新评估**：清空当前作答，重新开始
  2. **继续作答其他量表**：返回量表选择界面，已作答题量显示"已作答"且disabled不可勾选
  3. **查看已作答量表评估报告**：将所有已作答题量结果汇总，调用LLM生成评估报告，在右侧栏显示

#### FR-5.5: 退出与进度保存
- 只要用户不选择退出CGA，保持所有作答进度（localStorage持久化）
- 生成评估报告时，将该用户历史所有作答结果+当前结果一起传给LLM生成综合报告
- 用户选择退出时：
  - 若无作答完毕/无报告生成：弹出确认"退出后当前进度将不会保存，确认退出吗？"，确认后不保存
  - 若已有评估报告生成：弹出确认"您已完成量表评估，是否要退出？"，确认后保存最近一次报告
- 在历史对话中进入之前评估的对话时，显示上一次评估报告，用户可选择继续作答/重新作答/查阅报告

#### FR-5.6: 全量表完成状态
- 所有量表都作答完毕后，量表选择界面显示"所有量表已作答完毕"提示
- 无法再勾选任何量表，显示"生成评估报告"按钮
- 点击生成按钮汇总所有结果生成综合报告，在右侧栏显示（可编辑+导出）

#### FR-5.7: 量表题目数量核查
- 核查PHQ-9（9题）、GAD-7（7题）、PSQI（18题但分7成分）、Mini-Cog（3题）、MMSE（30题）的题目数量
- 修正scales.ts中不正确的questionCount和questions数组长度

### FR-6: 五大处方全面实现

#### FR-6.1: 固定欢迎语（不调用LLM）
- 点击五大处方按钮后，直接显示固定欢迎语文本（已在0008实现getOpeningMessage），不调用LLM流式生成

#### FR-6.2: MinerU API文件解析
- 用户上传文件（支持图片、PDF、Markdown、DOCX）后，调用MinerU API解析文件内容
- 创建API route: `apps/mvp/src/app/api/mineru/parse/route.ts`
- 修复文件上传8个限制bug（当前实际只能加载5个）：检查FileUpload组件，确保最多支持8个文件
- 解析后的文件内容整合到用户信息中，作为上下文传给LLM
- 允许用户只传语音/文本不传文件

#### FR-6.3: 信息收集对话卡片（InfoCollectionCard增强）
- 参照hzj_case.json的字段判断缺失信息
- 缺失字段通过对话卡片形式让用户作答，参照Trae Work对话卡片样式
- 每轮卡片最多4道问题（而不是所有字段一次性问完）
- 用户回答后（文本或语音），系统整合信息，如果仍有缺失字段则发起下一轮卡片
- 对话次数上限3轮，超过后用已有信息生成
- 对话卡片支持文本输入和语音输入（麦克风按钮）

#### FR-6.4: 本地知识库检索
- 扫描本地知识库目录（/Users/qizs/conclusion/gerclaw/本地知识库/md/）下的md文件
- 注意：本地知识库不在gerclaw-main目录内，需要通过配置或相对路径访问
- 由于是客户端项目，本地知识库md文件应在构建时或服务端API route中读取
- 根据用户健康问题关键词匹配相关文档片段
- 本地知识库检索优先于联网搜索
- 本地知识库找不到所需信息时才进行联网搜索补充
- 创建API route: `apps/mvp/src/app/api/knowledge/search/route.ts`

#### FR-6.5: 生成顺序：健康画像→五大处方
- 先整合所有收集到的信息生成用户健康画像
- 再基于健康画像生成五大处方（药物、运动、营养、心理、康复）
- 确保处方之间彼此不冲突、有临床可行性、内容安全无害
- 做好用药审查（药物相互作用检查）

#### FR-6.6: JSON结构化输出+校验
- 参照五大处方报告模板.md，定义五大处方JSON Schema（Zod）
- LLM输出JSON格式结果
- 系统使用Zod校验JSON格式
- 校验通过后将JSON字段整合为Markdown格式
- Markdown结果在右侧栏显示

#### FR-6.7: 右侧栏实时编辑+实时渲染
- 右侧栏内容区改造为左右分栏（或上下分栏切换）：
  - 左侧/上方：Markdown源码编辑器（textarea或contentEditable）
  - 右侧/下方：Markdown实时渲染预览（MarkdownRenderer组件）
- 用户编辑左侧源码时，右侧实时渲染预览
- 工具栏包含：复制按钮（复制渲染后的HTML/纯文本到剪贴板）、导出按钮（PDF/DOCX/MD三种格式）
- 适用于五大处方报告、CGA评估报告、用药审查报告、"转为文档编辑"的单条AI回复

#### FR-6.8: PII隐私脱敏
- 在将用户信息传给LLM前，对姓名、身份证号、医保号、住院号、电话号码进行正则脱敏
- UI显示原文不脱敏（已在0008实现desensitizeForLLM，需确保五大处方流程中调用）

### FR-7: 导出功能统一
- 所有导出按钮（右侧栏导出、分享对话框导出、报告导出）一律支持PDF、DOCX、Markdown三种格式
- PNG作为图片导出格式可选（分享对话框保留PNG/JPG选项）

## Non-Functional Requirements
- **NFR-1**: 所有按钮真实可用，不可出现点击无反应或仅摆设的情况
- **NFR-2**: lint 0错误，build成功
- **NFR-3**: 预录音频文件总大小控制在合理范围（每道题5-15秒mp3，预计5个量表约70题，总大小<20MB）
- **NFR-4**: 右侧栏实时编辑渲染延迟<100ms
- **NFR-5**: MinerU API调用有loading状态和错误处理
- **NFR-6**: 医疗安全底线：所有医疗输出带免责声明，高风险症状提示立即就医
- **NFR-7**: Agent必须自行使用浏览器工具逐条对照新任务.md的14条要求验证，发现不符合立即修复，直到全部通过才能提交

## Constraints
- **Technical**: Next.js 16 + React + TypeScript + Tailwind CSS + shadcn/ui；前端运行时无法直接读取本地文件系统目录（本地知识库需通过API route或构建时复制到public目录）
- **Business**: 无后端服务器，所有API调用走Next.js API routes或直接调用外部API
- **Dependencies**: MinerU API（已配置）、TTS API（Mimo，已有）、ASR API（已有）、LLM API（已有）、html2canvas/jsPDF/docx/file-saver（已有）

## Assumptions
- 本地知识库md文件可以在构建时复制到apps/mvp/public/knowledge/目录下供前端检索，或者创建API route在服务端读取
- TTS API支持批量生成音频文件并保存
- 用户提供的.env中MinerU API Key有效
- 量表题数以标准量表为准：PHQ-9=9题、GAD-7=7题、PSQI=7成分（约18子题但计分按7成分）、Mini-Cog=3题、MMSE=30题

## Acceptance Criteria

### AC-1: 消息操作按钮完整可用
- **Given**: 用户在任何模式下（访客/患者/医生）与AI对话完成
- **When**: 用户查看AI回复
- **Then**: 每条AI回复下方显示完整按钮行（赞/踩/复制/重新生成/播放/分享/三点菜单），三点菜单内含转为文档编辑和删除，所有按钮点击有真实功能
- **Verification**: `human-judgment`
- **Notes**: 需浏览器测试每个按钮

### AC-2: 默认不自动播放TTS
- **Given**: 用户在普通聊天界面（包括老年模式）
- **When**: AI回复完成
- **Then**: 不自动播放TTS语音；仅CGA评估内自动播放
- **Verification**: `human-judgment` + `programmatic`（代码检查无autoRead逻辑）

### AC-3: 加载动画正确区分
- **Given**: AI正在响应
- **When**: 模型思考阶段显示spinner，文字输出等待阶段显示三点跳动
- **Then**: 两种动画不混淆，spinner速率适中不刺眼
- **Verification**: `human-judgment`

### AC-4: 搜索链接可跳转
- **Given**: AI回复触发联网搜索
- **When**: 搜索结果展开后，用户点击任一结果标题
- **Then**: 在新标签页打开对应网页URL
- **Verification**: `programmatic`（a标签target=_blank）+ `human-judgment`（浏览器实际点击测试）

### AC-5: CGA多选+批量作答+完成页
- **Given**: 用户进入CGA评估
- **When**: 选择多个量表开始作答
- **Then**: 一次性做完所有题目（中途无切换），完成后中间栏显示三按钮，右侧栏不自动弹出
- **Verification**: `human-judgment`

### AC-6: CGA预录音频+开关记忆
- **Given**: 用户在CGA评估中
- **When**: 进入新题目
- **Then**: 若音频开启则自动播放预录音频；关闭后后续题目不播放；返回量表选择页停止播放
- **Verification**: `human-judgment`

### AC-7: CGA语音不自动跳题
- **Given**: 用户在CGA答题页通过语音选择选项
- **When**: 语音识别成功并选中选项
- **Then**: 不自动跳到下一题，用户需手动点击"下一题"
- **Verification**: `programmatic` + `human-judgment`

### AC-8: 五大处方MinerU解析+文件上下文
- **Given**: 用户在五大处方功能中上传文件
- **When**: 文件上传完成
- **Then**: 调用MinerU API解析，解析内容作为上下文传给LLM；文件上传支持8个
- **Verification**: `human-judgment` + `programmatic`

### AC-9: 五大处方信息收集卡片
- **Given**: 用户在五大处方流程中信息不全
- **When**: 系统检测到缺失字段
- **Then**: 弹出对话卡片（每轮最多4题），支持文本/语音回答，最多3轮
- **Verification**: `human-judgment`

### AC-10: 五大处方JSON输出+右侧栏渲染
- **Given**: 五大处方生成完成
- **When**: 输出结果
- **Then**: JSON通过Zod校验，转为Markdown在右侧栏显示，支持实时编辑+实时渲染预览
- **Verification**: `programmatic`（Zod校验）+ `human-judgment`

### AC-11: 本地知识库检索
- **Given**: 用户在五大处方流程中
- **When**: 需要检索医学信息
- **Then**: 优先检索本地知识库md文件，找不到再联网搜索
- **Verification**: `programmatic` + `human-judgment`

### AC-12: 右侧栏实时编辑渲染
- **Given**: 右侧栏显示可编辑文档（处方/报告/转为文档编辑）
- **When**: 用户在编辑区输入Markdown
- **Then**: 预览区实时渲染Markdown，延迟<100ms；工具栏有复制+导出（PDF/DOCX/MD）
- **Verification**: `human-judgment`

### AC-13: 量表题数正确
- **Given**: -
- **When**: 核查scales.ts
- **Then**: PHQ-9=9题、GAD-7=7题、Mini-Cog=3题、MMSE=30题
- **Verification**: `programmatic`

### AC-14: Lint+Build通过
- **Given**: 所有代码修改完成
- **When**: 运行npm run lint和npm run build
- **Then**: lint 0错误，build成功
- **Verification**: `programmatic`

## Open Questions
- [ ] PSQI量表的题目数量：PSQI官方是18个自评条目但组成7个成分，当前scales.ts中如何实现的需要核查
- [ ] 本地知识库目录不在gerclaw-main内，需要决定是构建时复制到public还是通过API route服务端读取
- [ ] 预录音频文件是首次运行时动态生成并缓存，还是构建时预先生成
