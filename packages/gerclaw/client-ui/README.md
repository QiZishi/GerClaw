# @gerclaw/client-ui

## 职责

在 DSH 原生 Web Client 上提供 GerClaw 产品界面：淡蓝色主题、品牌、左侧医疗入口、对话内任务卡、对话内语音控件、Plan/Goal 中文呈现和 Better Sidebar 产物页。本插件只通过公开 client slots、Conversation Node 和主题样式扩展原生对话，不拥有模型、session、业务计算、认证或医疗数据。

## 复用、接口与恢复

复用原生 connection、layout、sessions、conversation、Markdown renderer、Plan、Goal、附件和 `dsh-better-sidebar@0.15.2`。`MedicalTaskCard` 根据 `@gerclaw/app` 写入的版本化 session events 恢复步骤、耗时、最终结果和产物；`ArtifactsTab` 默认按当前 session 查询，可切换本账号全部历史。界面不接收密钥、上游地址或其他账号标识。

## 生命周期与扩展

模块卸载会注销 slot、Conversation Node、事件监听、MutationObserver、语音节点和样式。新增医疗入口时继续调用类型化业务 API 并使用统一 `TaskRun` 卡片；不要复制对话输入、Markdown 渲染或会话侧栏，也不要加入插件管理、终端和调试信息。

## 测试与限制

运行 `pnpm typecheck`、`pnpm lint` 和 `pnpm build`，再通过真实入口验证桌面、平板、手机、键盘焦点、中文 tooltip、底部输入框、Plan 审核、Goal 恢复、七种产物预览与下载。浏览器麦克风在非 localhost 环境需要可信 HTTPS；模型实际产生的分析过程会展示，但密钥、绝对路径、工具参数和内部状态字段会被过滤。
