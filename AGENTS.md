# Repository Guidelines

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

功能只有在以下条件全部满足后才算完成：已证明无法直接复用现有插件；新能力以独立插件接入 DSH；未修改所采用的原生插件；无医患权限差异；账号数据隔离有效；界面不暴露开发者功能或完整日志；关键业务结果与原 GerClaw 一致；相关测试和构建实际通过；当前阶段已形成可追溯的本地 Git 提交。
