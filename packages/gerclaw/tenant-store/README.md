# @gerclaw/tenant-store

为 `dsh-multi-tenant@0.2.0-rc.3` 的 `TenantSessionStore` 服务定义提供持久化实现。所有权记录写入 DSH `storage-domain`，不保存认证密码或医疗数据；插件卸载时关闭 domain。替换存储介质时只需替换本提供方，消费方继续依赖社区定义。
