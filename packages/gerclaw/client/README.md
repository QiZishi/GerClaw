# @gerclaw/app

## 职责

GerClaw 面向医生、患者和家属的唯一 Web 客户端与业务 API 聚合插件。它提供对话、Plan、Goal、处方、CGA、档案、资料库、用药审查、慢病、风险、陪伴、历史产物及七种格式导出。语音只出现在对话输入和最终回复朗读中。本插件不实现模型、会话、文件、RAG 或账号隔离。

## 复用与接口

复用 DSH Agent、session、projection、Plan、Goal、workspace、storage、deliverables 与工具服务，并调用其他 `@gerclaw/*` 领域服务。公开协议包括 `TaskRun`、`TaskStep`、`ArtifactDescriptor`；任务状态和模型可见状态写入账号 Host 的 session events，由 projection 恢复。

## 数据与生命周期

所有医疗数据和产物只写入当前账号独立 Host；返回浏览器的数据会移除内部路径、账号和会话标识。HTTP 路由、监听和领域存储都由 Cordis effect 注册并在卸载时释放。

## 扩展、测试与体验

新增页面应继续使用统一任务协议和规范化导出，不得暴露插件、堆栈、密钥或 DSH 品牌。运行 `pnpm exec vitest run packages/gerclaw/client/tests/gerclaw-plugins.spec.ts`、`pnpm typecheck`，并通过真实 GerClaw 入口做键盘、触控、移动端和下载验证。已知限制：非 localhost 的麦克风需要可信 HTTPS。
