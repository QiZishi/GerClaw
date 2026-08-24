# GerClaw 隔离 Storage Domain 适配器

该正式 Cordis 插件只解决一个边界：让 DSH 原生 `DomainFacility` 在 Loader 隔离的 `storage` realm 中挂载。它不实现存储、SQLite、业务表或插件开关。

代码基于 `@deepseek-ai/dsh-storage-domain` 的 provider 结构，仅让内部 backend 生命周期 fiber 显式注入同一 realm 的 `storage`。数据语义、校验与清理由 DSH 原生 `DomainFacility` 保持一致。插件由 Profile/Loader 装配和卸载，禁止业务代码直接调用 `apply`。

验证重点是 provider 缺失时 pending、恢复后重新激活、更新失败回滚，以及卸载后 SQLite 与 domain handle 可释放。
