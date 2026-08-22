# @gerclaw/launcher

从仓库根目录 `.env` 读取环境变量并通过真实 `dsh --profile web --patch`
加载 GerClaw 网关。启动检查只输出缺失的变量名，不输出变量值。
