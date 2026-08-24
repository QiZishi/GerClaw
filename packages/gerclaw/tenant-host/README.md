# @gerclaw/tenant-host

账号 Host 生命周期的 Cordis Service Definition。认证插件只依赖 `ctx.gerclawTenantHost`，不导入本地进程实现。提供方必须启动真实 DSH Profile，并在 principal scope 卸载时回收进程、连接与游客数据。
