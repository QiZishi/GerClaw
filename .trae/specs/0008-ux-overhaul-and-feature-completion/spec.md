# 0008 UX全面重构与功能完善 - Product Requirement Document

## Overview
- **Summary**: 对照豆包和Trae Work的交互体验，全面重构GerClaw的消息操作按钮、加载动画、功能入口欢迎语、CGA评估流程、五大处方生成流程，修复控制台错误，实现患者端/医生端角色切换，添加本地数据飞轮持久化。
- **Purpose**: 解决当前系统存在的消息操作按钮缺失、加载动画不美观、功能入口直接浪费token调用模型、CGA流程有bug、五大处方流程toy化、角色切换失效、搜索链接不可跳转、控制台报错等问题。
- **Target Users**: 老年患者、老年科医生

## Goals
1. 修复控制台所有错误（hydration mismatch、audio playback error等）
2. 移除模型选择器，去除聊天框自动选择按钮
3. 重做消息操作按钮行（复制、语音播放、分享/导出、点赞、点踩、重新生成、三点菜单含转为文档编辑和删除），参照豆包交互
4. 加载动画改为三点跳动动画（正文加载），思考动画为适中速率转圈
5. 搜索结果链接真实可跳转
6. 修改欢迎页快捷提问，去除意图模糊的问题
7. 功能入口点击后先显示固定欢迎语，用户输入后再调用模型
8. 精简系统提示语，减少不必要的思考token消耗
9. CGA评估：预录TTS音频占位、语音识别支持ABCD选项、不自动下一题、完成后不自动弹出右侧栏、多量表批量作答、量表题目数核查、作答进度保持、退出确认
10. 五大处方重构：固定欢迎语→文件上传(MinerU解析)→对话卡片收集缺失信息(参照Trae Work对话卡片)→本地知识库优先检索→联网搜索补充→JSON结构化输出→右侧栏渲染编辑导出→隐私脱敏
11. 删除患者端"用药审查"和"我的健康画像"功能入口
12. 统一所有导出按钮支持PDF/DOCX/MD三种格式
13. 修复患者/医生模式切换
14. 本地数据飞轮持久化（对话、报告、trace、反馈、用户修改记录）

## Non-Goals (Out of Scope)
- MinerU真实API集成的深度测试（API已配置，先做框架+真实调用，问题后续迭代）
- 真人录音替换TTS占位音频（先用TTS生成，后续可替换）
- 后端数据库存储（数据飞轮使用IndexedDB本地存储）
- 二阶段AgentScope多智能体架构
- RAG知识库向量检索（使用简单文本检索+联网搜索补充）

## Background & Context
- 项目基于Next.js 15 + React 19 + Zustand + Tailwind CSS + shadcn/ui
- MinerU API已在.env中配置（NEXT_PUBLIC_MINERU_URL和NEXT_PUBLIC_MINERU_API_KEY）
- 本地知识库位于/Users/qizs/conclusion/gerclaw/本地知识库/md/，包含谵妄、认知障碍、视力障碍、睡眠障碍、疼痛、焦虑、失能、吞咽障碍、压疮、冠心病等分类
- 五大处方输出模板已定义在docs/references/五大处方报告模板.md
- hzj_case.json提供了完整的患者输入数据结构参考
- 控制台现有3个代码错误需要修复：hydration mismatch、Audio playback error、搜索链接跳转
- 消息操作按钮在之前迭代中被意外移除

