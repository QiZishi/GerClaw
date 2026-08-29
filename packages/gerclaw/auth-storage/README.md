# @gerclaw/auth-storage

GerClaw 账号持久化 Service。它只负责账号记录的 durable storage-domain、一次性迁移和生命周期清理；密码哈希策略、Cookie 会话和游客会话仍由 `@gerclaw/auth` 负责。

## 复用与接口

- 复用 DSH `storage`、`storage-domain`、JSON/SQLite backend 和 credentials seam。
- 提供 `GerclawAccountStore`，消费方通过 Cordis `inject` 使用 `list`、`findByUsername`、`findById` 和 `put`。
- domain 名为 `gerclaw_auth_accounts`，全局值保存版本化 migration marker。

## 迁移与恢复

首次加载按“已有 domain → `GERCLAW_AUTH_ACCOUNTS` → `accounts.json` → 空库”顺序执行。旧 credential 和旧文件始终只读保留；成功后 marker 防止重复迁移。账号记录写入当前 Gateway 的 DSH storage，重启后由 storage-domain 恢复。

## 生命周期与改进

domain handle、写入队列和迁移只属于该插件；`ctx.effect()` 在卸载时关闭 domain。插件禁用时，认证消费方因依赖消失进入 Cordis `PENDING`，重新启用后自动恢复。更换后端只调整 Profile 的 backend 组合，不修改消费方。

## 已知限制

认证服务保留短期进程内 session Map；重启会使 Cookie 会话失效，但持久账号和密码哈希不会丢失。此包不保存医疗数据，也不改变医生与患者的功能边界。
