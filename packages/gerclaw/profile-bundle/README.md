# @gerclaw/profile-bundle

## 职责与接入

GerClaw 的正式 DSH Profile 层。`cordis.patch.yml` 替换默认系统提示语，挂载全部 GerClaw 领域插件，并保留原生 Agent、Plan、Goal、session、workspace、storage、deliverables 和相关健康技能。社区能力包括 `dsh-library@0.1.3`、`dsh-mineru@0.1.9` 与 Memorix；浏览器只由 `@gerclaw/app` 提供，不加载 DSH 开发者界面。

## 配置、数据与生命周期

配置只引用环境变量名，各账号子 Host 注入独立数据目录。Cordis Loader 统一管理插件依赖和卸载顺序，不允许业务测试手工挂载替代。

## 改进与测试

调整树结构前先确认 DSH 源码和市场插件，避免重复实现。运行 `pnpm gerclaw:dump-config` 检查真实解析树，再启动、停止和热卸载检查残留。已知限制：社区服务的可用性取决于其上游接口。
