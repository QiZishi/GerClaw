# 0012 最终需求完整实现 - The Implementation Plan

## [ ] Task 1: 修复P0-1 角色切换问题+修复现有lint错误
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 检查setRole状态重置逻辑是否完整
  - 检查DoctorHome组件确保无白屏
  - 确保用药审查/健康画像按钮仅医生可见
  - 修复CGAConversation.tsx中的react-hooks/set-state-in-effect lint错误
- **Acceptance Criteria Addressed**: AC-1, AC-11
- **Test Requirements**:
  - `human-judgement` TR-1.1: 访客→患者→医生切换正常无白屏
  - `human-judgement` TR-1.2: 医生模式能看到用药审查和健康画像按钮
  - `programmatic` TR-1.3: npm run lint无CGAConversation错误

## [ ] Task 2: 修复P0-2 流式输出/思考状态/中断恢复+动画
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 检查ThinkingBlock点击事件，确保只折叠/展开不中断生成
  - 修复停止按钮后的持久错误状态，reset streamingInterrupted
  - 检查SSE处理：thinkingStarted初始化、thinking delta正确渲染
  - 确认globals.css中spinner动画1.5s、三点脉冲1.2s
  - 确认停止按钮无animate-pulse
- **Acceptance Criteria Addressed**: AC-2, AC-3
- **Test Requirements**:
  - `human-judgement` TR-2.1: 点击ThinkingBlock只折叠不中断
  - `human-judgement` TR-2.2: 停止后下次发送正常
  - `human-judgement` TR-2.3: thinking和text正确流式渲染
  - `programmatic` TR-2.4: CSS动画时长正确

## [ ] Task 3: 修复P0-3 CGA语音预录音频+播放状态机
- **Priority**: high
- **Depends On**: Task 2
- **Description**: 
  - 移除CGA中所有TTS调用，改用 `/audio/scales/${scaleId}_${questionId}.mp3`
  - 音频不存在时静默处理（try/catch，不报错）
  - 实现播放状态机：cgaAudioEnabled状态持久在整个评估会话
  - 点停止→cgaAudioEnabled=false，后续不自动播放
  - 点播放→cgaAudioEnabled=true，后续自动播放
  - 返回量表选择页时stopAudio()
  - 语音识别选项后高亮但不自动跳转，需手动点下一题
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `programmatic` TR-3.1: 代码中无CGA调用TTS的地方
  - `human-judgement` TR-3.2: 播放/停止状态在切换题目时保持
  - `human-judgement` TR-3.3: 选完选项不自动跳题
  - `human-judgement` TR-3.4: 返回时音频停止

## [ ] Task 4: 移除普通聊天自动TTS
- **Priority**: high
- **Depends On**: Task 3
- **Description**: 
  - 搜索并移除所有autoRead/autoPlay/autoTTS相关逻辑在普通聊天场景
  - 确认只有CGA评估内有自动播放逻辑
  - 老年模式普通聊天也不自动播放
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**:
  - `programmatic` TR-4.1: grep无autoReadIfSeniorMode等自动播放
  - `human-judgement` TR-4.2: AI回复后不自动播放语音

