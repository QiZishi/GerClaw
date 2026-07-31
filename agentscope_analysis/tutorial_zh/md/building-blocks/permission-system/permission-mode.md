<!-- 来源：https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/permission-system/permission-mode -->

# 权限模式

权限模式是每次工具调用决策背后的全局策略：它决定哪些决策点生效，以及无人裁决的调用如何收尾。AgentScope 支持五种模式，分别适配不同的部署场景：

| 模式 | 行为 | 适用场景 |
| --- | --- | --- |
| `DEFAULT` | 只读调用自动放行（`Read` / `Glob` / `Grep`，以及 `ls`、`git status`、`cat` 等只读 Bash 命令）；其余操作在没有允许规则命中时都会询问用户。安全 ASK 无法被允许规则覆盖 | 最安全，推荐默认值 |
| `ACCEPT_EDITS` | `DEFAULT` 放行的一切，**外加**工作目录内的编辑操作无需询问即自动放行：对已配置工作目录下文件的 `Write` / `Edit`，以及**所有目标路径都在工作目录内**的 Bash 文件系统命令（`mkdir`/`touch`/`rm`/`cp`/`mv`/`sed`） | 用户在场的活跃开发 |
| `EXPLORE` | 放行只读操作，拒绝任何修改。不咨询允许规则与工具的安全检查：只读保证不会被规则放行掉。用户配置的拒绝/询问规则仍然优先于只读自动放行 | 代码探索、规划 |
| `BYPASS` | 完全信任：拒绝/询问规则与工具返回的 DENY 仍然生效，但**工具的安全 ASK 会被跳过**（`rm -rf /`、写入 `~/.bashrc`、命令注入等都会放行），其余一切均放行。请用拒绝规则保护特定路径 | 沙箱环境或完全可信的运行 |
| `DONT_ASK` | `ACCEPT_EDITS` 的无人值守版本：只读自动放行、工作目录内编辑自动放行，但任何原本会询问（不在场的）用户的操作都被转为 **DENY**。永不返回 ASK | 无人值守 / 计划任务 |

## 设置模式

可以在创建智能体时通过 `AgentState.permission_context` 设置模式，也可以在运行时切换：

**初始化时配置**

```python
from agentscope.agent import Agent
from agentscope.state import AgentState
from agentscope.permission import PermissionContext, PermissionMode

agent = Agent(
    name="my_agent",
    system_prompt="...",
    model=model,
    state=AgentState(
        permission_context=PermissionContext(
            mode=PermissionMode.DEFAULT,
        )
    ),
)
```

**运行时切换**

```python
# 切换到只读模式
agent.state.permission_context.mode = PermissionMode.EXPLORE

# 切换到无人值守模式以执行批处理
agent.state.permission_context.mode = PermissionMode.DONT_ASK
```

**ACCEPT_EDITS 配合工作目录**

```python
from agentscope.permission import AdditionalWorkingDirectory

agent = Agent(
    name="my_agent",
    system_prompt="...",
    model=model,
    state=AgentState(
        permission_context=PermissionContext(
            mode=PermissionMode.ACCEPT_EDITS,
            working_directories={
                "/my/project": AdditionalWorkingDirectory(
                    path="/my/project",
                    source="userSettings",
                )
            },
        )
    ),
)
```

## 各模式的决策流程

每种模式都沿[决策矩阵](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/permission-system/overview#%E5%86%B3%E7%AD%96%E7%9F%A9%E9%98%B5)中的决策点依次评估；下面的流程图把每种模式展开为完整的决策流程。ASK 结果会触发用户确认；如果用户接受自动生成的建议规则，规则会被持久化以供后续调用使用。

-
-
-
-
-

> **提示** **拒绝规则**与**显式询问规则**在每种模式下都始终生效（包括 `BYPASS`）。
>
> **工具发出的安全 ASK**（`bypass_immune=True`）在 `DEFAULT`、`ACCEPT_EDITS`、`DONT_ASK` 下被尊重，允许规则无法将其静默。`BYPASS` 模式按设计跳过：BYPASS 的语义是「用户已主动放弃安全提示，只剩拒绝/询问规则作为护栏」。详见[安全检查契约](https://docs.agentscope.io/versions/2.0.6dev/zh/building-blocks/permission-system/tool-check#%E5%AE%89%E5%85%A8%E6%A3%80%E6%9F%A5%E5%A5%91%E7%BA%A6)。
