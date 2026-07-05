# 0002-真实API接入与Mock数据清理 — 执行计划

> 任务编号：0002 | 创建日期：2026-07-06 | 优先级：P0 | 阶段：二（真实API接入，删除mock）

---

## 1. 任务目标

在0001已完成的前端UI壳子基础上，**删除所有Mock数据**，搭建API Client基础设施层，从`/Users/qizs/conclusion/gerclaw/.env.local`搬运并配置环境变量，接入真实LLM流式对话、Mimo ASR/TTS语音交互、联网搜索等核心能力，使GerClaw MVP从可交互UI原型升级为可真实使用的AI诊疗助手。所有功能必须真实调用API，禁止setTimeout模拟。

## 2. 范围

### 2.1 做什么

#### A. 环境变量配置与Mock数据清理
- 从 `/Users/qizs/conclusion/gerclaw/.env.local` 复制环境变量到 `apps/mvp/.env.local`，变量名适配Next.js公开变量（`NEXT_PUBLIC_`前缀）
- 更新 `lib/config.ts` Zod校验，主模型配置缺失时给出明确警告
- 创建 `.env.example` 模板文件
- 将CGA量表数据（phq9/gad7/psqi/miniCog/mmse）从mock提取到`src/data/scales.ts`作为正式静态医疗数据
- 将预置技能列表从mock提取到`src/data/skills.ts`作为正式静态配置数据
- 删除`src/data/mock/`目录下其余纯mock文件（messages/sessions/prescription/drug-review/patients/search-results）
- 全局清理所有mock导入和setTimeout模拟AI回复逻辑
- 删除整个`src/data/mock/`目录

#### B. API Client基础设施层
- 创建`src/services/api-client.ts`：统一API客户端基类（超时/指数退避重试/错误分类/Trace ID/AbortController）
- 创建`src/services/llm/client.ts`：LLM流式对话封装
  - 支持OpenAI协议SSE流式解析
  - 主备自动降级（primary→backup1→backup2）
  - 患者端/医生端差异化system prompt
  - 医疗安全指令内置
- 创建`src/services/llm/index.ts`：导出公共API
- 创建`src/services/voice/asr.ts`：Mimo ASR语音识别（非流式，Base64传输）
- 创建`src/services/voice/tts.ts`：Mimo TTS语音合成（PCM16流式SSE）
- 创建`src/hooks/useAudioRecorder.ts`：MediaRecorder录音封装+音量指示
- 创建`src/hooks/useAudioPlayer.ts`：Web Audio API PCM16流式播放
- 创建`src/services/search/search-client.ts`：AnySearch主+Tavily备搜索封装

#### C. 真实LLM流式对话
- 普通聊天模式：用户文本→LLM流式回复→打字机效果渲染Markdown
- 停止生成：AbortController中断
- 重新生成：重新发起上一条AI回复
- 复制按钮：复制纯文本到剪贴板
- 消息历史管理：最近20轮发送给LLM
- 自动会话标题：首次AI回复后用用户首条消息前20字符
- 高风险症状检测：先显示红色紧急就医卡片，再调用LLM

#### D. Mimo ASR语音输入
- 麦克风权限请求
- MediaRecorder录音+实时音量指示+录音时长
- 录音停止→ASR识别→结果填入textarea
- 权限拒绝/API失败的适老化友好提示

#### E. Mimo TTS语音朗读
- AI消息播放按钮→TTS流式PCM16→Web Audio API实时播放（冰糖音色）
- 播放中暂停/继续控制
- 播放状态视觉反馈

#### F. 联网搜索
- 用户消息含"搜索"/"查一下"/"最新"关键词时触发搜索
- 搜索结果卡片展示（标题/favicon/snippet/链接）
- AI回复中[1][2]角标引用
- AnySearch失败降级Tavily

