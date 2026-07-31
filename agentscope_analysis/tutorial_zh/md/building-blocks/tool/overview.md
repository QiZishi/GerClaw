<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/tool/overview -->

# 概述

工具是智能体与外部世界交互的途径：执行 shell 命令、读写文件、调用 API。每个工具通过 JSON Schema 暴露给大模型，智能体通过统一的接口完成调用。

AgentScope 包含以下三个工具相关的概念：

| 概念 | 职责 |
| --- | --- |
| **工具** | 继承自 `ToolBase` 的子类，包括 AgentScope 内置工具，以及将 Python 函数和 MCP 工具封装成 `ToolBase` 子类的 `FunctionTool` / `MCPTool` 包装器 |
| **Toolkit** | 工具管理模块，负责注册工具、MCP 客户端与技能，向大模型暴露它们的 JSON Schema，并把每次工具调用分发给对应的工具对象 |
| **工具组（Tool Group）** | 一组工具 / MCP / 技能的集合，可以作为整体被激活或停用；智能体在运行时通过内置元工具控制工具组 |

最简单的 `Toolkit` 只需传入一组工具实例：

```python
from agentscope.tool import Toolkit, Bash, Read, Write, Edit

toolkit = Toolkit(
    tools=[Bash(), Read(), Write(), Edit()],
)
```

只传 `tools` 时，这些工具都进入特殊的 `"basic"` 组，该组始终激活。追加 `mcps`、`skills_or_loaders` 或额外的 `tool_groups` 即可拓展智能体的能力。

## 延伸阅读

每种能力来源都有独立的页面介绍：

## Python 函数工具

内置工具、自定义工具、函数包装与工具中间件。

## MCP

接入 MCP 服务并使用其工具。

## Skill

用 Markdown 指令集拓展智能体能力。

## 元工具

让智能体在运行时自主激活或停用工具组。

相关章节：

## 智能体

智能体如何在 ReAct 循环中编排工具调用。

## 权限系统

精细控制哪个工具可以执行、何时执行。
