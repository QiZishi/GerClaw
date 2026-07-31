<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/context/offload-context -->

# 卸载上下文

上下文卸载把智能体已经从上下文中移除的内容（被压缩的消息、被截断的工具输出）写入外部存储，方便智能体之后通过文件工具（Read、Grep、Glob）回查那些被压缩走的细节。执行卸载的组件称为**卸载器（Offloader）**。

## 挂载卸载器

卸载器是任何实现 `Offloader` 协议的对象。该协议是结构化的，仅有两个方法：

| 方法 | 说明 |
| --- | --- |
| `offload_context(session_id, msgs)` | 持久化被压缩的消息；返回一个引用（例如文件路径） |
| `offload_tool_result(session_id, tool_result)` | 持久化被截断的工具结果；返回一个引用 |

把实现该协议的对象传入智能体的 `offloader` 参数即可完成挂载。所有内置[工作区](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/workspace/overview)（本地、Docker、E2B 等）都实现了该协议，可以直接用作卸载器：

```python
from agentscope.agent import Agent
from agentscope.workspace import LocalWorkspace

workspace = LocalWorkspace(workdir="/tmp/agent_workspace")
await workspace.initialize()

agent = Agent(
    name="my_agent",
    system_prompt="...",
    model=model,
    toolkit=toolkit,
    offloader=workspace,
)
```

未挂载卸载器时，被压缩的消息与被截断的工具结果在离开上下文窗口后即被丢弃。

## 使用工作区卸载

工作区把卸载的内容写到其文件系统的 `workdir` 之下，并按 `session_id` 隔离每次智能体运行。下图以本地工作区为例展示目录布局，沙箱类工作区在各自的文件系统中采用相同结构：

{workdir}

data

{sha256}.png

sessions

{session_id}

context.jsonl

tool_result-{tool_id}.txt

skills

内容布局如下：

- sessions/{session_id}/ context.jsonl tool_result-{tool_id}.txt
- data/
- skills/

## 自定义卸载器

需要接入工作区以外的后端（数据库、对象存储、向量库等）时，开发者只需实现 `Offloader` 协议。该协议是结构化的，无需继承：

```python
from typing import Any
from agentscope.message import Msg, ToolResultBlock

class S3Offloader:
    def __init__(self, bucket: str, prefix: str) -> None:
        self.bucket = bucket
        self.prefix = prefix

    async def offload_context(
        self,
        session_id: str,
        msgs: list[Msg],
        **kwargs: Any,
    ) -> str:
        key = f"{self.prefix}/sessions/{session_id}/context.jsonl"
        content = "\n".join(m.model_dump_json() for m in msgs)
        await self._upload(self.bucket, key, content)
        return f"s3://{self.bucket}/{key}"

    async def offload_tool_result(
        self,
        session_id: str,
        tool_result: ToolResultBlock,
        **kwargs: Any,
    ) -> str:
        key = f"{self.prefix}/sessions/{session_id}/tool_result-{tool_result.id}.txt"
        # 从工具结果块中抽取文本并上传
        ...
        return f"s3://{self.bucket}/{key}"
```

像使用工作区一样，把实例传入 `Agent(offloader=...)` 即可。
