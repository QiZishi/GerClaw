# @gerclaw/app

## 职责

GerClaw 的业务 API 与任务状态聚合插件。它连接处方、CGA、档案、资料库、用药审查、慢病、风险、陪伴和七种格式导出，并把可恢复的医疗任务写入 session events。本插件不实现界面、模型、会话、文件、RAG 或账号隔离；浏览器呈现由 `@gerclaw/client-ui` 负责。

## 复用与接口

复用 DSH Agent、session、projection、Plan、Goal、workspace、storage、deliverables 与工具服务，并调用其他 `@gerclaw/*` 领域服务。公开协议包括 `TaskRun`、`TaskStep`、`ArtifactDescriptor`；任务状态和模型可见状态写入账号 Host 的 session events，由 projection 恢复。

## 数据与生命周期

所有医疗数据和产物只写入当前账号独立 Host；返回浏览器的数据会移除内部路径、账号和会话标识。HTTP 路由、监听和领域存储都由 Cordis effect 注册并在卸载时释放。

五大处方模式由 App 的 `agent/pre-step` 生命周期接管当前会话中的用户消息：原文仍作为标准 `user/message` 保存并显示，文字或语音转写由模型只做字段提取，缺失判断、单问题追问、5 轮上限、生成触发和完成提示均由确定性状态机控制。上传资料编号只在当前账号记录中解析。生成成功后只显示唯一的已校验任务卡，普通回复不得另写一份内容不同的处方。

## 扩展、测试与体验

新增页面应继续使用统一任务协议和规范化导出，不得暴露插件、堆栈、密钥或 DSH 品牌。运行 `pnpm exec vitest run packages/gerclaw/client/tests/gerclaw-plugins.spec.ts`、`pnpm typecheck`，并通过真实 GerClaw 入口做键盘、触控、移动端和下载验证。已知限制：非 localhost 的麦克风需要可信 HTTPS。
