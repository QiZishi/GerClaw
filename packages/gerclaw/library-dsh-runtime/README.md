# `@gerclaw/library-dsh-runtime`

该包把固定版本 `dsh-library@0.1.3` 的 `LibraryStore` 放在一个正式 Cordis Service provider 内。`@gerclaw/library-dsh` 和共享知识库只注入 `gerclawLibraryRuntime`，不再直接打开 storage domain 或构造具体 Store。

## 生命周期

provider 通过 `storageDomain` 和 `subprocess` 注入依赖，在 `Service.init` 中打开当前 isolate 的 Library domain，并以 `ctx.effect()` 绑定 domain 与 Store 的释放。Loader 禁用 provider 时，依赖它的消费者会进入 pending，重新启用后重新获得新的 runtime 实例。

## 改进方式

可替换实现只需继承 `GerclawLibraryRuntime`，提供 `add/remove/list/search`，并在 Profile 中替换 provider；不要在消费者包导入 `LibraryStore` 或调用其他插件的 `apply()`。算法、许可证和第三方来源记录保留在本包依赖与 `NOTICE` 中。
