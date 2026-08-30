# GerClaw 全面收口进展

本文件是本轮执行的唯一进展记录。只有真实命令或浏览器断言退出成功的内容才标记为完成；源码存在、局部测试通过或历史截图不等于产品验收通过。

## 完成标准

医生、患者和游客的产品主路径、语音、五大处方、共享与私有医学资料、账号隔离、七种产物、原生热插拔、老年友好界面及完整工程检查全部通过。所有插件由 Cordis 和 DSH（深度求索智能体底座）原生加载器管理，不建立平行会话、存储、检索、模型或生命周期机制。

## 阶段状态

| 阶段 | 状态 | 验收与提交 |
| --- | --- | --- |
| 一：产品壳层与主对话 | 完成 | 游客 6/6、医生与患者 2/2、加载器 7/7 通过；`3ec56fd` |
| 二：语音与五大处方 | 完成 | 三身份浏览器 3/3、加载器 3/3 通过；`9b586d4` |
| 三：共享与私有医学资料 | 完成 | 三身份浏览器 4/4、故障恢复 1/1、真实加载器与外部检索 1/1 通过；`f63ce11` |
| 四：账号隔离与七种产物 | 完成 | 三身份浏览器 4/4、加载器 5/5 通过；`e815377` |
| 五：热插拔与最终收口 | 完成 | 三身份完整路径、加载器 29/29、工程门禁 48/48 通过；提交待记录 |

## 阶段一记录：产品壳层与主对话

### 已完成

- 已核对真实网关加载的预设、配置档案、组合包和 `@gerclaw/client-ui` 浏览器构建。
- 已删除页面级全文扫描、文本改写与全页 `MutationObserver`，改用原生中文本地化、插槽、会话输入和类型化错误投影。
- 已用原生会话输入承载计划、目标、随访问卷、风险评估、健康教育和用药提醒，普通用户不再看到原始命令清单。
- 已修复隔离账号首次安装失败：配置档案安装改为优先使用本地缓存、缺失时正常获取，未增加第二套安装器。
- 已修复客户端组合项未激活：删除不存在的服务依赖，补齐本地化包依赖，并按原生插槽优先级替换品牌与友好错误。
- 已确认主模型真实返回中文内容，未使用备用模型；目标创建、暂停、恢复、编辑、清除和计划审核均通过游客真实浏览器路径。
- 已把上传、语音、发送和计划入口统一为不小于 44 像素，并通过三视口、键盘焦点和双倍缩放检查。

### 复用映射

| 用户需求 | 复用能力 | GerClaw 只保留的职责 |
| --- | --- | --- |
| 对话、历史与文件归属 | DSH 原生会话、工作区与存储 | 账号作用域装配与产品化投影 |
| 计划与健康目标 | DSH 原生计划、目标、命令与会话事件 | 中文入口和健康场景提示 |
| 模型调用 | DSH 模型服务与提供方组合 | GerClaw 预设和友好失败呈现 |
| 界面组合 | DSH 客户端插槽、本地化与会话投影 | 品牌、医疗入口和结构化结果 |

### 市场盘点

- 2026-08-30 实时读取 `https://dsh.market/plugins.json`：索引生成时间为
  2026-08-29T03:37:09.804Z，共列出 5120 项，不再是方案起草时的 0 项。
- 阶段一相关候选包括 `dsh-mobile`、`dsh-i18n` 和
  `dsh-plugin-no-workspace`。它们分别重复现有响应式样式、原生本地化和底层工作区
  装配；本阶段继续复用 DSH 原生能力，不新增市场插件。

### 当前证据与阻塞