#### G. 五大处方真实LLM生成
- LLM驱动自然对话式信息收集（非硬编码字段追问）
- 一次问1-2个问题，像聊天而非填表
- AI判断信息充分后输出`[生成处方]`标记
- 流式生成Markdown格式五大处方报告到右侧面板
- 摘要回复+"查看完整处方"按钮
- 5轮对话上限保护
- 患者端亲切/医生端专业差异化话术

#### H. CGA评估AI解读
- 保留三阶段UI（选量表→选项卡片答题→完成）
- 代码计算量表得分和分级（非LLM判断）
- 答题完成后LLM流式生成评估解读
- PHQ-9第9题（自杀念头）得分>0时强烈建议就医+危机干预热线
- 右侧面板展示解读+得分摘要

#### I. 用药审查AI辅助
- LLM驱动对话收集用药信息
- 结构化审查报告：用药汇总+潜在相互作用+Beers提醒+剂量建议+就医建议
- 醒目标注"AI辅助审查仅供参考"

#### J. 医疗安全后处理
- 创建`src/lib/security-postprocess.ts`
- 确定性诊断拦截：替换"确诊为""你得了XX病"等为可能性表述
- 免责声明自动附加
- 自杀风险提示：危机干预热线
- 高风险症状二次检查

#### K. 会话localStorage持久化
- 所有store修改操作自动持久化
- 初始化时从localStorage恢复
- try-catch防护，损坏数据自动清除
- 消息过多自动截断（最近50条/会话）

### 2.2 不做什么（二阶段及以后）
- 二阶段全栈架构（FastAPI/AgentScope/PostgreSQL/Qdrant）
- 账号系统与健康画像后端持久化
- PDF/DOCX真实导出（Markdown文本导出后续再做）
- MinerU文档真实解析（文件上传仅做基础选择+标签展示）
- 技能管理真实上传/执行
- DDI/Beers真实规则引擎（LLM辅助审查+明确标注仅供参考）
- CGA量表真实结构化计分报告（LLM柔性解读+代码基础计分）
- Embedding/Rerank模型接入（RAG知识库，全栈阶段）

## 3. 验收标准

- [ ] `.env.local`存在于apps/mvp/，所有变量NEXT_PUBLIC_前缀适配完成
- [ ] `.env.example`模板创建完成
- [ ] `src/data/mock/`目录完全删除，全局无mock导入
- [ ] CGA量表迁移到`src/data/scales.ts`，技能列表迁移到`src/data/skills.ts`
- [ ] `src/services/`目录结构完整：api-client/llm/voice/search各模块
- [ ] API Client支持超时、重试、主备降级、AbortController
- [ ] 普通聊天：输入文本可获得LLM流式打字机回复，末尾有免责声明
- [ ] 停止生成按钮可中断流式输出
- [ ] 重新生成按钮可重新回复
- [ ] 复制按钮可复制消息内容
- [ ] 输入"胸痛"等高危词先显示红色紧急就医卡片
- [ ] ASR语音：点击麦克风→录音→停止→识别文本填入输入框
- [ ] TTS朗读：点击播放按钮可听到冰糖音色语音播放，可暂停
- [ ] 联网搜索：含"搜索"关键词时显示搜索结果卡片，有角标引用
- [ ] 五大处方：点击后AI自然对话收集信息→流式生成处方→右侧面板展示
- [ ] CGA评估：选量表→答题→提交→LLM流式生成解读→右侧面板展示
- [ ] 用药审查：输入药物→LLM生成结构化审查建议，有"仅供参考"提示
- [ ] 医疗安全：AI回复无确定性诊断用语，均带免责声明；自杀相关内容有危机热线
- [ ] 会话持久化：刷新页面后会话和消息历史恢复
- [ ] 患者/医生模式切换正常，主色差异化（患者#0EA5E9/医生#2563EB）
- [ ] 老年模式：基础字号≥18px（老年模式20px），按钮≥48px，二次确认
- [ ] 侧边栏完全折叠仅留展开+新建按钮并排
- [ ] 右侧面板默认480px（min360/max640），内容可编辑
- [ ] `npm run lint`：0错误0警告
- [ ] `npm run build`：Next.js静态导出成功
- [ ] `npm run dev`：http://localhost:3000可访问，核心功能端到端可用
- [ ] Playwright自动化测试核心路径PASS≥20项
- [ ] 用户手动测试通过（AGENTS.md步骤8d）
- [ ] 无铁律违反（确定性诊断/硬编码配置/适老化回退/吞错误）

