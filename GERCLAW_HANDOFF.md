# GerClaw 项目交接文档

- 更新日期：2026-08-25
- 工作目录：`/Users/qizs/conclusion/gerclaw/gerclaw-harness`
- 当前分支：`codex/cordis-remediation`

## 1. 交接目标

本文记录当前代码、真实运行验证和未完成工作，供后续智能体从现有实现继续开发。后续工作必须遵守根目录 `AGENTS.md`：优先复用 DSH 与合规第三方插件，所有插件启停、依赖等待、级联卸载和恢复必须走 Cordis Loader、Profile overlay 与 HMR；禁止新增平行插件管理、会话、事件、依赖注入或生命周期实现。

代码开发继续采用 Ponytail 的工程原则：先复现真实问题并定位根因，优先使用平台原生能力，保持最小必要改动，只增加保护已观察故障或明确产品要求的测试。

## 2. 不得回退的产品基线

- 品牌只显示 `GerClaw`、`老年慢病智慧诊疗助手` 和根目录 `icon.png`，前端不得出现 `DeepSeek`、`DeepSeek Harness` 或 `DSH` 品牌文字。
- 保留淡蓝色主题、完整左上品牌布局、当前产品化登录页用途说明和三项核心亮点文案。
- 首页是原生对话工作台，输入框固定在底部；模型 Markdown 自动渲染，医疗结果使用结构化卡片。
- 五大处方必须在对话中完成：用户通过文字、语音或文件提供资料，系统自动匹配输入；缺失信息时每轮只问一个问题，最多五轮；资料完整后生成药物、运动、营养、心理和康复五章，执行格式校验并只显示一张最终结果卡。禁止恢复独立处方表单。
- 医生和患者拥有完全相同的功能，身份只影响称呼；账号只用于数据隔离。
- 用户可以看到模型明确输出的分析依据、证据和步骤摘要，但不得暴露平台隐藏推理、密钥、内部地址、调用参数、堆栈或插件结构。
- 语音只是底部对话输入和最终回复朗读能力，不得新增独立语音页面或导航。

## 3. 已完成工作

