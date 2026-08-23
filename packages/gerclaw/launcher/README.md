# @gerclaw/launcher

## 职责

从仓库根目录 `.env` 读取配置，通过真实 `dsh --profile web --patch` 启动 GerClaw 网关；不承载医疗数据或业务逻辑。启动检查只报告缺失变量名，绝不输出变量值。

## 接入、生命周期与测试

公开 `gerclaw` 与配置导出命令，加载 `profile-bundle/cordis.patch.yml`。收到退出信号后关闭 Cordis Host、账号子进程和临时资源。扩展启动参数时不得绕过 Loader 或把密钥放入命令行。运行 `pnpm gerclaw:dump-config`、`pnpm typecheck`，再以 `pnpm gerclaw` 验证启动和停止。
