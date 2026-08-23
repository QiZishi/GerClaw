# @gerclaw/skills

## 职责

提供从原 GerClaw 转换的四项 DSH skill：随访问卷、风险评估、健康教育、用药提醒。用户可通过自然语言、能力菜单或 slash command 调用；本目录不提供开发者式技能管理页。

## 复用、状态与生命周期

skill 采用 DSH 原生 skill filesystem、tool-skill 和 session/Agent 执行机制，内容位于 `skills/*/SKILL.md`。Profile 同时保留经确认相关的 DSH 健康能力，排除 Cordis 开发和插件管理技能。调用记录进入当前账号 session；文件系统插件卸载后不保留监听。

## 改进与测试

修改 skill 时保持输入、期望输出、医疗边界和失败语义，禁止通过身份设置功能差异。通过真实对话分别执行四个 slash command，并运行 Loader 配置检查。skill 的建议不替代专业诊断。