- 当前分支为 `codex/cordis-remediation`，基准提交为 `1433bdc`。
- 工作区当前包含 58 个已跟踪改动和 15 个未跟踪路径入口；这些改动按用户闭环验收后分阶段提交，不重置或建立未验收快照。
- `pnpm gerclaw:dump-config`：退出码 0，确认 GerClaw 组合包和客户端路径进入真实配置。
- `pnpm exec tsc -b packages/gerclaw/client-ui`：退出码 0。
- `pnpm exec vitest run packages/gerclaw/client/tests/gerclaw-plugins.spec.ts packages/gerclaw/client/tests/session-projection.spec.ts`：2 个测试文件、22 项测试通过。
- `GERCLAW_BASELINE_E2E=1 pnpm exec vitest --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-baseline.e2e.ts`：1 个测试文件、6 项真实浏览器测试通过，耗时 73.59 秒；覆盖登录页、桌面、平板、手机、双倍缩放、键盘焦点、44 像素触控、真实模型回复、目标全生命周期和计划审核。成功验收不生成截图，命令退出结果为浏览器证据。
- 使用独立临时网关把主模型地址指向不可连接端口后，`GERCLAW_BASELINE_E2E=1 GERCLAW_FAILURE_E2E=1 GERCLAW_E2E_BASE_URL=http://127.0.0.1:3100 pnpm exec vitest --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-baseline.e2e.ts -t '主模型连接失败'`：1 项真实浏览器测试通过，耗时 23.53 秒；确认用户消息仍在会话、仅显示可恢复中文提示、原始连接信息不泄露且输入框仍可继续输入。未配置备用模型。临时网关与游客数据已移入系统废纸篓，可恢复。
- `pnpm build`：退出码 0。
- 2026-08-30 已确认根目录安全配置存在 `GERCLAW_TEST_DOCTOR_PASSWORD` 和
  `GERCLAW_TEST_PATIENT_PASSWORD`，未记录变量值。真实网关登录仍对两个固定账号
  返回“用户名或密码不正确”；阶段一双账号浏览器用例为 2 项失败、9 项按筛选跳过，
  两项均未进入账号工作台。诊断截图为
  `output/playwright/gerclaw-stage1-doctor-diagnostic.png`，不进入 Git。
- 两个固定账号均存在于现有账号存储，账号目录和历史数据未修改；未创建新账号。
- 2026-08-30 再次使用认证服务相同的 `scrypt` 参数离线比对：两个变量均存在，
  但与对应固定账号的密码摘要均不匹配；检查过程只读，未启动网关或修改账号数据。
- 用户随后明确授权强制重置两个固定账号密码。已在 DSH 存储域的权威账号表中将
  密码重置为安全配置中的对应值，离线比对均通过；每个账号只修改 `salt` 和
  `passwordHash`，其他账号、恢复码字段、账号数量与历史数据均未变化。旧迁移来源已
  恢复原样，权威账号表备份保存在被 Git 忽略的账号运行目录。
- 账号密码阻塞已解除：医生与患者均已使用安全配置中的密码通过真实网关登录；后续
  阶段不再把账号凭据列为阻塞，也不会新建账号或重置历史数据。
- `GERCLAW_REAL_E2E=1 node --env-file=.env node_modules/vitest/vitest.mjs --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-real.e2e.ts -t '阶段一：'`：1 个测试文件、医生与患者 2 项真实浏览器测试通过，9 项按阶段筛选跳过，耗时 853.14 秒；覆盖真实登录、产品壳层、主模型回复、计划审核、目标创建／编辑／暂停／恢复／清除和四项健康能力。
- `pnpm exec vitest run packages/gerclaw/profile-bundle/tests/agent-preset-loader.spec.ts packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts`：2 个测试文件、7 项真实加载器测试通过。
- `pnpm verify-md-wrap` 与 `git diff --check`：退出码均为 0。
- 阶段一提交：`3ec56fdca715413a35d7b22ba6390e5158a517d8`，提交信息为
  `fix(web): stabilize GerClaw product shell`。

## 阶段二记录：语音与五大处方

### 当前任务

- 重新检索 DSH 市场的语音、录音、转写、朗读和处方候选，不新增重复插件。
- 盘点现有 `SpeechProvider`、通义千问提供方、底部麦克风、通用上传入口和五大处方多轮状态，删除旁路实现。
- 修复真实链路根因后运行局部测试、真实加载器启停测试和医生、患者、游客真实网关验收。

### 输入条件

- 两个固定账号密码已与根目录安全配置一致，真实登录已通过。
- 阶段一提交已形成；后续改动继续保留在工作区并按阶段归属提交。

### 复用与市场盘点

- 实时检索 `https://dsh.market/` 的语音、转写、朗读和处方关键词；页面仍显示收录
  0 个插件，没有可采用的市场候选，本阶段不新增插件。
- 继续复用现有 `SpeechProvider`、通义千问提供方、底部麦克风、通用上传入口、
  DSH 原生会话投影和子智能体；GerClaw 只保留语音产品交互与五大处方领域规则。

### 已完成与证据

