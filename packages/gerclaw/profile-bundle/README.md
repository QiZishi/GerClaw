# @gerclaw/profile-bundle

GerClaw 的正式 DSH Profile 层。该层替换部署级系统提示语，保留原生
Plan、Goal、技能、会话、文件、Workspace、Storage 与工具服务，并挂载
GerClaw 医疗业务插件、`dsh-library`、`dsh-mineru` 和 Memorix MCP。

浏览器端只由 `@gerclaw/app` 提供，不加载 DSH 的开发者界面组件。
