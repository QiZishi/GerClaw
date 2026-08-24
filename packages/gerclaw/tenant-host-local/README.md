# @gerclaw/tenant-host-local

`TenantHostRuntime` 的单机提供方。它以 `dsh-multi-tenant` principal scope 为唯一实例与生命周期容器，通过 DSH `ctx.subprocess` 运行官方 `dsh plugin` 安装命令和真实账号 Web Profile；不维护 Host Map、启动 Map 或自定义插件开关。账号空闲时销毁 scope，游客 scope 销毁后删除游客目录。
