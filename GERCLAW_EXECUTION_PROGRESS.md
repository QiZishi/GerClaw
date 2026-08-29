# GerClaw 全面收口进展

本文件是本轮执行的唯一进展记录。只有真实命令或浏览器断言退出成功的内容才标记为完成；源码存在、局部测试通过或历史截图不等于产品验收通过。

## 完成标准

医生、患者和游客的产品主路径、语音、五大处方、共享与私有医学资料、账号隔离、七种产物、原生热插拔、老年友好界面及完整工程检查全部通过。所有插件由 Cordis 和 DSH（深度求索智能体底座）原生加载器管理，不建立平行会话、存储、检索、模型或生命周期机制。

## 阶段状态

| 阶段 | 状态 | 验收与提交 |
| --- | --- | --- |
| 一：产品壳层与主对话 | 进行中 | 游客 6/6、医生与患者 2/2、加载器 7/7 通过；待提交 |
| 二：语音与五大处方 | 未开始 | 待阶段一提交后开始 |
| 三：共享与私有医学资料 | 未开始 | 待阶段二提交后开始 |
| 四：账号隔离与七种产物 | 未开始 | 待阶段三提交后开始 |
| 五：热插拔与最终收口 | 未开始 | 待阶段四提交后开始 |

## 当前阶段：产品壳层与主对话

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
- `GERCLAW_REAL_E2E=1 node --env-file=.env node_modules/vitest/vitest.mjs --config vitest.e2e.config.ts run --retry=0 packages/gerclaw/client/tests/gerclaw-real.e2e.ts -t '阶段一：'`：1 个测试文件、医生与患者 2 项真实浏览器测试通过，9 项按阶段筛选跳过，耗时 853.14 秒；覆盖真实登录、产品壳层、主模型回复、计划审核、目标创建／编辑／暂停／恢复／清除和四项健康能力。
- `pnpm exec vitest run packages/gerclaw/profile-bundle/tests/agent-preset-loader.spec.ts packages/gerclaw/profile-bundle/tests/service-hotplug.spec.ts`：2 个测试文件、7 项真实加载器测试通过。
- `pnpm verify-md-wrap` 与 `git diff --check`：退出码均为 0。
- 本阶段尚无提交号；三身份浏览器和加载器门槛已满足，正在完成阶段差异与敏感文件检查。

### 下一步

首个执行动作：复核阶段一暂存差异和敏感文件，提交
`fix(web): stabilize GerClaw product shell`，记录提交号后进入阶段二。
