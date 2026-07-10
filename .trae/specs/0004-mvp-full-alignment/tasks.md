# 0004-MVP全量功能对齐与上线 — The Implementation Plan (Decomposed and Prioritized Task List)

## [x] Task 1: 提示语统一与环境变量检查
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 修改client.ts中所有system prompt：移除"小Ger"自称，统一为"GerClaw医学诊疗智能体"
  - 患者端话术保持亲切温柔，医生端保持专业简洁
  - 检查.env.example完整性，补全缺失配置项（Mimo URL配置等）
  - 核对当前.env.local配置有效性，确保主备模型、ASR/TTS、搜索配置正确
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: grep检查代码中无"小Ger"字样
  - `programmatic` TR-1.2: .env.example包含所有必要配置项
  - `human-judgement` TR-1.3: AI回复中自称符合规范
- **Notes**: 这是基础任务，优先完成以避免后续重复修改

## [x] Task 2: 真流式输出架构修复
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 重构StreamingText组件：移除setInterval伪造逐字逻辑，改为直接渲染传入的content
  - 修改ChatArea中onText回调：每收到delta立即updateMessage追加内容，不累积fullText后一次性设置
  - 首token到达前显示Loader2旋转圆圈（当streaming=true且content为空时）
  - 流式过程中显示闪烁光标（typing-cursor CSS）
  - 修改SSE解析确保delta正确传递（检查client.ts中onText回调参数）
  - 处理SSE中断：保留已接收内容，标记为stopped状态
- **Acceptance Criteria Addressed**: AC-1
- **Test Requirements**:
  - `programmatic` TR-2.1: StreamingText中无setInterval代码
  - `human-judgement` TR-2.2: 发送消息后文字逐块出现（不是等很久然后逐字蹦）
  - `human-judgement` TR-2.3: 首字到达前显示旋转Loader
  - `human-judgement` TR-2.4: 停止生成后保留已接收内容
- **Notes**: 这是核心架构修复，影响所有流式场景

## [x] Task 3: 思维链可视化实现
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 扩展LLMStreamCallbacks接口，添加onThinkingDelta回调
  - 修改client.ts处理reasoning_content/thinking字段，调用onThinkingDelta
  - 修改ChatArea：添加thinking block到消息blocks
  - 完善ThinkingBlock组件：默认折叠、"思考中..."旋转动画、点击展开/收起
  - 思考完成自动收起（思考内容接收完毕后默认折叠，可手动展开）
  - 低对比度浅灰背景样式
  - 若模型不支持thinking，显示简化的"思考中..."状态指示器（不显示空区块）
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgement` TR-3.1: AI思考时显示"思考中..."折叠区块
  - `human-judgement` TR-3.2: 点击展开可查看思考内容
  - `human-judgement` TR-3.3: 思考完成后自动收起
- **Notes**: 需确认当前配置模型是否返回reasoning_content

## [x] Task 4: 工具调用卡片与搜索可视化完善
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - 为搜索流程添加ToolCallBlock：搜索开始时显示运行中卡片，完成后显示✓，失败显示✗
  - 搜索卡片点击展开显示搜索query和结果概览
  - 失败状态显示重试按钮
  - 实现引用角标：检测AI回复中的[1][2]标记，渲染为蓝色上角标
  - 点击角标在右侧面板展开对应引用详情（标题、来源、摘要、链接）
  - 简化版DecisionTimeline：显示"思考中→搜索中→回答中"步骤指示器
  - 简化版SubAgentTree：MVP阶段显示单智能体状态即可
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgement` TR-4.1: 搜索时显示工具调用卡片（运行中→完成）
  - `human-judgement` TR-4.2: 搜索结果在AI回复中以[1][2]角标标注
  - `human-judgement` TR-4.3: 点击角标在右侧面板显示引用详情
  - `human-judgement` TR-4.4: 工具失败显示重试按钮
- **Notes**: MVP阶段工具主要是搜索，图片理解不需要单独工具卡片

## [x] Task 5: 可靠性容错机制实现
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - 实现React Error Boundary组件：包裹整个App，捕获渲染错误显示友好错误页+重试按钮
  - 网络状态检测：使用navigator.onLine+定期fetch轻量请求检测，离线时顶部显示横幅提示，禁用发送按钮
  - localStorage写满检测：chatStore保存时try-catch，QuotaExceededError时提示用户导出重要对话后清除历史
  - API降级用户提示：ASR/TTS不可用时按钮禁用，hover显示"语音服务暂时不可用"
  - 流式中断处理：SSE错误时保留已接收内容，显示"回复中断，点击重试"
  - 所有错误提示使用用户能理解的自然语言，不显示技术错误栈
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `human-judgement` TR-5.1: 组件报错不白屏，显示错误边界提示
  - `human-judgement` TR-5.2: 断网时显示离线提示
  - `human-judgement` TR-5.3: localStorage满时提示用户
  - `human-judgement` TR-5.4: 错误信息无技术术语
- **Notes**: 可以先实现Error Boundary和离线检测，其他容错可简化

