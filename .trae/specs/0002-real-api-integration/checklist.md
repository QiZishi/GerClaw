# GerClaw 0002 — 真实 API 接入与 Mock 数据清理 - 验证清单

## 环境变量与 Mock 清理（Task 1）
- [ ] `.env.local` 文件存在于 `apps/mvp/` 下，包含所有 `NEXT_PUBLIC_` 前缀变量
- [ ] `.env.example` 模板文件创建完成，包含变量说明和占位符
- [ ] `lib/config.ts` Zod 校验更新，主模型配置缺失时有明确警告
- [ ] `src/data/mock/` 目录已完全删除
- [ ] CGA 量表数据已迁移到 `src/data/scales.ts`（正式静态医疗数据）
- [ ] 预置技能列表已迁移到 `src/data/skills.ts`（正式静态配置数据）
- [ ] 全局搜索 `from @/data/mock` 无匹配结果
- [ ] ChatArea.tsx 中无 mock 导入，scales 从 `@/data/scales` 导入
- [ ] Sidebar.tsx 不依赖 mockSessions，从 Zustand store 初始化
- [ ] 所有 setTimeout 模拟 AI 回复逻辑已移除
- [ ] `npm run build` 成功，TypeScript 无类型错误
- [ ] `npm run lint` 通过，0 错误 0 警告
- [ ] 启动 dev server 后首页正常显示，欢迎页可见，CGA 选量表显示 5 个量表卡片

## API Client 基础设施（Task 2）
- [ ] `src/services/` 目录结构创建完成
- [ ] `src/services/api-client.ts` 实现：超时控制、指数退避重试、错误分类、Trace ID、AbortController
- [ ] `src/services/llm/client.ts` 实现：streamChat 函数、主备自动降级、SSE 解析、系统 prompt 构建
- [ ] 患者端 system prompt：亲切、易懂、短句、无专业术语、鼓励就医、禁确定性诊断
- [ ] 医生端 system prompt：专业、简洁、循证、标注依据、禁最终诊断
- [ ] `src/services/llm/index.ts` 导出公共 API
- [ ] TypeScript 编译通过，services 层不依赖 React/Hooks
- [ ] 代码 review：LLM client 实现了主备降级逻辑，有完整错误处理

## 真实 LLM 流式对话（Task 3）
- [ ] 普通聊天模式调用真实 LLM streamChat，无 setTimeout 模拟
- [ ] AI 消息以流式打字机效果逐字输出 Markdown
- [ ] 流式输出过程中停止按钮可中断生成（AbortController）
- [ ] 停止后消息显示为"已停止"状态
- [ ] 重新生成按钮可重新发起 AI 回复
- [ ] 复制按钮可复制消息纯文本到剪贴板
- [ ] 消息历史最多保留最近 20 轮发送给 LLM
- [ ] 新会话首次 AI 回复后自动设置标题（用户首条消息前 20 字符）
- [ ] 高风险症状（胸痛等）检测：先显示红色紧急就医卡片，再调用 LLM
- [ ] AI 回复末尾自动附加医疗免责声明
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：输入"你好，我最近睡眠不好怎么办"看到流式回复
- [ ] 手动测试：输入"胸痛"看到红色紧急卡片
- [ ] 手动测试：停止、重新生成、复制按钮功能正常

## Mimo ASR 语音输入（Task 4）
- [ ] `src/services/voice/asr.ts` 实现：recognizeAudio 函数，Base64 编码，Mimo API 调用
- [ ] ASR API 使用 `api-key` header（非 Authorization: Bearer）
- [ ] `src/hooks/useAudioRecorder.ts` 实现：MediaRecorder 封装、录音状态、音量指示、时长计时
- [ ] ChatInput.tsx 麦克风按钮移除"功能开发中"toast
- [ ] 录音中 UI：停止图标（红色）、录音时长显示、脉冲动画、音量指示条
- [ ] 停止录音后调用 ASR，识别过程显示 loading 状态
- [ ] 识别结果自动填入 textarea，可编辑发送
- [ ] 麦克风权限拒绝时给出适老化友好提示
- [ ] ASR 失败时 toast 提示"语音识别失败，请重试"
- [ ] 老年模式：大字提示"正在录音…"、"正在识别…"，按钮尺寸加大
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：点击麦克风→允许权限→录音→停止→识别文本填入输入框
- [ ] 手动测试：识别文本可编辑后发送

## Mimo TTS 语音朗读（Task 5）
- [ ] `src/services/voice/tts.ts` 实现：streamTTS 函数，SSE 解析 PCM16 chunk
- [ ] TTS 使用冰糖音色，中文女声
- [ ] `src/hooks/useAudioPlayer.ts` 实现：Web Audio API PCM16 24kHz 播放、缓冲队列
- [ ] 朗读按钮移除"功能开发中"toast
- [ ] 按钮状态切换：播放→播放中（暂停图标）→暂停→播放完成恢复
- [ ] 播放中可暂停/继续
- [ ] TTS 失败时 toast 提示"语音播放失败"
- [ ] 老年模式：播放按钮更大，状态指示清晰
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：点击 AI 消息朗读按钮听到语音播放
- [ ] 手动测试：播放中点击暂停可暂停，再次点击继续
- [ ] 手动测试：播放完成按钮自动恢复初始状态

## 联网搜索（Task 6）
- [ ] `src/services/search/search-client.ts` 实现：AnySearch 主 + Tavily 备
- [ ] 搜索结果格式统一：title/url/snippet/source/favicon
- [ ] 搜索触发机制：LLM 输出特殊标记或用户消息含"搜索"/"查一下"/"最新"关键词
- [ ] 搜索结果使用 SearchResultCard 在消息流中展示
- [ ] AI 回复引用搜索结果时使用 [1][2] 上标
- [ ] 点击角标可展开引用详情（CitationPopover）
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：问"最新高血压指南是什么"可见搜索结果卡片和引用