## 4. 执行步骤

| 步骤 | 描述 | 预计产出 | 验收点 |
|------|------|---------|--------|
| 1 | 搬运.env.local到apps/mvp/.env.local，适配NEXT_PUBLIC_前缀；更新config.ts Zod校验；创建.env.example | 环境变量配置完成 | TR-1.1~TR-1.4 |
| 2 | 迁移CGA量表到src/data/scales.ts，技能列表到src/data/skills.ts；删除其余mock文件和mock目录；清理所有组件中的mock导入和setTimeout模拟 | Mock清理完成 | TR-1.2, TR-1.5 |
| 3 | 搭建services/api-client.ts（超时/重试/错误分类/Trace ID/AbortController） | API Client基类 | TR-2.1~TR-2.2 |
| 4 | 实现services/llm/client.ts（SSE解析/主备降级/system prompt构建） | LLM流式客户端 | TR-2.3 |
| 5 | 修改ChatArea.tsx doSend接入真实LLM流式对话：消息历史构建/流式增量渲染/停止/重发/复制/高风险卡片 | 普通对话真实可用 | TR-3.1~TR-3.7 |
| 6 | 实现services/voice/asr.ts + hooks/useAudioRecorder.ts + ChatInput麦克风按钮集成 | ASR语音输入可用 | TR-4.1~TR-4.6 |
| 7 | 实现services/voice/tts.ts + hooks/useAudioPlayer.ts + 朗读按钮集成 | TTS语音朗读可用 | TR-5.1~TR-5.5 |
| 8 | 实现services/search/search-client.ts + 搜索触发逻辑+结果展示 | 联网搜索可用 | TR-6.1~TR-6.3 |
| 9 | 修改五大处方流程：LLM驱动对话收集信息→[生成处方]标记→流式生成报告到右侧面板 | 五大处方真实生成 | TR-7.1~TR-7.6 |
| 10 | 修改CGA流程：代码计分→LLM流式解读→右侧面板展示+自杀风险提示 | CGA AI解读可用 | TR-8.1~TR-8.5 |
| 11 | 修改用药审查流程：LLM驱动对话→结构化审查报告+仅供参考提示 | 用药审查AI辅助 | TR-9.1~TR-9.3 |
| 12 | 创建lib/security-postprocess.ts：确定性诊断拦截+免责声明附加+自杀热线提示，集成到所有LLM onDone回调 | 医疗安全后处理 | TR-10.1~TR-10.5 |
| 13 | 修改chatStore：localStorage持久化+try-catch防护+自动截断+会话标题更新 | 会话持久化 | TR-11.1~TR-11.4 |
| 14 | 运行npm run lint修复所有错误警告 | Lint通过 | TR-12.1 |
| 15 | 运行npm run build确保静态导出成功 | Build通过 | TR-12.2 |
| 16 | 启动dev server，端到端手动验证所有核心功能 | 功能验证 | TR-12.4 |
| 17 | 适老化回归检查（字体/按钮/对比度/二次确认） | 适老化不回退 | TR-12.5 |
| 18 | Playwright自动化测试覆盖核心路径 | 自动化测试 | TR-12.3 |
| 19 | Git提交（每个小步conventional commit） | 版本提交 | - |
| 20 | 启动dev server供用户手动测试，记录后台日志，根据反馈修复 | 用户测试 | AGENTS.md 8a-8f |

## 5. 依赖和前置条件