## Functional Requirements
- **FR-1**: 移除模型选择器，聊天框区域不再显示模型选择下拉
- **FR-2**: 每条AI回复底部显示操作按钮行：复制、语音播放(TTS)、分享、点赞、点踩、重新生成、三点菜单(转为文档编辑+删除)
- **FR-3**: 复制按钮：点击后将AI最终回复文本复制到剪贴板，显示复制成功提示
- **FR-4**: 语音播放按钮：默认不自动播放，点击后TTS朗读AI回复，再次点击停止播放；按钮图标根据播放状态切换
- **FR-5**: 分享按钮：点击弹出分享对话框，默认选中当前问答对，可勾选其他消息，支持PNG/PDF/DOCX/MD格式导出
- **FR-6**: 点赞/点踩按钮：点击后给出反馈输入框，提交后记录到数据飞轮
- **FR-7**: 重新生成按钮：删除最后一条AI回复，重新发送用户消息生成
- **FR-8**: 三点菜单：包含"转为文档编辑"和"删除"两个选项
- **FR-9**: 转为文档编辑：将AI回复渲染到右侧栏Markdown编辑器，支持编辑、复制、导出(PDF/DOCX/MD)
- **FR-10**: 删除(消息级)：弹出多选删除对话框，默认选中当前问答对，可勾选其他消息，确认前二次确认，删除后不进入模型上下文
- **FR-11**: 删除右上角全局导出按钮
- **FR-12**: 正文加载动画为三点跳动（···），思考中动画为适中速率spinner（降低动画速度）
- **FR-13**: 搜索结果中的链接使用<a target="_blank" rel="noopener noreferrer">确保新标签页打开
- **FR-14**: 欢迎页快捷提问改为有明确上下文的健康问题
- **FR-15**: 点击功能入口（五大处方、CGA评估）时，先在聊天区插入固定欢迎语消息，不调用LLM；用户发送消息后才开始功能流程
- **FR-16**: 精简系统提示语，去除冗长的字数校验指令，添加思考效率要求
- **FR-17**: CGA评估：用TTS预生成各量表题目和选项音频文件存放在public目录；语音答题支持"选项A/B/C/D"和"a/b/c/d"识别；选择选项后不自动跳转下一题，用户手动点"下一题"；音频播放遵循用户的播放/停止偏好（跨题目保持状态）
- **FR-18**: CGA完成后：右侧栏不自动弹出，中间栏显示"作答完毕"+完成量表列表+三个按钮（重新评估/继续作答其他量表/查看评估报告）
- **FR-19**: CGA量表选择：支持多选+全选，一次性按顺序作答所有选中量表，中途不切换
- **FR-20**: CGA继续作答：返回量表选择页，已作达标为已完成不可勾选，全答完显示"所有量表已作答完毕"+生成报告按钮
- **FR-21**: CGA量表题目数核查，确保与真实量表一致
- **FR-22**: CGA作答进度保持：不退出则保留所有作答数据；退出时根据是否有报告生成显示不同确认文案；无报告时退出不保存，有报告时保存报告
- **FR-23**: 五大处方流程：固定欢迎语→上传文件(图片/PDF/MD/DOCX)→MinerU解析文件→对照hzj_case.json模板检查缺失字段→对话卡片(每轮4题，最多3轮)收集信息→数据脱敏→先生成健康画像→再生成五大处方(药物/运动/营养/心理/康复)→用药冲突审查→本地知识库优先检索→联网搜索补充→JSON结构化输出→格式校验→渲染为Markdown→右侧栏可编辑导出
- **FR-24**: 患者端删除"用药审查"和"我的健康画像"功能入口（聊天区和快捷入口）
- **FR-25**: 所有导出按钮统一支持PDF/DOCX/MD三种格式（分享额外支持PNG）
- **FR-26**: 修复患者模式和医生模式之间的切换
- **FR-27**: 数据飞轮：IndexedDB持久化存储所有对话、生成报告、LLM trace、用户反馈(赞踩)、用户编辑修改记录

## Non-Functional Requirements
- **NFR-1**: 所有交互响应<100ms（按钮点击反馈）
- **NFR-2**: 三点加载动画速率适中（约1.2Hz），思考spinner速率适中（约0.8Hz），不闪烁刺眼
- **NFR-3**: 适老化：患者端老年模式≥18px正文字号、≥48px按钮、高对比度、图标必带文字标签
- **NFR-4**: 医疗安全底线：禁止确定性诊断，所有医疗输出带免责声明，高风险提示立即就医
- **NFR-5**: lint和build必须通过，无TypeScript错误
- **NFR-6**: 控制台无Error级别日志（Electron内部错误除外）

## Constraints
- **Technical**: Next.js 15 App Router、React 19、Zustand、Tailwind CSS、shadcn/ui、IndexedDB(通过idb库或原生API)
- **Business**: 老年医疗场景，安全合规优先
- **Dependencies**: MinerU API（已配置）、AnySearch/Tavily搜索API（已配置）、Mimo TTS/ASR（已配置）、本地知识库md文件

## Assumptions
- MinerU API可正常调用解析PDF/图片/DOCX/MD文件
- TTS预生成的音频可以作为占位，后续替换为真人录音
- IndexedDB在现代浏览器中可用，存储容量足够
- 本地知识库文件不需要向量检索，使用关键词匹配+文本片段检索即可

## Acceptance Criteria

### AC-1: 控制台无前端代码错误
- **Given**: 用户访问http://localhost:3000/
- **When**: 页面加载完成
- **Then**: 浏览器控制台无hydration mismatch错误、无Audio playback error（除了无音频源时的正常错误）、无未捕获异常
- **Verification**: `programmatic`