| 范围 | 当前事实 | 主要位置或证据 |
|---|---|---|
| DSH 底座与本地 Git | 已基于 `dsh-v0.1.1-rc.2` 建立独立仓库，并形成 Cordis 整改阶段提交 | `git log`；当前分支 `codex/cordis-remediation` |
| 本地知识库 | `knowledge-base` 已复制 437 个文件，源目标相对路径和 SHA-256 零差异 | `knowledge-base/`；`packages/gerclaw/local-rag/tests/shared-index.spec.ts` |
| GerClaw 品牌与基础布局 | 品牌、图标、淡蓝主题、底部输入框、登录页亮点文案和侧栏区块顺序已实现 | `packages/gerclaw/client-ui/src/client/`；提交 `3aa5b30` |
| System Prompt | GerClaw 专属 System Prompt 已接入，默认开发者提示语在正式 Profile 中停用 | `packages/gerclaw/system-prompt/`；`packages/gerclaw/profile-bundle/cordis.patch.yml` |
| 四项健康技能 | 随访问卷、风险评估、健康教育和用药提醒已进入 GerClaw preset | `apps/cli/config/agent-presets/gerclaw/` |
| Plan 与 Goal | 使用 DSH 原生 Plan、Goal、审批和 session 状态，不维护平行实现 | `apps/cli/config/agent-presets/gerclaw/`；`packages/gerclaw/profile-bundle/cordis.patch.yml` |
| 五大处方核心流程 | 对话式 intake、单轮单问、五轮上限、文件资料提取、五章 schema 校验和确定性用药附录已经实现 | `packages/gerclaw/prescription/`；`packages/gerclaw/client/src/index.ts` |
| 医疗领域逻辑 | 五种 CGA、用药相互作用与阈值、健康档案、慢病记录、风险提醒、陪伴和医学证据包已有实现及局部确定性测试 | `packages/gerclaw/cga/`、`medication-review/`、`health-profile/`、`chronic-care/`、`risk-alert/`、`companion/`、`medical-evidence*` |
| Cordis 医疗服务 | `GerclawTaskRuntime`、`HealthRepository`、`GerclawArtifactService` 服务边界、提供方、消费方和业务 projection 已进入真实 Profile | `packages/gerclaw/task-runtime*/`、`health-repository*/`、`artifact*/`、`client/src/projection.ts` |
| Qianwen 语音后端 | `SpeechProvider`、Qianwen provider 和基于 `dsh-talk@0.1.3` 的消费方已拆分；只使用 Qianwen，SiliconFlow 未进入语音路径 | `packages/gerclaw/speech*/`、`voice/`；提交 `7fca5f0`、`060005c` |
| 语音协议与生命周期 | ASR/TTS 协议、60 秒限制、PCM 转换、尾部刷新、取消、中断和资源清理已有聚焦测试；Provider 缺失时 pending、恢复后激活已有 Loader 测试 | `packages/gerclaw/speech-qianwen/tests/`；`packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts` |
| RAG 架构代码 | 已拆成一份共享只读基础知识库、每账号私有资料库和注入式 RAG 消费者；复用 DSH storage、`dsh-library`、MinerU 与 SiliconFlow embedding/rerank | `packages/gerclaw/library-dsh*/`、`shared-knowledge/`、`local-rag/` |
| 账号隔离拓扑 | 每个持久账号和游客使用独立 DSH Host；认证、Host runtime 与本地提供方已按 Cordis 服务组合 | `packages/gerclaw/tenant-*/`、`auth*/`；提交 `dbf3d78`、`ba7d3f8` |
| 真实医生路径 | 医生账号五大处方专项和完整真实 Playwright 主流程已通过 | `packages/gerclaw/client/tests/gerclaw-real.e2e.ts` 的实际运行结果 |
| 真实患者路径 | 患者账号完整真实 Playwright 主流程已通过，使用同一主模型，无备用模型命中 | 同上 |

当前已形成的主要整改提交：`7f40759`、`dbf3d78`、`ba7d3f8`、`7fca5f0`、`bcd286d`、`e9b101d`、`2038f82`、`3aa5b30`、`b94886d`、`060005c`、`0a455df`。

## 4. 未完成工作与阻塞

