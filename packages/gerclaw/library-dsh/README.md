# GerClaw dsh-library Provider

本包以固定版 `dsh-library@0.1.3` 为源码底座，将账号私有资料库提供为 `gerclawLibrary` Cordis 服务；分块、embedding、混合检索和 storage-domain 由同一 isolate 内注入的 `@gerclaw/library-dsh-runtime` 承担。

它删除了不适合作为内部服务调用面的命令与 Tool 注册；用户可见 Tool 由产品侧 adapter 调用本服务，业务包不得把 Tool 当内部 API。`library-dsh` 只注入 `gerclawLibraryRuntime`，不导入或实例化 `LibraryStore`。存储、SQLite、subprocess 和领域句柄均由真实 Loader/Cordis effect 管理；每个账号 Host 的独立 storage isolate 确保资料互不相见。
