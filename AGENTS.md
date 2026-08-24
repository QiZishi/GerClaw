# Repository Guidelines

## 最高优先级：插件必须原生热插拔

**所有插件的启用、禁用、更新与卸载必须使用 DSH/Cordis 原生 Loader、`cordis.yml`/profile overlay 和 HMR 生命周期；禁止手搓任何平行的插件开关机制。** 这一要求高于下文其他实现约定。产品中的插件控制入口必须修改 Loader 管理的组合状态，由 DSH 完成依赖解析、卸载和重新加载；不得只切换业务层布尔值、维护自定义插件注册表、手动 `import`/调用插件、用条件分支隐藏功能，或依赖重启进程实现启停。

所有新插件必须把注册和外部资源绑定到 Cordis 生命周期：使用 `ctx.effect()`、`ctx.on()` 或返回 disposer 的原生注册接口，确保禁用或热重载时工具、服务、监听器、定时器、连接和 UI 投影均被完整移除，重新启用时不会重复注册或残留旧状态。每个插件必须通过真实 Loader 组合测试验证“启用后出现 → 运行中禁用后消失且资源释放 → 再启用后恢复”，不能用直接调用 `apply()` 的单元测试代替。开始相关开发前先阅读 `docs/cordis-tutorial/02-lifecycle-and-effects.zh.md` 与 `docs/cordis-tutorial/06-composition-and-hmr.zh.md`。

## Cordis 架构与能力插件自管理

- DSH 参考源码统一为 `/Users/qizs/conclusion/deepseek-harness` 当前最新标签 `dsh-v0.1.1-rc.2`（包版本 `0.1.1-rc.2`，基准提交 `b150a551b8d465e31e418e1b2eaf5e79bbb7d28e`）；每次开发前核对该仓库的 `package.json`、最新标签和 `HEAD`，参考源升级后同步更新本文件与依赖版本。
- 实施前阅读 `/Users/qizs/conclusion/deepseek-harness/Cordis架构审计与自定义插件构建指南.md`，先列出“需求 → DSH 现有能力 → GerClaw 插件服务／事件 → 组合项 → 清理与验证”；通用 Harness 能力必须复用 DSH。
- DSH 原生插件或合规第三方插件能够满足需求时，优先直接接入底座；不能整体直接使用但存在可复用代码时，以其源码为基础建立本项目维护的适配插件，删除不适用代码，改进其余代码以符合本任务和 Cordis 生命周期，不得因局部不兼容而全部重写。不得修改已直接采用的上游插件；源码改造必须保留来源、版本和许可证记录。
- 必须直接对照 `/Users/qizs/conclusion/deepseek-harness/docs/architecture.zh.md`、`/Users/qizs/conclusion/deepseek-harness/docs/cordis-primer.zh.md`、`/Users/qizs/conclusion/deepseek-harness/docs/cordis-tutorial/index.zh.md`、`/Users/qizs/conclusion/deepseek-harness/docs/cordis-api/`、`/Users/qizs/conclusion/deepseek-harness/docs/capability-seams.zh.md`、`/Users/qizs/conclusion/deepseek-harness/docs/cookbook/extension-cookbook.zh.md`、`/Users/qizs/conclusion/deepseek-harness/packages/extensions/tool-cordis/src/index.ts` 和 `/Users/qizs/conclusion/deepseek-harness/packages/extensions/cordis-host-runner/src/index.ts`；不得凭记忆猜测接口。
- 可替换能力必须完整包含服务定义、提供方和消费方；依赖用 `inject`，观察／拦截用类型化事件，资源用 effect，作用域用子上下文／`isolate`，配置用运行时 schema，并由真实 Profile／Bundle 加载。
- 禁止跨包导入具体提供方、手动实例化 Service／调用 `apply()`，以及自建注册表、事件总线、依赖注入、生命周期或绕过 DSH 服务的模型／文件／进程路径。
- 需求无现成能力时，智能体先用 `cordis_inspect_* → cordis_define → cordis_run → cordis_inspect_self → cordis_stop／cordis_undefine` 完成临时插件试制、诊断、更新和回滚；验证成功后必须重写为正式 TypeScript workspace package 并接入 Loader，不得把进程内临时定义当成交付。
- 验收必须经 `pnpm gerclaw:dump-config` 和真实 Loader 证明启用、依赖消失、清理、重新激活和版本回退；直调函数或手动创建 `Context` 的单测不是 Cordis 接入证据。

## 项目目标

本仓库用于将 `/Users/qizs/conclusion/gerclaw/gerclaw-main-codex` 的关键产品能力迁移为 DeepSeek Harness（DSH）插件，最终形成基于 DSH 底座的新版 GerClaw。业务功能的流程、计算逻辑和最终效果应与原 GerClaw 一致；通用 Harness 能力必须优先复用 DSH，不得平移 GerClaw 自建实现。

## 初始化与代码来源

首次开发先将 `/Users/qizs/conclusion/deepseek-harness` 的源码复制到本目录，保留本文件、根目录 `.env` 与 `icon.png`，排除 `.git/`、`node_modules/`、构建产物和缓存。此后只在本仓库开发，不回写两个参考仓库。