| 优先级 | 范围 | 未完成事实 | 完成条件 |
|---:|---|---|---|
| P0 | 新会话冷启动 | 游客真实路径在第一条消息前被“选择工作区”阻断，输入区处于 inert 状态 | 新会话自动创建并打开，用户无需选择内部存储空间；刷新、重连和 Host 重启后仍可恢复 |
| P0 | 语音输入可见性 | `TalkMicButton` 已实现并注册，但截图和游客冷启动中没有渲染麦克风及音频上传按钮 | 登录或游客进入空白新会话后，输入区右下方发送按钮左侧持续显示“开始语音输入”和“上传音频进行识别” |
| P0 | 左栏医疗入口 | 当前存在与“新会话”重复的“健康对话”图标；展开态把六项功能压成无文字的小图标横排 | 删除“健康对话”；五大处方、综合量表、用药核对、健康档案、更多按顺序纵向排列并显示中文标签，折叠态保留图标、tooltip 和 `aria-label` |
| P0 | 网页产品语义 | 页面仍出现“工作区”“选择一个工作区开始”等开发者式概念 | 用户可见 DOM、metadata、提示和错误中不出现“工作区”；每个会话自动绑定账号内独立 DSH workspace，内部服务继续保留 |
| P0 | 游客 E2E | 游客完整真实路径因冷启动问题失败 | 修复后先重跑游客失败场景，再跑医生、患者、游客完整矩阵；结束后清理游客目录与进程 |
| P0 | 真实语音链路 | 协议和 Loader 测试已通过，但尚无可见麦克风条件下的真实浏览器 ASR→自动发送→模型回复→TTS 朗读证据 | Playwright 与 in-app Browser 均真实完成录音、上传、临时/最终转写、自动发送、朗读、停止、重播和新输入打断，无 fallback |
| P1 | 共享 RAG | 代码和确定性清单测试存在，但真实共享索引 READY、SiliconFlow embedding/rerank、私有资料合并和来源回溯尚未形成最终证据 | 437 份基础资料均进入单一共享只读索引；医生、患者、游客可检索基础资料但只能检索各自私有资料；引用可定位原文 |
| P1 | 跨账号攻击测试 | 独立 Host 已实现，但 session、文件、资料、产物、下载和 WebSocket 标识互换尚未全量验证 | 两个持久账号交换全部标识均返回拒绝或不存在，不能读取内容或推断他人数据 |
| P1 | 产物全链路 | 七格式代码和右栏接入存在，尚未完成三身份的生成、恢复、预览、下载和隔离矩阵 | Markdown、HTML、DOCX、PDF、PNG、JPG、JSON 来自同一结果，进入当前账号 DSH workspace/file reference 并由 Better Sidebar 预览 |
| P1 | Loader 全链路 | 部分服务链有 hot-plug 测试，尚未逐条证明所有可替换依赖的 pending、级联卸载、恢复、失败更新回滚和无残留 | 运行真实 Profile/Loader 组合测试并记录 active→pending/unloaded→active 与资源清理证据 |
| P1 | in-app Browser | 尚未开始三身份人工路径复验 | 仅在 Playwright 全矩阵通过后，使用 Browser 技能按医生、患者、游客重新执行完整路径 |
| P2 | 最终工程检查 | 尚未执行完成态的 Loader dump、卸载残留、全量 typecheck、lint、build、docs 和 `check:all` | 所有检查真实通过，失败不得以降级或备用服务视为成功 |
| P2 | 文档收口 | 根 README 和若干插件 README 的完成态描述早于真实验收，部分新包缺 README | 双重验收后按实际实现修订；补齐 `artifact*`、`document-parser*`、`health-repository*`、`medical-evidence-public`、`task-runtime*` 等包文档 |
| P2 | Git 收口 | 当前工作区仍有大量未提交的已跟踪修改和未跟踪正式源码 | 按 UI 冷启动、RAG、任务/产物、验收、文档形成独立可回滚提交；不得混入运行产物 |

## 5. 截图问题的根因与锁定整改

### 5.1 输入区必须显示语音按钮

`@gerclaw/voice` 已在 `packages/gerclaw/voice/src/client/index.ts` 注册 DSH 原生 `conversation.input.left` 槽，麦克风和音频上传按钮位于 `TalkMicButton.tsx`。DSH 原生对话组件只有在当前会话 zone 已建立时才渲染该槽；冷启动没有自动创建并打开会话，因此语音按钮与资料上传按钮同时消失。

整改必须修复原生会话初始化，不得把按钮绝对定位到页面或另建输入框。删除 `packages/gerclaw/client-ui/src/client/index.ts` 中无来源的 `sessionStorage` 启动门槛，使用 DSH `sessions.create({ workspaceId })` 与 `sessions.open(sessionId)` 建立当前会话。按钮位置为发送按钮相邻左侧；麦克风、音频上传、发送三个控件应始终处于同一输入区。

### 5.2 用户界面删除“工作区”概念

DSH workspace 仍是文件、产物、会话 cwd 和账号隔离的内部能力，不能删除其服务或自行替代。GerClaw 网页端不允许用户选择、添加、删除或理解 workspace；每次新建会话自动拥有账号内独立的内部 workspace，并由 session 绑定。

GerClaw Profile 应禁用纯用户界面的 workspace picker/browser，同时保留 workspace registry、storage 和 session binding。用户可见文案统一使用“当前对话资料”或“本次健康对话资料”；`健康工作区尚未就绪` 改为 `健康对话尚未就绪`。DOM 中不得出现“工作区”“选择工作区”“添加工作区”。

### 5.3 左栏医疗功能改为纵向有标签入口