### AC-2: 模型选择器已移除
- **Given**: 用户在聊天界面
- **When**: 查看聊天输入区域
- **Then**: 不显示"选择模型"按钮或下拉菜单
- **Verification**: `human-judgment`

### AC-3: 消息操作按钮完整可用
- **Given**: AI回复完成
- **When**: 查看AI消息底部
- **Then**: 显示复制、播放、分享、点赞、点踩、重新生成、三点菜单按钮；所有按钮可点击并执行对应功能
- **Verification**: `human-judgment`

### AC-4: 三点菜单功能
- **Given**: 用户点击AI消息的三点菜单
- **When**: 菜单展开
- **Then**: 显示"转为文档编辑"和"删除"两个选项；点击转为文档编辑则右侧栏打开编辑器；点击删除弹出多选删除对话框
- **Verification**: `human-judgment`

### AC-5: 加载动画正确
- **Given**: AI正在生成回复正文
- **When**: 正文内容尚未到达但已开始streaming
- **Then**: 显示三点跳动动画而非spinner
- **Verification**: `human-judgment`

### AC-6: 思考动画速率适中
- **Given**: AI正在思考（thinking状态）
- **When**: ThinkingBlock显示中
- **Then**: spinner旋转速率适中，不刺眼不闪烁
- **Verification**: `human-judgment`

### AC-7: 搜索结果链接可跳转
- **Given**: 搜索工具返回结果并展开
- **When**: 用户点击搜索结果标题
- **Then**: 在新标签页打开对应网页URL
- **Verification**: `programmatic`

### AC-8: 欢迎语不浪费token
- **Given**: 用户点击"五大处方生成"或"老年综合评估"入口
- **When**: 功能入口被点击
- **Then**: 聊天区显示固定欢迎语（非LLM生成），不调用LLM API；用户输入消息后才开始LLM调用
- **Verification**: `programmatic`

### AC-9: CGA语音答题支持ABCD
- **Given**: 用户在CGA答题页面，语音播放开启
- **When**: 用户语音说"A"或"选项A"
- **Then**: 系统识别并选中A选项；选中后不自动进入下一题
- **Verification**: `programmatic`

### AC-10: CGA完成后流程正确
- **Given**: 用户完成所有选中量表的题目
- **When**: 最后一题作答完毕
- **Then**: 右侧栏不自动弹出；中间栏显示"作答完毕"+已完成量表列表+"重新评估"/"继续作答其他量表"/"查看评估报告"三个按钮
- **Verification**: `human-judgment`

### AC-11: 五大处方MinerU文件解析
- **Given**: 用户进入五大处方流程
- **When**: 上传PDF/图片/DOCX/MD文件
- **Then**: 调用MinerU API解析文件，提取结构化信息
- **Verification**: `programmatic`

### AC-12: 五大处方对话卡片收集
- **Given**: 用户信息有缺失字段
- **When**: 信息校验发现缺失
- **Then**: 以对话卡片形式展示最多4道问题让用户作答，最多3轮
- **Verification**: `human-judgment`

### AC-13: 五大处方右侧栏编辑
- **Given**: 五大处方生成完成
- **When**: 报告生成后
- **Then**: 在右侧栏渲染Markdown报告，支持编辑、复制、导出(PDF/DOCX/MD)
- **Verification**: `human-judgment`

### AC-14: 患者端无用药审查和健康画像
- **Given**: 用户处于患者/访客模式
- **When**: 查看欢迎页和聊天输入区快捷按钮
- **Then**: 不显示"用药审查"和"我的健康画像"按钮
- **Verification**: `human-judgment`

### AC-15: 角色切换正常
- **Given**: 用户在任意角色页面
- **When**: 点击角色切换按钮切换到医生/患者模式
- **Then**: 页面正确切换到对应模式，显示对应功能
- **Verification**: `human-judgment`

### AC-16: 数据飞轮持久化
- **Given**: 用户进行对话、生成报告、提交反馈
- **When**: 刷新页面
- **Then**: 历史对话、报告、反馈记录仍然存在（从IndexedDB恢复）
- **Verification**: `programmatic`

## Open Questions
- [ ] CGA量表的TTS音频生成：是在构建时预生成还是首次使用时缓存？→ 构建时/首次使用时生成到public/audio/cga/目录
- [ ] MinerU API的具体调用方式（文件上传URL/参数格式）需要根据实际API文档调整 → 先按常见REST API方式实现，根据实际测试调整
- [ ] 对话卡片组件的UI样式参照Trae Work，需要在实现时参考截图设计
