<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/plan -->

# 计划模式

## 概述

计划（Planning）是智能体把复杂请求拆分成离散、有序、可追踪步骤的方式。AgentScope 不让模型仅靠自由形式的推理来同时兼顾多步目标，而是提供一小组内置工具，让智能体通过工具调用来维护一份**显式、结构化的任务清单** —— 任务的创建、查询与更新都走工具调用。

AgentScope 内置了四个计划相关的工具：

| Tool | 操作 | 只读 |
| --- | --- | --- |
| `TaskCreate` | 向任务清单末尾追加新任务 | 否 |
| `TaskGet` | 按 ID 获取单个任务的完整信息（描述、状态、依赖） | 是 |
| `TaskList` | 列出所有任务及其状态、owner、阻塞关系 | 是 |
| `TaskUpdate` | 更新任务的状态、字段或依赖边，亦可删除任务 | 否 |

四者都是状态注入式工具（`is_state_injected = True`）：智能体运行时把当前的 `AgentState` 注入每次调用，工具直接读写 `agent.state.tasks_context`。这意味着任务清单**以智能体为作用域**，并随智能体的状态进行持久化。

## 使用计划工具

### 装配工具

像其他内置工具一样实例化并注册到 `Toolkit`：

```python
from agentscope.agent import Agent
from agentscope.tool import (
    Toolkit,
    TaskCreate,
    TaskGet,
    TaskList,
    TaskUpdate,
)

toolkit = Toolkit(
    tools=[
        TaskCreate(),
        TaskGet(),
        TaskList(),
        TaskUpdate(),
    ],
)

agent = Agent(
    name="planner",
    system_prompt="You are a planning assistant.",
    model=model,
    toolkit=toolkit,
)
```

每个工具的 `description` 已经包含详细提示，说明何时调用、何时跳过以及如何解读输出，因此不需要额外的系统提示工程。`check_permissions()` 硬编码为 `ALLOW` —— 计划工具是纯内存状态变更，不会触发用户提示。

### 任务生命周期

典型的规划循环如下：

登记工作

收到新指令时，智能体对每个离散步骤分别调用一次 `TaskCreate`，提供一句简短的命令式 `subject` 和更详尽的 `description`。新任务按创建顺序追加；`id` 是稳定且单调递增的数字串（`"1"`、`"2"`……）。

查看队列

`TaskList` 返回每个任务一行的紧凑摘要（id、状态、subject、owner、blocked-by），智能体据此挑选下一个可做的任务 —— 通常是 ID 最小且无未解 `blocked_by` 的 `pending` 任务。

认领并开始

开始工作前，智能体调用 `TaskUpdate` 把任务的 `status` 置为 `in_progress`（多智能体场景下还可设置 `owner`）。

获取完整上下文

`TaskGet` 返回特定任务的完整描述、依赖边与元数据 —— 当描述较长时，在执行前调用很有帮助。

完成或重新规划

完成时，`TaskUpdate` 把状态翻转为 `completed`。若智能体发现了新工作，则回到 `TaskCreate`；若某个任务已无需做，则把状态置为 `deleted`（硬删除，同时会修正所有引用了该任务的其他任务的依赖边）。

状态流转刻意保持线性：

```text
pending → in_progress → completed
                          (或)
                      ↘ deleted（任意状态均可，硬删除）
```

### 表达依赖

任务暴露两条对称的依赖边：

- blocks
- blocked_by

`TaskUpdate` 接受 `add_blocks` 与 `add_blocked_by` 参数。每次调用都会**自动修改两端**，保持数据一致：

```python
# 创建好任务 "1" 与 "2" 后，让 "2" 依赖 "1"：
await TaskUpdate()(
    task_id="2",
    add_blocked_by=["1"],
    _agent_state=agent.state,
)
# 此时：task "2".blocked_by == ["1"] 且 task "1".blocks == ["2"]
```

任务被删除时，其 ID 会从其他所有任务的 `blocks` 与 `blocked_by` 中移除，保证依赖图始终有效。

> **提示** `TaskList` 会标注每个仍有未解 `blocked_by` 的任务，`TaskGet` 则返回完整的依赖边列表。智能体据此优先选择无阻塞的工作，但**执行层面是仅建议性的** —— 运行时不会阻止模型去做一个被阻塞的任务。

## 存储

所有任务状态都存在智能体上，位于 `agent.state.tasks_context`。相关类型如下：

```python
class Task(BaseModel):
    id: str                       # 单调递增的数字串，由 TaskCreate 分配
    subject: str                  # 一句话命令式描述
    description: str              # 详细的需求 / 上下文
    state: Literal["pending", "in_progress", "completed"] = "pending"
    owner: str | None = None
    blocks: list[str] = []        # 被本任务阻塞的任务 ID
    blocked_by: list[str] = []    # 阻塞本任务的任务 ID
    metadata: dict[str, Any] = {}
    created_at: str               # 创建时设置的 ISO-8601 时间戳

class TaskContext(BaseModel):
    tasks: list[Task] = []
```

`AgentState.tasks_context` 是 `agent.state` 模型上的常规字段，这意味着：

- 可被序列化保存。 agent.state
- 以智能体为单位。
- 可在智能体循环之外修改。 agent.state

## 自定义任务

由于任务存在 `agent.state.tasks_context`，开发者可以绕过 LLM 直接以编程方式管理任务。常见场景：

- 预置（Seeding）
- 导入（Importing）
- 迁移（Migrating）
- 评测（Evaluation）

下面的示例在智能体第一次 reply 之前预置了两个有依赖关系的任务：

```python
from agentscope.agent import Agent
from agentscope.state import Task
from agentscope.tool import Toolkit, TaskCreate, TaskGet, TaskList, TaskUpdate

agent = Agent(
    name="planner",
    system_prompt="You are a planning assistant.",
    model=model,
    toolkit=Toolkit(
        tools=[TaskCreate(), TaskGet(), TaskList(), TaskUpdate()],
    ),
)

agent.state.tasks_context.tasks.extend(
    [
        Task(
            id="1",
            subject="Fetch project requirements",
            description="Read README.md and CONTRIBUTING.md in the repo root.",
            metadata={"source": "seed"},
        ),
        Task(
            id="2",
            subject="Draft an implementation plan",
            description="Produce a step-by-step plan based on the requirements.",
            blocked_by=["1"],
            metadata={"source": "seed"},
        ),
    ],
)
# 保持反向边一致：
agent.state.tasks_context.tasks[0].blocks.append("2")
```

> **注意** 直接修改 `tasks_context` 时，你需要自行保证：
>
> - ID 唯一且可解析。 TaskCreate max(int(task.id) for task in tasks) + 1 "1" "2"
> - 依赖边双向一致。 blocks blocked_by TaskUpdate
> - 状态值合法。 Task.state pending in_progress completed deleted TaskUpdate 操作

也可以随时清空或重置计划：

```python
agent.state.tasks_context.tasks.clear()
```

智能体下一轮就会看到一个空计划并从头开始。

## 延伸阅读

- Tool ToolBase AgentState
- Agent AgentState