- 已修复录音和音频文件最终转写的提交时序：在同一个 DSH 原生输入实例中同步写入并发送，避免跨帧切换会话输入实例。
- 已补齐音频文件取消和插件卸载期间的连接清理，取消不会留下永久等待的转写承诺。
- 已将五大处方收集状态改为可恢复会话投影；仍保持每轮一个问题、最多五轮和单张五章结果卡。
- `pnpm exec vitest run packages/gerclaw/speech-qianwen/tests/qianwen.spec.ts packages/gerclaw/speech-qianwen/tests/realtime-protocol.spec.ts packages/gerclaw/voice/tests/interaction.spec.ts packages/gerclaw/client/tests/gerclaw-plugins.spec.ts packages/gerclaw/client/tests/session-projection.spec.ts`：5 个测试文件、34 项测试通过。
- `pnpm exec vitest run packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts -t 'speech|voice'`：3 项真实加载器测试通过，3 项按筛选跳过；覆盖提供方等待、运行中卸载、资源释放和恢复。
- `pnpm exec tsc -b packages/gerclaw/speech-qianwen packages/gerclaw/voice packages/gerclaw/prescription packages/gerclaw/client`：退出码 0。
- 首次三身份浏览器运行在逐字转写断言处 3 项失败；录音均已完成最终转写。将断言收敛为固定音频的稳定完整语义片段后，仍要求该片段真实出现在用户消息中。
- 医生阶段二真实浏览器用例 1 项通过，耗时 257.18 秒；患者与游客 2 项通过，耗时 548.46 秒。三身份均覆盖浏览器录音、临时与最终转写、自动发送、音频上传、朗读、停止、重播、输入打断、录音取消和五章处方结果卡。
- `pnpm gerclaw:dump-config` 与 `pnpm build`：退出码均为 0。
- 阶段二提交：`9b586d4fd1ed406187dfb99388d44c9cfbcefea1`，提交信息为
  `fix(health): complete voice and prescription flow`。

## 阶段三记录：共享与私有医学资料

### 当前任务

- 重新检索 DSH 市场的资料库、文档解析、向量嵌入和重排序候选，不新增重复插件。
- 复用底座资料库、现有文档解析和硅基流动服务，删除重复检索运行时与跨包具体提供方依赖。
- 验证 437 份共享资料、账号私有上传、合并检索、原文定位、失败恢复和跨账号不可串用。

### 输入条件

- 阶段二提交已形成，真实网关仍可用；两个固定账号的安全凭据继续有效。
- 共享索引只在确认当前索引可重建且验收成功后清理旧版本，不删除账号资料。

### 复用与市场盘点

- 2026-08-30 在阶段三开发前重新检索 DSH Market 的资料库、检索增强生成、向量嵌入、
  重排序和 MinerU（文档解析）候选；当前页面显示收录 0 个插件，因此不新增市场插件。
- 继续复用现有 `dsh-library`、文档解析、硅基流动嵌入与重排序服务。GerClaw 仅保留
  共享医学语料装配、账号作用域和来源投影，不建立第二套资料库或生命周期机制。

### 已完成与当前证据

- 已确认基础医学语料为 437 份，并由一个共享只读索引装配；账号上传资料仍进入对应
  账号的私有存储域。
- 已把 `dsh-library` 的具体存储内核收敛到唯一 Cordis 服务提供方；消费方只依赖服务
  接口，未跨包实例化具体提供方。
- 已修复租户进程启动竞态：不再以端口可连接或启动文本作为就绪条件，只有原生
  `/api/host.describe` 接口真实返回成功后才向浏览器开放租户网关，避免启动期接口
  偶发返回 404。
- 已将医学资料界面注册放入原生远程服务依赖注入回调，消除客户端在远程服务尚未
  激活时直接取值导致的加载失败。
- `pnpm exec vitest run packages/gerclaw/local-rag/tests/loader-invariant.spec.ts packages/gerclaw/local-rag/tests/real-rag.spec.ts`：加载器约束 1 项通过，真实外部服务项按开关跳过。
- `GERCLAW_REAL_RAG=1 node --env-file=.env node_modules/vitest/vitest.mjs run packages/gerclaw/local-rag/tests/real-rag.spec.ts`：1 项真实外部检索与加载器测试通过，耗时 20.72 秒；覆盖 437 份共享索引就绪、共享检索、账号私有资料不可串用、运行中禁用后等待和恢复后重新激活。
- 最终复验同一真实外部检索与加载器测试再次通过，耗时 19.57 秒；加载器约束测试
  1 项通过。
