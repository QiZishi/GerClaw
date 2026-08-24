# GerClaw dsh-library Provider

本包以固定版 `dsh-library@0.1.3` 为源码底座，保留其分块、embedding、混合检索、MMR 和 storage-domain 实现，将账号私有资料库提供为 `gerclawLibrary` Cordis 服务。

它删除了不适合作为内部服务调用面的命令与 Tool 注册；用户可见 Tool 由产品侧 adapter 调用本服务，业务包不得把 Tool 当内部 API。存储、SQLite、subprocess 均由真实 Loader 注入；领域句柄通过 `ctx.effect` 在卸载时关闭。每个账号 Host 的独立 storage isolate 确保资料互不相见。
