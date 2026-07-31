<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/agent/interrupt-agent -->

# 中断智能体

`Agent` 类基于 `asyncio.CancelledError` 实现中断机制，支持在模型推理或工具执行的任意阶段停止执行。中断之后，智能体的上下文会保持一致状态，会话可以立即通过新的输入消息继续。

中断智能体有两种方式，取决于智能体是否正在运行：

- 智能体正在运行 reply reply_stream task.cancel() asyncio.CancelledError
- 智能体处于暂停状态 reply_stream UserInterruptEvent ToolResultBlock ToolResultStartEvent ToolResultTextDeltaEvent ToolResultEndEvent ReplyEndEvent reply reply_stream

**中断运行中的智能体**

```python
import asyncio
from agentscope.agent import Agent
from agentscope.message import UserMsg

async def chat(agent: Agent) -> None:
    async for event in agent.reply_stream(
        UserMsg(name="user", content="..."),
    ):
        ...

async def main() -> None:
    agent = Agent(...)
    task = asyncio.create_task(chat(agent))

    # 在任意时刻取消任务即可中断智能体
    await asyncio.sleep(1)
    task.cancel()

asyncio.run(main())
```

**中断已暂停的智能体**

```python
from agentscope.agent import Agent
from agentscope.event import UserInterruptEvent

async def main() -> None:
    agent = Agent(...)

    # 假设智能体此前已因 RequireUserConfirmEvent
    # 或 RequireExternalExecutionEvent 而暂停。
    # 传入 UserInterruptEvent 以清理待处理状态并结束当前回复。
    async for event in agent.reply_stream(
        UserInterruptEvent(reply_id=agent.state.reply_id),
    ):
        print(event)
```

> **提示** 使用 `agent.state.reply_id` 引用当前处于暂停状态的回复。有关智能体如何进入暂停状态，请参见[人机交互](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/agent/human-in-the-loop)。