- `pnpm exec tsc -b packages/gerclaw/library-dsh-runtime packages/gerclaw/library-dsh packages/gerclaw/local-rag packages/gerclaw/rag packages/gerclaw/medical-evidence-public`：退出码 0。
- `GERCLAW_REAL_E2E=1 node --env-file=.env node_modules/vitest/vitest.mjs --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-real.e2e.ts -t '阶段三：'`：1 个测试文件、4 项真实浏览器测试通过，14 项按阶段筛选跳过，耗时 60.74 秒；覆盖医生、患者、游客共享检索、私有上传、可打开来源回溯，以及医生私有资料不会出现在患者检索结果中。
- 使用真实 GerClaw 主网关和临时外部服务故障注入运行“医学资料服务失败”浏览器
  用例：1 项通过，17 项按筛选跳过，耗时 8.77 秒；确认只显示可恢复中文提示，
  不伪造结果、不泄露提供方和底层网络错误。临时故障注入文件与运行目录已移入系统
  废纸篓，可恢复，未进入仓库。
- `pnpm gerclaw:dump-config`、相关包类型检查、21 项客户端测试、`pnpm build` 和
  `git diff --check`：退出码均为 0。
- 当前阻塞：无。阶段三真实验收已通过，正在提交本阶段路径。
- 阶段三提交：`f63ce11726c05dd884071b6d15750708c436d7d0`，提交信息为
  `fix(rag): complete shared and private retrieval`。

### 下一步

阶段四首个执行动作：盘点现有账号隔离、产物服务、下载与网页套接字边界，将需求
映射到已有 DSH 会话、存储和 GerClaw 产物服务，再运行双账号标识交换与七种产物的
一致性验证。

## 阶段四记录：账号隔离与七种产物

### 复用与市场盘点

- 2026-08-30 在开发前重新检索 DSH Market 的账号隔离、产物、预览、下载和恢复
  候选；当前页面没有可直接采用的候选，本阶段不新增市场插件。
- 继续复用 DSH 多租户进程、原生会话与会话投影、工作区、文件和存储能力，以及
  现有 `GerclawArtifactService`。GerClaw 只补齐账号作用域、恢复和友好错误语义，
  未建立第二套会话、存储、文件或产物机制。

### 已完成与证据

- 两个固定账号已使用安全配置中的密码通过真实浏览器登录和退出；未创建新的真实
  测试账号，也未修改其他账号或历史医疗数据。
- 注册与恢复码成功路径已在隔离存储的真实加载器测试中通过：恢复码仅可使用一次，
  旧密码和已使用恢复码失效，卸载并重新加载后新密码仍有效。
- 产物和文档统一经账号宿主内的 `GerclawArtifactService` 访问；会话任务改用浏览器
  请求的全局唯一标识，并由 DSH 原生会话投影恢复，消除不同账号间任务标识碰撞。
- 双账号交换产物、文档、任务、会话和网页套接字标识时均被拒绝；对外状态、正文与
  网页套接字关闭结果和随机不存在标识完全一致，不泄露对象是否存在。
- 七种格式 `Markdown`、`HTML`、`DOCX`、`PDF`、`PNG`、`JPG`、`JSON` 来自同一
  计分任务；真实浏览器已验证七项下载、图片和 PDF 预览、浏览器下载及退出重登后的
  历史恢复。
- 游客用例验证登录期间只新增游客专用目录，退出后目录数量恢复到基线；持久账号宿主
  与历史数据保持不变。
- `pnpm exec vitest run packages/gerclaw/auth-storage/tests/loader.spec.ts packages/gerclaw/client/tests/session-projection.spec.ts packages/gerclaw/client/tests/gerclaw-plugins.spec.ts`：3 个测试文件、26 项测试通过。
- `pnpm exec vitest run packages/gerclaw/auth-storage/tests/loader.spec.ts packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts -t 'account|auth|task runtime'`：2 个测试文件、5 项真实加载器测试通过，5 项按筛选跳过。
- `GERCLAW_REAL_E2E=1 node --env-file=.env node_modules/vitest/vitest.mjs --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-real.e2e.ts -t '阶段四：'`：1 个测试文件、4 项真实浏览器测试通过，16 项按阶段筛选跳过，耗时 20.41 秒；覆盖医生、患者、游客七种产物和双账号标识交换。
- `pnpm gerclaw:dump-config`、相关包类型检查、`pnpm build` 和 `git diff --check`：退出码均为 0。
- 当前阻塞：无。阶段四真实验收已通过并形成独立提交。
- 阶段四提交：`e815377d090617dfe14f9a56b88e73ecbee02e7a`，提交信息为
  `fix(tenant): close isolation and artifact workflows`。

