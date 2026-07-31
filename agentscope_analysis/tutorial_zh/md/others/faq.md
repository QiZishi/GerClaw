<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/others/faq -->

# 常见问题

<details>
<summary>AgentScope 2.0 与 1.0 兼容吗？</summary>

不兼容。AgentScope 2.0 是一次破坏性更新，重新设计了 agent 抽象，并新增了事件系统、workspace、权限系统等大量新特性。API 与 1.0 源码不兼容，也不提供自动迁移路径。

对所有新项目，我们建议直接采用 2.0，以获得新版能力；1.0 的文档仍会保留供存量用户参考。
</details>

<details>
<summary>AgentScope 是否支持沙箱化执行？</summary>

支持。**Workspace** 是 AgentScope 为 agent 提供的执行环境抽象，内置三种实现 —— `LocalWorkspace`（宿主文件系统）、`DockerWorkspace`（容器）、`E2BWorkspace`（E2B 云沙箱），共享同一份接口，因此同一份 agent 代码可以无差别地在任意后端上运行。Workspace 同时负责管理 MCP server 生命周期、skill 与上下文 offload。

完整介绍见 [Workspace](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/workspace/overview)，包括如何把 workspace 接入 `Agent`，以及多租户场景下的 `WorkspaceManager`。
</details>

<details>
<summary>AgentScope 2.0 有配套的前端吗？</summary>

有，分两个层次：

- TypeScript SDK pnpm install @agentscope-ai/agentscope Msg Event
- 前端 UI Agent Service
</details>

<details>
<summary>2.0 还会提供 RAG 和 long-term memory 吗？</summary>

会。两个模块正在从 1.0 向 2.0 架构迁移，会在后续版本中陆续上线，具体进度请关注 changelog 与 GitHub 发版。
</details>

<details>
<summary>除了 Python 还有其他语言版本吗？</summary>

有。AgentScope 目前提供三种语言实现，各自独立仓库：

- Python agentscope-ai/agentscope
- TypeScript agentscope-ai/agentscope-typescript
- Java agentscope-ai/agentscope-java
</details>