## 五大处方真实 LLM 生成（Task 7）
- [ ] 五大处方流程移除硬编码字段追问和 setTimeout 模拟
- [ ] AI 使用专门 system prompt 通过自然对话引导收集信息
- [ ] 一次询问 1-2 个问题，像聊天而非填表
- [ ] AI 判断信息充分后输出 `[生成处方]` 标记
- [ ] 检测到标记后进入处方生成阶段，显示 GeneratingOverlay
- [ ] 处方以 Markdown 格式流式输出到右侧面板
- [ ] 生成完成后 AI 发送摘要消息 + "查看完整处方"按钮
- [ ] 保留 5 轮对话上限保护，超过则基于已有信息生成
- [ ] 患者端话术亲切易懂，医生端话术专业简洁结构化
- [ ] 处方内容末尾附医疗免责声明
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试（患者模式）：点击五大处方→自然对话→生成处方→右侧面板查看
- [ ] 手动测试（医生模式）：话术专业简洁

## CGA 评估 AI 解读（Task 8）
- [ ] 保留三阶段 UI（选量表→答题→完成），使用正式 scales 静态数据
- [ ] 移除 mock setTimeout 假完成逻辑
- [ ] 答题完成后构建 prompt（量表名+答题结果+得分+分级）
- [ ] 代码计算量表得分和分级（非 LLM 判断）
- [ ] 调用 LLM 流式生成评估解读（结果概述+详细解读+建议+就医提示）
- [ ] CGAReport 组件展示 LLM 解读 + 得分摘要
- [ ] 结果末尾附免责声明
- [ ] PHQ-9 第 9 题得分>0 时强烈建议立即就医/危机干预热线
- [ ] 适老化细节保持：按钮尺寸、字体大小、导航
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：选 PHQ-9→答题→提交→AI 流式生成解读→右侧面板展示

## 用药审查 AI 辅助（Task 9）
- [ ] 用药审查流程移除硬编码字段追问，改为 LLM 驱动对话
- [ ] System prompt 指示收集：用药清单/诊断/不良反应
- [ ] 生成结构化审查报告：用药汇总+相互作用+Beers提醒+剂量建议+就医建议
- [ ] 报告开头醒目标注："⚠️ AI 辅助用药审查仅供参考，不替代专业药师/医生判断"
- [ ] 医生端/患者端提示差异化
- [ ] 右侧面板展示审查报告
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试（医生模式）：进入用药审查→输入药物→AI 生成审查建议

## 医疗安全后处理（Task 10）
- [ ] `src/lib/security-postprocess.ts` 创建：postprocessMedicalText 函数
- [ ] 免责声明自动附加（检查末尾是否已有，无则追加）
- [ ] 确定性诊断拦截：检测"确诊为"/"你得了XX病"/"肯定是"等，替换为可能性表述
- [ ] 高风险词二次检查：输出中提及高危症状但未提示就医则强补
- [ ] 自杀风险提示：PHQ-9 第9题>0 或消息提自杀/不想活时，附危机干预热线
- [ ] 所有 LLM onDone 回调中调用后处理
- [ ] 高风险症状红色卡片逻辑优先于 LLM 回复
- [ ] 单元测试：确定性表述正确拦截
- [ ] 单元测试：免责声明自动追加
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：AI 回复不出现确定性诊断用语
- [ ] 手动测试：提到自杀相关内容时出现危机热线提示

## 会话 localStorage 持久化（Task 11）
- [ ] chatStore.ts 所有修改操作后自动持久化到 localStorage
- [ ] Store 初始化时从 localStorage 读取历史数据
- [ ] localStorage 操作 try-catch 防护，损坏数据自动清除
- [ ] 消息过多自动截断（保留最近 50 条/会话）
- [ ] 会话列表按 updatedAt 降序排列
- [ ] 删除会话同步删除对应消息
- [ ] `npm run build` + `npm run lint` 通过
- [ ] 手动测试：创建对话→发消息→刷新页面→会话和消息恢复
- [ ] 手动测试：删除会话→刷新→会话不再出现
- [ ] 手动测试：新对话标题自动更新

## 全量构建验证与回归（Task 12）
- [ ] `npm run lint` 0 错误 0 警告
- [ ] `npm run build` 成功，Next.js 静态导出完成
- [ ] Playwright 自动化测试核心路径 PASS ≥ 20 项
- [ ] 患者模式/医生模式切换正常，主色差异化正确
- [ ] 普通对话流式回复完整流程（发送→流式→停止/重发/复制）
- [ ] 高风险症状检测（胸痛、呼吸困难等）红色卡片显示
- [ ] 老年模式切换：基础字号 18px（老年 20px）、按钮≥48px、高对比度、二次确认
- [ ] 五大处方完整流程（患者端）
- [ ] CGA 评估完整流程
- [ ] 用药审查完整流程（医生端）
- [ ] 语音输入功能可用（麦克风权限允许时）
- [ ] 语音朗读功能可用
- [ ] 会话持久化（刷新恢复）
- [ ] 侧边栏完全折叠，仅显示展开和新建按钮并排
- [ ] 右侧面板自动展开/收起，宽度默认 480px，内容可编辑
- [ ] 技能面板在中间栏展示，有返回按钮
- [ ] 适老化回归：所有核心页面正文字号≥18px，按钮≥48px（老年模式），高对比度
- [ ] 医疗安全：所有 AI 医疗输出带免责声明，无确定性诊断
- [ ] 配置无硬编码：所有 API Key/模型名/URL 通过环境变量
- [ ] dev server 正常启动 http://localhost:3000，无控制台报错
