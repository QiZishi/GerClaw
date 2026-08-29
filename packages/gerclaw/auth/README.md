# @gerclaw/auth

GerClaw 认证 Service，基于 `dsh-login` 固定提交的 Cookie、随机会话和 scrypt 结构裁剪。已删除管理员例外、跨账号用户管理和固定 DSH API 白名单；新增自助注册、恢复码和游客。账号记录通过 `@gerclaw/auth-storage` 的 `GerclawAccountStore` 持久化，密码、恢复码和 Cookie 不写入会话日志，医生/患者字段只改变称呼。