删除 `packages/gerclaw/client-ui/src/client/MedicalNavigation.tsx` 的 `chat` entry 及对应点击分支。“新会话”、历史会话和中栏对话已经覆盖健康对话入口。

展开侧栏按 `五大处方 → 综合量表 → 用药核对 → 健康档案 → 更多` 纵向排列，每项使用足够高度的圆角按钮、图标和常显中文标签；折叠侧栏只显示图标，但必须保留中文 tooltip、键盘焦点和 `aria-label`。整体顺序保持 `新会话 → GerClaw 医疗功能 → 搜索/历史会话 → 底部设置`。

## 6. 后续智能体执行顺序

1. 先保护当前品牌、登录页和五大处方基线，检查工作区 diff，不清理用户文件或历史账号数据。
2. 使用 DSH 原生 session/workspace 服务修复冷启动，确保新建会话自动绑定内部 workspace，并从产品界面移除 workspace 概念。
3. 让 `conversation.input.left` 在空白新会话建立后正常挂载，完成真实 Qianwen ASR/TTS 浏览器链路。
4. 删除冗余“健康对话”入口，把其余医疗入口改为带中文标签的纵向按钮；补桌面、平板、手机和折叠态断言。
5. 重跑游客失败场景，然后重跑医生、患者、游客 Playwright 完整矩阵。
6. 完成真实共享 RAG、跨账号标识交换、七种产物和完整 Loader 热插拔验证。
7. Playwright 全通过后读取并使用 in-app Browser 技能，按三种身份重新执行完整用户路径；浏览器发现的问题必须补对应回归测试。
8. 完成配置树、卸载残留、类型、lint、build、docs 与 `check:all`，清理游客、测试进程和临时产物，再按阶段提交。

## 7. 必须保留或清理的运行数据

- 必须保留持久测试账号 `gc_doctor_test_20260823` 与 `gc_patient_test_20260823`；密码不得写入仓库、日志、截图、报告或本文件。
- `.env` 只能读取变量名和服务配置，禁止打印、修改密钥或暂存。
- 不得提交 `.playwright-cli/`、`dsh/`、`output/`、`.gerclaw/` 运行数据、日志、缓存、构建产物或临时账号资料。
- 游客验收结束后必须清理游客目录、会话和子进程；持久账号与历史医疗数据不得删除。
- 不配置 Git remote，不推送，不连接或同步任何远程服务器。

## 8. 下一轮关键验收断言

```ts
await expect(page.getByRole('button', { name: '开始语音输入' })).toBeVisible()
await expect(page.getByRole('button', { name: '上传音频进行识别' })).toBeVisible()
await expect(page.getByRole('button', { name: '发送消息' })).toBeVisible()
expect(await page.getByRole('button', { name: '健康对话', exact: true }).count()).toBe(0)
expect(await page.locator('body').innerText()).not.toMatch(/工作区|选择工作区|添加工作区/)
```

五个医疗按钮必须可见且按纵向坐标递增；展开态显示中文标签，折叠态 tooltip 和 `aria-label` 保持可用。修复后必须先验证游客冷启动，再执行完整 Playwright 矩阵，不能只验证 DOM 存在。

## 9. Git 与验证注意事项

当前工作区不是干净状态：除已跟踪修改外，`apps/cli/config/agent-presets/gerclaw/`、`packages/gerclaw/auth-storage/`、`library-dsh-runtime/`、projection 与测试文件仍未提交；旧的 `packages/gerclaw/profile-bundle/presets/gerclaw/agent.cordis.yml` 删除与新 preset 迁移必须作为同一变更核对。先用 `git diff --check` 和密钥/产物检查确认当前边界，再提交阶段成果，禁止破坏性 reset 或覆盖历史。

最终至少运行：

```bash
pnpm gerclaw:dump-config
pnpm typecheck
pnpm lint
pnpm build
pnpm docs:check
pnpm check:all
```

这些命令只能在真实 Playwright 与 in-app Browser 验收完成后作为最终工程门槛；它们不能替代真实产品路径。