- 0001已完成（前端UI壳子，用户手动测试通过）
- Node.js ≥ 18.18
- `/Users/qizs/conclusion/gerclaw/.env.local`中API Key均有效且额度充足
- Mimo ASR/TTS API支持浏览器端CORS跨域调用
- 主模型（qwen3.7-plus OpenAI兼容协议）支持流式输出和Markdown
- Vercel AI SDK已安装，但优先使用原生fetch+ReadableStream手写SSE解析（兼容性更好）
- 无需新增npm依赖

## 6. 决策日志

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-07-06 | 0002合并多个长期规划模块（0003~0008+0011~0013）为一个端到端真实接入计划 | MVP需要端到端可用的核心闭环，拆分过细无法验证整体流程 |
| 2026-07-06 | 优先使用原生fetch+ReadableStream手写SSE解析，而非Vercel AI SDK | 非官方OpenAI端点（阿里云DashScope/Mimo/字节豆包）兼容性更可控 |
| 2026-07-06 | ASR先做非流式（stream:false），TTS做流式PCM16 | 降低复杂度，ASR非流式已可用，TTS流式对体验关键 |
| 2026-07-06 | 联网搜索MVP阶段简化为关键词触发（"搜索"/"查一下"/"最新"），不做LLM tool use | MVP快速验证，tool use后续迭代增强 |
| 2026-07-06 | CGA量表计分由代码计算（确定性逻辑），LLM仅负责解读和建议 | 符合"状态机骨架+LLM柔性层"架构（ADR-005），分数准确不依赖LLM |
| 2026-07-06 | 环境变量从/Users/qizs/conclusion/gerclaw/.env.local搬运，变量名映射为config.ts中定义的NEXT_PUBLIC_*格式 | 用户指定该文件已配置好所有环境变量 |

## 7. 假设和风险

| 假设 | 如果不成立的影响 | 应对措施 |
|------|----------------|---------|
| Mimo ASR/TTS API支持CORS跨域 | 浏览器端无法直接调用 | 使用CORS代理临时解决，或提示用户二阶段走后端代理 |
| 主模型qwen3.7-plus支持OpenAI SSE流式格式 | 流式解析失败 | 手写SSE解析增加容错，降级到backup1 |
| TTS PCM16 24kHz mono在Web Audio API可正常播放 | 音频播放卡顿/无声 | 增加缓冲策略，降级为先完整接收再播放 |
| API Key额度充足 | 调用失败返回429/402 | 主备降级，提示用户检查额度 |
| MediaRecorder在目标浏览器可用 | 录音失败 | 提示用户使用Chrome/Edge最新版 |

## 8. 进度记录

| 日期 | 进展 | 状态 |
|------|------|------|
| 2026-07-06 | 创建执行计划，待开始执行 | 🚧待开始 |

## 9. 验收清单核对

| 验收标准 | 状态 | 说明 |
|---------|------|------|
| .env.local配置完成 | ⬜ | - |
| .env.example创建 | ⬜ | - |
| src/data/mock/目录删除 | ⬜ | - |
| CGA量表/技能数据迁移 | ⬜ | - |
| services/基础设施搭建 | ⬜ | - |
| LLM流式对话可用 | ⬜ | - |
| ASR语音输入可用 | ⬜ | - |
| TTS语音朗读可用 | ⬜ | - |
| 联网搜索可用 | ⬜ | - |
| 五大处方真实生成 | ⬜ | - |
| CGA AI解读可用 | ⬜ | - |
| 用药审查AI辅助 | ⬜ | - |
| 医疗安全后处理 | ⬜ | - |
| localStorage持久化 | ⬜ | - |
| npm run lint通过 | ⬜ | - |
| npm run build成功 | ⬜ | - |
| 适老化不回退 | ⬜ | - |
| Playwright自动化测试 | ⬜ | - |
| 用户手动测试通过 | ⬜ | - |

完成后：审阅者将本文件移入`../completed/`目录，并回写`docs/长期规划.md`进度总览表。
