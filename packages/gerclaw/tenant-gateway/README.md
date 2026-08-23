# @gerclaw/tenant-gateway

## 职责

GerClaw 的认证与反向代理入口。它只保存强哈希认证信息、随机会话标识和子 Host 状态，不读取医疗内容。医生与患者仅是称呼偏好，功能和数据规则完全相同。

## 隔离、恢复与接口

每个注册账号或游客由独立真实 DSH Web Profile 子进程提供服务，使用独立 `DSH_HOME`、workspace、session、storage、产物、知识库索引与 Memorix 目录。Cookie 为 `HttpOnly`、`SameSite=Strict`；HTTP 和 WebSocket 都按当前 Cookie 代理，外部 ID 不能跨 Host 使用。

## 生命周期、改进与测试

注册 Host 空闲停止但数据保留；游客退出或超时后清除进程和临时目录。子进程、计时器和代理连接由 Cordis effect/AbortSignal 回收。新增认证方式不得扩大网关的数据可见范围。运行 GerClaw contract test，并用两个账号交换会话、文件、产物和 WebSocket 标识验证拒绝。单机首版需要外部 HTTPS 才能公网部署。