- DSH 是运行底座和插件规范来源。
- `gerclaw-main-codex` 只提供领域需求、业务逻辑与效果基准。
- 新插件放入 `packages/gerclaw/<feature>/`，遵循 DSH 的 ESM、TypeScript、Cordis 和包命名约定。
- 新前端放入独立的 GerClaw Client 插件，不复制原 GerClaw 页面或视觉实现。

## 复用优先，禁止直接手搓

写任何插件前必须依次完成：

1. 阅读 DSH 的 `AGENTS.md`、`docs/architecture.zh.md`、`docs/user/develop/basic/`、`docs/cookbook/extension-cookbook.zh.md`，以及最接近需求的现有插件与测试。
2. 盘点 DSH 仓库已有插件，确认能否直接组合或配置复用。
3. 实时浏览 [DSH Market](https://dsh.market/)，按功能关键词检索第三方插件；在任务或 PR 中记录候选、结论与理由。
4. 仅当原生和第三方插件均不能满足 GerClaw 特定业务时，才新建或基于第三方插件做必要改进。

Memory、RAG、session、文件/产物、搜索、工具执行等通用能力采用 DSH 原生插件；禁止迁移 `gerclaw_api/modules/memory`、`rag`、`agent_harness`、`runtime`、`skill` 等平行 Harness 实现。优先转写五大处方生成、CGA 量表与计分、语音对话等 GerClaw 特有能力。

## 插件边界与权限原则

- 不修改准备采用的 DSH 原生插件，只通过配置、组合和新的 GerClaw 插件接入。
- 不给复用插件增加门禁、白名单、审批链或额外限制；不要为“更安全”引入与需求无关的严苛拦截。输入格式校验和明确错误处理可以保留，但不得变成使用资格限制。
- 医生和患者拥有完全相同的功能，不设置角色分流、功能隐藏或互相授权流程。
- 账号仅用于租户隔离：每位用户只能访问自己的对话、上传文件、生成产物与历史记录，不用于限制功能。

## 前端产品规范

前端必须重新设计为简约、低学习成本的 GerClaw 工作台，并使用根目录 `icon.png` 作为品牌元素。禁止出现 DSH 原生品牌、开发者术语、终端、插件管理、运行时诊断、权限调试或完整生产日志。用户界面只展示：智能体当前步骤、关键结果、步骤耗时、总耗时、最终结果，以及结果导出/下载入口。所有定制功能同时面向医生和患者，文案不得预设用户身份。

## 配置、安全与验证

模型、ASR、TTS、embedding、rerank、搜索等服务必须读取根目录 `.env` 中现有变量；不得硬编码、输出或提交密钥。新增变量同步写入脱敏的 `.env.example`。

复制 DSH 后使用 `pnpm install` 安装依赖；改动至少运行相关 `pnpm test`、`pnpm typecheck`、`pnpm lint` 和 `pnpm build`。每个新插件需有单元测试及通过真实 DSH Loader/profile 的集成验证；领域迁移还要用原 GerClaw 的代表性输入对比关键字段、计分、流程和导出结果。

## 阶段性 Git 管理

复制 DSH 源码后，在本目录初始化独立的本地 Git 仓库，并先提交未经业务修改的 DSH 基线。后续按“底座配置、插件复用接入、单个 GerClaw 插件、账号隔离、前端、集成验证”等可独立验收的阶段推进。每个阶段必须在相关验证通过后立即检查 diff 并提交，不得将多个阶段积压到一个提交，也不得把下一阶段的半成品混入当前提交。

提交信息采用 Conventional Commits，例如 `chore: import dsh baseline`、`feat(cga): add assessment plugin`、`feat(web): add gerclaw workspace`。提交前确认 `.env`、密钥、`node_modules/`、缓存、日志和构建产物均未暂存；提交后记录实际运行的验证命令，并保持工作区无该阶段遗留改动。禁止用跳过检查、覆盖历史或破坏性重置来伪造干净状态。除非用户明确要求，不配置远端、不推送、不创建 PR。

## 完成标准

功能只有在以下条件全部满足后才算完成：插件启停已通过 DSH 原生热插拔测试；已证明无法直接复用现有插件；新能力以独立插件接入 DSH；未修改所采用的原生插件；无医患权限差异；账号数据隔离有效；界面不暴露开发者功能或完整日志；关键业务结果与原 GerClaw 一致；相关测试和构建实际通过；当前阶段已形成可追溯的本地 Git 提交。

## Conventions

本文件中的项目约束、插件边界、权限原则、前端规范和文档要求共同构成本仓库约定。下级 `AGENTS.md` 可细化局部规则，但不得放宽这些要求。

vendored packages are rescoped ([mapping](docs/rescope.md)) and `private: true`. `@deepseek-ai/cordis` is a peerDependency (+ dev) of every harness package.

## Run relevant checks locally

根据改动范围运行相关单测、`pnpm typecheck`、`pnpm lint`、`pnpm build` 和文档检查；完整交付前运行 `pnpm check:all`。

## Commands

常用产品命令为 `pnpm gerclaw` 和 `pnpm gerclaw:dump-config`。其他开发命令以根目录 `package.json` 为准。

## Pre-release stance: foundation over blast radius

项目仍处于预发布阶段。优先保持清晰的插件边界、可恢复状态和可卸载生命周期；兼容处理仅用于已存在且实际使用的入口。
