# @gerclaw/tenant-gateway

GerClaw 的账号入口。它只保存账号认证信息和子 Host 生命周期状态；每个
注册账号或游客由独立的真实 DSH Web Profile 子进程提供服务，使用独立
`DSH_HOME`、Workspace、Session、Storage、产物与 Memorix 数据目录。

医生与患者字段仅用于称呼偏好，不参与任何权限判断。游客退出或超时后
清除临时目录；注册账号空闲时只停止进程并保留数据。