## [x] Task 6: CGA全语音交互实现
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 修改CGAConversation组件：进入新题目时，老年模式下自动调用TTS朗读题目文本+选项
  - 添加"朗读题目"按钮到题目导航区域
  - 集成ASR语音答题：CGA答题区域添加麦克风按钮，点击开始录音，识别后尝试匹配选项关键词
  - 识别成功自动选中对应选项，识别失败允许手动选择
  - 上一题/下一题切换时停止当前朗读并自动朗读新题目
  - 评估完成时TTS提示"评估已完成，请在右侧查看结果"
  - 语音按钮大小符合适老化规范（≥48px点击区）
- **Acceptance Criteria Addressed**: AC-4, AC-9
- **Test Requirements**:
  - `human-judgement` TR-6.1: 进入CGA答题自动朗读第一题（老年模式）
  - `human-judgement` TR-6.2: 点击下一题自动朗读新题目
  - `human-judgement` TR-6.3: 麦克风按钮点击可录音识别答案
  - `human-judgement` TR-6.4: 语音按钮≥48px
- **Notes**: 语音答题关键词匹配需要容错（比如选"是"能匹配"是的""对""有"等）

## [x] Task 7: 五大处方语音引导
- **Priority**: medium
- **Depends On**: Task 6
- **Description**:
  - 五大处方开场消息发送完成后，老年模式下自动TTS朗读
  - AI追问消息流式完成后自动TTS朗读（老年模式）
  - 确保VoiceReadButton在处方流程消息中正常工作
  - 处方生成完成摘要消息自动TTS朗读提示
  - 用药审查流程同步支持语音朗读
- **Acceptance Criteria Addressed**: AC-4, AC-9
- **Test Requirements**:
  - `human-judgement` TR-7.1: 五大处方开场自动朗读（老年模式）
  - `human-judgement` TR-7.2: AI追问自动朗读
  - `human-judgement` TR-7.3: 每条消息有朗读按钮可用
- **Notes**: 复用现有useAudioPlayer和VoiceReadButton逻辑

## [x] Task 8: UI交互细节补齐
- **Priority**: medium
- **Depends On**: Task 7
- **Description**:
  - 右侧面板拖拽调整宽度：实现拖拽手柄，宽度范围320-500px，默认400px（宽度可记忆到localStorage）
  - 完善消息操作按钮：悬停时清晰显示复制/重新生成/朗读/导出按钮
  - 欢迎页快捷入口卡片：确保五大处方/CGA/用药审查/健康画像四个卡片点击正确触发功能
  - 左侧边栏布局微调：确保标识区、新建按钮（蓝色主按钮全宽）、技能按钮（⚡+文字）、搜索框顺序正确
  - 免责声明可见性检查：所有AI消息底部、输入框底部都显示免责声明
  - 思考区块和工具卡片样式统一对齐设计规范
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `human-judgement` TR-8.1: 右侧面板可拖拽调整宽度
  - `human-judgement` TR-8.2: 欢迎页四个快捷入口可点击
  - `human-judgement` TR-8.3: 免责声明在所有医疗场景可见
  - `human-judgement` TR-8.4: 消息操作按钮悬停清晰显示
- **Notes**: 右侧面板拖拽可用简单的mousedown/mousemove/mouseup实现，不需要额外库

## [x] Task 9: 全量回归测试与bug修复
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  - 运行npm run lint，修复所有警告和错误
  - 运行npm run build，确保构建成功，静态页面完整生成
  - 启动npm run dev，手动测试核心流程：
    - 普通文本对话（真流式输出）
    - 语音输入ASR
    - 语音朗读TTS
    - 联网搜索+引用角标
    - 五大处方生成流程（对话收集→生成报告→导出）
    - CGA评估流程（选量表→答题（含语音）→生成报告→导出）
    - 用药审查流程
    - 图片上传多模态理解
    - Markdown导出（单消息/会话/报告）
    - 角色切换（医生/患者）
    - 老年模式切换（字号/按钮/语音自动朗读）
    - 停止生成/重新生成
    - 新建会话/切换会话/删除会话
    - 会话持久化（刷新页面数据不丢失）
  - 适老化检查：字体≥18px、按钮≥48px、高对比度、二次确认
  - 医疗安全检查：无确定性诊断、免责声明可见、高风险提示
  - 修复测试中发现的所有bug
- **Acceptance Criteria Addressed**: AC-7, AC-8, AC-9, AC-10
- **Test Requirements**:
  - `programmatic` TR-9.1: npm run lint 0错误0警告
  - `programmatic` TR-9.2: npm run build成功
  - `human-judgement` TR-9.3: 所有核心流程手动测试通过
  - `human-judgement` TR-9.4: 适老化规范检查通过
  - `human-judgement` TR-9.5: 医疗安全检查通过
- **Notes**: 这是最终质量门禁任务，必须全部通过才算完成

## Task Dependencies Graph
```
Task 1 (提示语/环境变量)
  ↓
Task 2 (真流式修复)
  ↓
Task 3 (思维链)
  ↓
Task 4 (工具卡片/搜索完善)
  ↓
Task 5 (可靠性容错)
  ↓
Task 6 (CGA语音)
  ↓
Task 7 (处方语音)
  ↓
Task 8 (UI细节)
  ↓
Task 9 (回归测试)
```
