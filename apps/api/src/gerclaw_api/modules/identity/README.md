# Identity 模块

## 职责与边界

`identity` 提供本地患者/医生账号的凭据与可撤销会话基础能力，并由
`/api/v1/auth` 路由暴露。它负责加密账号名、scrypt 密码验证器、短期 access
token、一次性轮换 refresh token 与 PHI-free 安全事件。

该模块不是临床资质、机构目录、患者授权或紧急访问系统。`doctor` 仅是由服务端
签发并写入 JWT 的账户角色；在医生资质验证与患者授权事实源交付前，它不授予临床
scope、跨患者读取、审批权限或紧急覆盖。

## 接口与契约

FastAPI 的严格 Pydantic 请求/响应契约位于
`api/routes/auth.py`，前端只能经同源 BFF 调用。

| 接口 | 行为 | 成功结果 |
|---|---|---|
| `POST /auth/guest` | 基于受签名 visitor header 签发最小权限访客 token | 短期 bearer token |
| `POST /auth/register` | 创建 `patient` 或 `doctor` 本地账号 | access 与 refresh token |
| `POST /auth/login` | 验证凭据且避免枚举账号状态 | 新会话 token |
| `POST /auth/refresh` | 消费旧 refresh token 并原子轮换 | 新会话 token |
| `POST /auth/logout` | 幂等撤销一个 refresh token | `204` |
| `POST /auth/password` | 已认证账户修改密码并撤销全部 refresh token | `204` |
| `GET /auth/session` | 验证当前 access token，仅返回渲染账户界面所需身份 | opaque actor 与角色 |

账号名为受限 ASCII 标识符，密码长度为 12–128。所有请求都拒绝未知字段；公开认证
失败使用稳定错误码，不返回账号是否存在、密码验证细节或 refresh token 状态。

## 数据流与安全

1. 账号名以 `EncryptedText` 保存，同时以带密钥、不可逆 fingerprint 查询。
2. 密码明文只在请求内进入 versioned `scrypt-v1` 验证器，数据库仅保存 hash。
3. refresh token 仅向同源 BFF 返回；数据库只保存 token fingerprint、过期时间、撤销
   时间和轮换关系。
4. 注册、登录、刷新、登出和改密写入 `identity_security_events`。事件只含 tenant、
   opaque actor、受限 outcome、角色与 subject fingerprint，不含用户名、密码、token、
   地址或医疗内容。
5. JWT 的 role 与 scopes 均由服务端签发。Runtime 会再次投影身份；前端角色展示或
   客户端 claim 均不能提升权限。
6. `GET /auth/session` 只接受账户主体格式；同源 BFF 用它恢复页面状态，绝不向
   浏览器脚本回传 access 或 refresh token。

认证与限流异常会以安全错误终止。数据库事务提交失败时不会返回会话成功；refresh
token 重放、失效或撤销均按无效会话处理。

## 配置与依赖

依赖 `Settings` 提供的 JWT issuer/audience/secret、访客身份 secret、数据库加密键和
Redis 限流。密钥、URL、token 生命周期及协议不写入此模块代码。持久化由
`repositories/account.py` 负责；路由负责 HTTP、RateLimiter 与 JWT 签发。

## 验证与限制

运行账号认证与安全审计的定向测试：

```bash
cd apps/api
uv run pytest --no-cov tests/test_auth.py tests/test_account_security_audit.py
uv run ruff check src/gerclaw_api/modules/identity api/routes/auth.py
uv run mypy src/gerclaw_api/modules/identity api/routes/auth.py
```

当前不提供邮箱或手机验证、找回密码、MFA、风险风控、机构归属、医生执业资质、患者
授权、访客数据迁移、独立假名映射或受控重新识别。上述能力必须在专门的受审计流程
中实现，不能由本地账户角色推断或绕过。