## [ ] Task 5: 完善消息操作按钮
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 复制按钮：navigator.clipboard.writeText，toast"已复制"2秒
  - 语音播放按钮：点击播放/停止切换，调用useAudioPlayer
  - 导出按钮：点击弹出ExportDialog，默认选中当前AI+对应的用户提问
  - 点赞/点踩：点击后toast"感谢反馈"，无需反馈框
  - 重新生成：只在最后一条AI消息显示
  - 三点菜单：DropdownMenu，包含"转为文档编辑"和"删除"
  - 转为文档编辑：setRightPanel('doc-editor')，panelContent设为AI文本
  - 删除：弹出DeleteConfirmDialog确认后removeMessage
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgement` TR-5.1: 各按钮功能正常
  - `human-judgement` TR-5.2: 导出默认选中一组问答
  - `human-judgement` TR-5.3: 点赞点踩只显示toast

## [ ] Task 6: 修复联网搜索链接可跳转
- **Priority**: medium
- **Depends On**: Task 5
- **Description**: 
  - 检查SearchResultCard/ToolCallBlock：标题用<a>标签，target="_blank" rel="noopener noreferrer"
  - 检查CitationPopover/SourceReferences："查看原文"按钮window.open或<a>标签正确
  - 移除任何e.preventDefault()在链接点击处
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-6.1: 链接有target="_blank" rel="noopener noreferrer"
  - `human-judgement` TR-6.2: 点击在新标签页打开

## [ ] Task 7: CGA完成页+量表选择多选
- **Priority**: medium
- **Depends On**: Task 6
- **Description**: 
  - 修复完成页不自动打开右侧栏（移除openRightPanel自动调用）
  - 完成页显示"作答完毕"+已完成量表名（逗号分隔）
  - 三个按钮并列：重新评估、继续作答其他量表、查看评估报告
  - 查看评估报告：点击才调用生成报告并打开右侧栏
  - 继续作答：返回ScaleSelector，已完成量表显示"已作答"badge且disabled
  - ScaleSelector：添加全选按钮；支持多选；localStorage保存进度
  - 多选后合并题目一次性作答，中途不切换量表界面
  - 所有量表完成显示"所有量表已作答完毕"+生成报告按钮
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `human-judgement` TR-7.1: 完成后不自动弹右侧栏
  - `human-judgement` TR-7.2: 三按钮功能正常
  - `human-judgement` TR-7.3: 量表多选+全选
  - `human-judgement` TR-7.4: 已完成量表禁用

## [ ] Task 8: 五大处方生成流程完善
- **Priority**: medium
- **Depends On**: Task 7
- **Description**: 
  - 点击五大处方按钮立即显示固定欢迎语（getOpeningMessage），不调用LLM
  - 用户输入后开始收集信息，使用InfoCollectionCard显示字段
  - 字段列表：年龄/性别/慢病/用药/吸烟/饮酒/运动/饮食/睡眠/情绪
  - 调用LLM前desensitizeForLLM脱敏PII
  - 最多5轮收集后生成五大处方
  - 本地知识库返回503维护中，不加载436文件
  - 生成后在对话显示，右侧栏Markdown编辑器打开完整报告
  - 所有医疗内容带免责声明，高风险提示就医
- **Acceptance Criteria Addressed**: AC-8
- **Test Requirements**:
  - `human-judgement` TR-8.1: 点击立即显示欢迎语无加载
  - `human-judgement` TR-8.2: InfoCollectionCard显示收集字段
  - `programmatic` TR-8.3: PII脱敏函数正常
  - `human-judgement` TR-8.4: 右侧栏显示可编辑导出的报告
  - `programmatic` TR-8.5: 知识库返回503

## [ ] Task 9: 文件上传10个+导出统一
- **Priority**: medium
- **Depends On**: Task 8
- **Description**: 
  - 确认constants.ts中maxFileCount=10
  - 检查FileUpload组件支持10个文件
  - MinerU API解析，若MINERU_API_KEY未配置则降级提示不崩溃
  - 统一所有导出按钮支持PDF/DOCX/Markdown三种格式
  - 确认ExportDialog格式选项正确
- **Acceptance Criteria Addressed**: AC-9
- **Test Requirements**:
  - `programmatic` TR-9.1: maxFileCount=10
  - `programmatic` TR-9.2: MinerU路由存在，未配置时友好提示
  - `human-judgement` TR-9.3: 所有导出按钮有PDF/DOCX/MD选项

## [ ] Task 10: 修复hydration mismatch+其他细节
- **Priority**: medium
- **Depends On**: Task 9
- **Description**: 
  - 检查layout.tsx和page.tsx，使用mounted状态确保SSR/CSR一致
  - 检查有无window/document在SSR阶段访问
  - 确保所有按钮文字标签完整（适老化要求）
  - 修复3个unused var警告
- **Acceptance Criteria Addressed**: AC-10, AC-11
- **Test Requirements**:
  - `human-judgement` TR-10.1: 控制台无hydration错误
  - `programmatic` TR-10.2: 无unused var警告

## [ ] Task 11: Lint+Build最终验证
- **Priority**: high
- **Depends On**: Task 10
- **Description**: 
  - 运行npm run lint，修复所有错误和警告
  - 运行npm run build，确保TypeScript类型检查通过
  - 修复所有发现的问题
- **Acceptance Criteria Addressed**: AC-11
- **Test Requirements**:
  - `programmatic` TR-11.1: npm run lint 0 errors, 0 warnings
  - `programmatic` TR-11.2: npm run build成功