### 下一步

阶段五首个执行动作：重新阅读 Cordis 生命周期和组合热更新文档，盘点全部可替换
GerClaw 服务，并通过真实加载器验证依赖消失、资源释放、恢复、失败更新回退和无重复
注册，随后运行完整三身份浏览器矩阵与全部工程检查。

## 阶段五记录：热插拔与最终收口

### 复用与市场盘点

- 已重新阅读 Cordis 生命周期、组合与热更新文档，并对照 DSH 架构指南核对真实
  Loader 接入规则；未修改底座核心，也未建立平行生命周期或插件注册机制。
- 2026-08-30 在阶段五开发前再次检索 DSH Market 的生命周期、热插拔、网关、语音、
  检索和存储候选；产品页面当前显示收录 0 个插件，本阶段不新增市场插件。
- 继续复用 DSH Profile、Bundle、Loader、`ctx.effect()`、`ctx.on()` 和原生服务依赖；
  本阶段只补全现有服务的真实组合验收。

### 已完成与当前证据

- 新增一个参数化真实 Loader 矩阵，覆盖老年综合评估、用药核对、健康档案、慢病、
  陪伴、风险提醒、公开医学证据、文档解析、健康资料库、产物、五大处方、任务运行、
  租户宿主、租户存储、租户网关和客户端应用 16 个可替换服务。
- `pnpm exec vitest run packages/gerclaw/profile-bundle/tests/all-service-hotplug.spec.ts packages/gerclaw/profile-bundle/tests/hotplug.spec.ts packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts packages/gerclaw/auth-storage/tests/loader.spec.ts packages/gerclaw/local-rag/tests/loader-invariant.spec.ts packages/gerclaw/profile-bundle/tests/cordis-lab.spec.ts`：6 个测试文件、29 项真实 Loader 测试通过；逐项覆盖活动、依赖消失后的等待或卸载、消费方级联停止、服务移除、资源归零、恢复、失败更新回退和无重复注册，未直接调用 `apply()`。
- `pnpm gerclaw:dump-config`、`pnpm typecheck`、`pnpm lint`、`pnpm docs:check`、
  `pnpm verify-md-links`、`pnpm verify-md-wrap` 和 `git diff --check`：退出码均为 0；
  文档检查包含 64 项测试、2059 个链接和 1992 个格式检查。
- 完整浏览器文件首次运行 20 项中 17 项通过、2 项失败、1 项按环境跳过；失败根因为
  长会话虚拟化后问题卡定位不稳定。修复为类型化任务标识和当前可见问题卡定位后，
  医生、患者完整路径复跑通过，游客完整路径最终复跑 1 项通过、19 项按筛选跳过，
  耗时 806.52 秒。首次全文件成功项与三身份最终成功复跑共同闭合全部可运行路径，
  未将首次失败写成通过。
- 最终基线浏览器复验为 6 项通过、1 项按环境跳过，耗时 59.18 秒；覆盖三视口、
  键盘焦点、双倍缩放、44 像素触控目标和产品壳层。
- 已用应用内浏览器分别复验游客、医生和患者：三身份均显示品牌、五项健康入口、
  模型选择器、麦克风和上传入口，均无工作区选择泄露，并获得主模型真实回复。
- `pnpm build`：退出码 0。
- 首次全量门禁暴露 GerClaw 包未完整接入底座全局约束；按现有约束清单、类型出口和
  目录生成器完成最小接入，并删除检索聚合层重复重排序、客户端重复任务协议和租户
  网关重复鉴权路径。最终 `pnpm check:all` 为 48 项通过、0 项失败、0 项跳过，耗时
  154.54 秒；包含 266 个源码与 266 个编译后约束伴随项，重复代码检测为 0。
- 成功证据形成后，旧 `.playwright-cli/`、`dsh/` 和 `output/` 运行产物已移入
  `/Users/qizs/.Trash/gerclaw-final-cleanup-20260830-0904/`，可从系统废纸篓恢复；游客
  目录确认为空。两个固定账号及其历史医疗数据未删除。

### 收口状态

- 当前阻塞：无。两个固定账号均已使用安全配置中的密码通过登录，密码不再是阻塞项。
- 阶段五实现和验收已完成；最后动作是复查差异与敏感文件，提交
  `chore: complete GerClaw acceptance`，随后回填提交号。
