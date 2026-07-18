# 07_AgentHarness回路 — AgentScope权限引擎与人机回环参考索引

> **模块**: AgentScope Permission Engine + Human-in-the-Loop (HITL) Events
> **适用版本**: AgentScope 2026.x（含PermissionMode 5种模式、外部执行工具、中间件审批）
> **对应GerClaw需求**: 07_AgentHarness回路.md（权限确认、医生审批、外部执行中断恢复）
> **编写时间**: 2026-07-02

---

## 1. 模块映射总览

GerClaw老年医疗AI平台要求所有医疗决策（尤其是处方、诊断修改、转诊）必须经过"AI建议→权限检查→人工审批→执行"的闭环。AgentScope提供了三层机制实现这一回环：

| GerClaw需求 | AgentScope对应机制 | 核心模块/类 |
|------------|-------------------|------------|
| 工具调用权限分级（查询/建议/处方） | PermissionEngine + PermissionRule | `agentscope.permission` |
| 5种权限模式（默认/接受编辑/只读/旁路/不询问） | PermissionMode 枚举 | `PermissionMode.DEFAULT/ACCEPT_EDITS/EXPLORE/BYPASS/DONT_ASK` |
| 处方前医生确认（ASK→确认→执行） | RequireUserConfirmEvent / UserConfirmResultEvent | `agentscope.event` |
| 外部系统执行（HIS开药、急诊通知） | RequireExternalExecutionEvent / ExternalExecutionResultEvent + is_external_tool | `agentscope.tool.ToolBase` |
| 自定义审批逻辑（主任审批、药师审核） | 自定义Tool.check_permissions() + MiddlewareBase.on_acting | `agentscope.middleware` |
| 审批超时/紧急绕过 | PermissionMode运行时切换 + bypass_immune安全标记 | `PermissionContext.mode` |
| 审计轨迹 | reply_stream事件流 + TracingMiddleware | `agentscope.event` + `agentscope.middleware` |

**核心数据流**:

```
用户输入 → Agent.reply_stream()
  → 模型推理生成ToolCallBlock
  → PermissionEngine.check_permission(tool, tool_input)
      → 按PermissionMode分发_check_*方法
      → deny规则 → ask规则 → tool.check_permissions() → allow规则 → 默认行为
  → 决策为ALLOW: 执行工具 → 继续ReAct循环
  → 决策为ASK:  发布RequireUserConfirmEvent → Agent暂停等待
      → 外部传入UserConfirmResultEvent(confirmed=True/False, rules=[...])
      → 确认: 执行工具 → 将接受的规则写入PermissionEngine → 继续
      → 拒绝: 跳过工具 → 将拒绝结果反馈给LLM → 继续
  → 工具is_external_tool=True: 发布RequireExternalExecutionEvent → Agent暂停
      → 外部系统执行后传入ExternalExecutionResultEvent(execution_results=[...])
      → 将结果注入上下文 → 继续ReAct循环
  → 模型生成最终文本回复 → REPLY_END
```

---

## 2. 核心API参考

### 2.1 PermissionMode — 5种权限模式

**导入路径**: `from agentscope.permission import PermissionMode`

| 枚举值 | 行为 | GerClaw适用场景 |
|--------|------|----------------|
| `DEFAULT` | 所有操作需显式规则或用户确认；Bash只读命令自动ALLOW；Read/Glob/Grep返回PASSTHROUGH需规则匹配才放行 | **推荐默认模式**。日常问诊，所有处方/诊断修改操作自动ASK |
| `ACCEPT_EDITS` | 自动放行工作目录内的文件操作和Bash文件系统命令（需目标路径在working_directories内）；危险路径保护仍生效 | 不适用于医疗场景（文件系统导向） |
| `EXPLORE` | 只读模式：允许Read/Grep/Glob和只读Bash命令；拒绝任何修改操作 | 症状初筛、病历查询阶段，Agent仅做信息检索 |
| `BYPASS` | 跳过所有安全检查（deny/ask规则仍生效，工具自身DENY仍生效）；bypass_immune安全ASK被忽略 | **紧急情况绕过**：红旗症状急救路径，需配合deny规则保护核心禁区 |
| `DONT_ASK` | 将所有ASK转为DENY，无人值守执行；Safety ASK也被转为DENY | 夜间自动随访、定时报告生成等无医生在场场景 |

**运行时切换模式**:
```python
agent.state.permission_context.mode = PermissionMode.EXPLORE  # 切换到只读
agent.state.permission_context.mode = PermissionMode.DONT_ASK  # 无人值守
```

### 2.2 PermissionRule — 权限规则配置

**导入路径**: `from agentscope.permission import PermissionRule, PermissionBehavior`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `tool_name` | `str` | 是 | 规则适用的工具名（如"prescribe_drug"、"query_drug_info"） |
| `rule_content` | `str \| None` | 是 | 匹配模式；`None`表示工具名级别规则（匹配该工具所有调用）；Bash为`"前缀:*"`前缀匹配；文件工具为glob模式；自定义工具默认仅`None`级别匹配 |
| `behavior` | `PermissionBehavior` | 是 | `ALLOW`/`DENY`/`ASK` |
| `source` | `str` | 是 | 规则来源：`"userSettings"`/`"projectSettings"`/`"session"`/`"suggested"`/`"medicalPolicy"` |

**规则优先级**: DENY > ASK > ALLOW（同名规则deny优先于ask，ask优先于allow）。

**GerClaw医疗规则示例**:
```python
PermissionRule(
    tool_name="query_drug_info",       # 药品说明书查询
    rule_content=None,                  # 匹配所有调用
    behavior=PermissionBehavior.ALLOW,
    source="medicalPolicy",
)
PermissionRule(
    tool_name="prescribe_drug",         # 开药
    rule_content=None,
    behavior=PermissionBehavior.ASK,    # 必须确认
    source="medicalPolicy",
)
PermissionRule(
    tool_name="modify_diagnosis",       # 修改诊断
    rule_content=None,
    behavior=PermissionBehavior.ASK,
    source="medicalPolicy",
)
PermissionRule(
    tool_name="emergency_referral",     # 急诊转诊
    rule_content=None,
    behavior=PermissionBehavior.DENY,   # Agent不可直接触发，仅外部系统
    source="medicalPolicy",
)
```

### 2.3 PermissionDecision — 权限决策结果

**导入路径**: `from agentscope.permission import PermissionDecision`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `behavior` | `PermissionBehavior` | 必填 | ALLOW / DENY / ASK / PASSTHROUGH |
| `message` | `str` | 必填 | 人类可读的决策说明 |
| `decision_reason` | `str \| None` | `None` | 决策原因（如"safety check"、"read-only command"） |
| `updated_input` | `dict \| None` | `None` | 修改后的输入（如路径清理后） |
| `suggested_rules` | `list[PermissionRule] \| None` | `None` | 建议用户接受的规则（ASK时自动生成） |
| `bypass_immune` | `bool` | `False` | 是否为不可绕过的安全ASK（设为True后allow规则也无法静默，仅BYPASS模式跳过） |

**PermissionBehavior枚举值**:
- `ALLOW`: 允许执行
- `DENY`: 拒绝执行
- `ASK`: 询问用户确认
- `PASSTHROUGH`: 委托给权限引擎继续按规则/模式评估（工具自定义check_permissions返回此值表示"我不做决定，交给引擎"）

### 2.4 PermissionEngine.check_permissions 流程

**导入路径**: `from agentscope.permission import PermissionEngine, PermissionContext`

PermissionEngine是权限判断的核心，根据当前PermissionMode分发到对应的检查方法：

**DEFAULT模式流程**（最常用）:
```
1. deny规则匹配 → 命中则返回DENY
2. ask规则匹配 → 命中则返回ASK
3. tool.check_permissions(tool_input, context) → 工具自身动态检查
   - 返回ALLOW → 直接ALLOW
   - 返回DENY → 直接DENY
   - 返回ASK（bypass_immune=True）→ 返回ASK（不可被allow规则覆盖）
   - 返回ASK（bypass_immune=False）→ 继续
   - 返回PASSTHROUGH → 继续
4. allow规则匹配 → 命中则返回ALLOW
5. 默认返回ASK
```

**各模式差异**:
- `_check_default`: 如上所述
- `_check_explore`: 非只读操作直接DENY → 规则匹配
- `_check_accept_edits`: 工作目录内文件操作自动ALLOW → 其余走default
- `_check_bypass`: deny规则 → ask规则（非bypass_immune）→ 工具DENY → 默认ALLOW
- `_check_dont_ask`: 所有ASK转为DENY

**直接调用PermissionEngine**（不启动完整Agent）:
```python
from agentscope.permission import PermissionEngine, PermissionContext, PermissionMode
context = PermissionContext(mode=PermissionMode.DEFAULT)
engine = PermissionEngine(context)
engine.add_rule(some_rule)
decision = await engine.check_permission(tool_instance, tool_input_dict)
```

### 2.5 RequireUserConfirmEvent处理流程

**导入路径**: `from agentscope.event import RequireUserConfirmEvent`

当PermissionEngine返回ASK决策时，Agent自动发布此事件并暂停执行。

**事件字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `EventType.REQUIRE_USER_CONFIRM` | 事件类型常量 |
| `reply_id` | `str` | 当前reply的ID（恢复时必须匹配） |
| `tool_calls` | `list[ToolCallBlock]` | 待确认的工具调用列表，每个tool_call包含：`id`、`name`、`input`（JSON字符串）、`state="asking"`、`suggested_rules`（建议规则列表） |

**典型处理逻辑**:
```python
async for event in agent.reply_stream(UserMsg(name="user", content=...)):
    if event.type == EventType.REQUIRE_USER_CONFIRM:
        # 将待审批项展示给医生
        for tc in event.tool_calls:
            print(f"[需审批] {tc.name}: {tc.input}")
            print(f"  建议规则: {tc.suggested_rules}")
        # 暂停事件流，等待医生操作
        break
```

### 2.6 UserConfirmResultEvent恢复reply

**导入路径**: `from agentscope.event import UserConfirmResultEvent, ConfirmResult`

医生审批后，构造此事件传入`agent.reply_stream(inputs=...)`恢复执行。

**ConfirmResult字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `confirmed` | `bool` | True=批准执行，False=拒绝 |
| `tool_call` | `ToolCallBlock` | 对应的工具调用（id/name/input必须与原调用一致） |
| `rules` | `list[PermissionRule] \| None` | 批准时附带的规则（接受suggested_rules中的规则则写入引擎，后续相同调用不再询问） |

**恢复执行**:
```python
from agentscope.message import ToolCallBlock
from agentscope.event import UserConfirmResultEvent, ConfirmResult

result_event = UserConfirmResultEvent(
    reply_id=reply_id,  # 必须与RequireUserConfirmEvent中的reply_id一致
    confirm_results=[
        ConfirmResult(
            confirmed=True,
            tool_call=ToolCallBlock(
                id=tc.id, name=tc.name, input=tc.input,
            ),
            rules=tc.suggested_rules,  # 接受建议规则，后续自动放行
        ),
    ],
)

# 恢复执行
async for event in agent.reply_stream(inputs=result_event):
    # 继续处理事件...
    pass
```

### 2.7 ExternalExecutionResultEvent外部执行结果回传

**导入路径**: `from agentscope.event import RequireExternalExecutionEvent, ExternalExecutionResultEvent`

外部执行工具（`is_external_tool = True`）将实际执行委派给Agent运行时之外的系统（如HIS开药系统、急诊通知系统）。

**外部工具定义**:
```python
from agentscope.tool import ToolBase
from agentscope.permission import PermissionDecision, PermissionBehavior

class EmergencyNotifyTool(ToolBase):
    name = "emergency_notify"
    description = "发送急诊通知给值班医生"
    is_external_tool = True    # 关键标记
    is_read_only = False
    is_concurrency_safe = True

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="急诊通知始终允许派发",
        )
    # 不需要实现__call__/call()方法
```

**RequireExternalExecutionEvent字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `EventType.REQUIRE_EXTERNAL_EXECUTION` | 事件类型 |
| `reply_id` | `str` | reply ID |
| `tool_calls` | `list[ToolCallBlock]` | 需外部执行的工具调用 |

**ExternalExecutionResultEvent字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `EventType.EXTERNAL_EXECUTION_RESULT` | 事件类型 |
| `reply_id` | `str` | reply ID |
| `execution_results` | `list[ToolResultBlock]` | 外部执行返回的结果 |

**外部执行结果回传**:
```python
from agentscope.message import ToolResultBlock, TextBlock
from agentscope.event import ExternalExecutionResultEvent

# 外部系统执行完毕后，构造结果回传
result_event = ExternalExecutionResultEvent(
    reply_id=reply_id,
    execution_results=[
        ToolResultBlock(
            id=tc.id,
            name=tc.name,
            output=[TextBlock(text="急诊通知已发送，值班医生张医生5分钟内到达")],
            state="success",
        ),
    ],
)
async for event in agent.reply_stream(inputs=result_event):
    pass
```

### 2.8 中间件实现自定义审批逻辑

**导入路径**: `from agentscope.middleware import MiddlewareBase`

MiddlewareBase提供6个洋葱模型Hook + 1个转换器Hook，可在不修改Agent代码的前提下注入审批逻辑：

| Hook | 模式 | 拦截位置 | GerClaw用途 |
|------|------|---------|------------|
| `on_reply` | 洋葱 | 整个reply流程（所有ReAct轮次） | 审批超时计时、审计日志开启/关闭 |
| `on_reasoning` | 洋葱 | 推理步骤（模型调用前后） | 强制注入安全提示到system prompt |
| `on_acting` | 洋葱 | 单个工具调用执行（I/O层） | 自定义审批路由（高风险→主任审批）、审批日志 |
| `on_model_call` | 洋葱 | 底层模型API调用 | Token预算监控、模型降级 |
| `on_compress_context` | 洋葱 | 上下文压缩 | 保留医疗关键信息不被压缩 |
| `on_system_prompt` | 转换器 | system prompt组装 | 动态注入患者安全警示 |

**自定义审批中间件骨架**:
```python
from agentscope.middleware import MiddlewareBase

class MedicalApprovalMiddleware(MiddlewareBase):
    """医疗审批中间件：拦截高风险工具调用，路由到对应审批级别。"""

    async def on_acting(self, agent, input_kwargs, next_handler):
        tool_call = input_kwargs.get("tool_call", {})
        tool_name = tool_call.get("name", "")

        # 高风险操作：主任审批
        if tool_name in {"prescribe_controlled_drug", "modify_critical_diagnosis"}:
            # 可在此处：记录审批日志、通知主任、等待审批结果
            print(f"[主任审批] 高风险操作: {tool_name}")

        # 继续执行链
        async for chunk in next_handler(**input_kwargs):
            yield chunk
```

---

## 3. 源码路径索引

| 模块 | 文件路径（相对于agentscope源码根目录src/agentscope/） |
|------|-----------------------------------------------------|
| PermissionMode / PermissionBehavior 枚举 | `permission/_types.py` |
| PermissionRule 类 | `permission/_rule.py` |
| PermissionContext / AdditionalWorkingDirectory 类 | `permission/_context.py` |
| PermissionDecision 类 | `permission/_decision.py` |
| PermissionEngine 类（含5种_check_*方法） | `permission/_engine.py` |
| permission模块公开API导出 | `permission/__init__.py` |
| ToolBase（含check_permissions/match_rule/generate_suggestions/is_external_tool） | `tool/_base.py` |
| ToolMiddlewareBase（工具级中间件） | `tool/_middleware.py` |
| MiddlewareBase（Agent级中间件基类） | `middleware/_base.py` |
| RequireUserConfirmEvent / UserConfirmResultEvent / ConfirmResult | `event/_event.py` (L378-L429) |
| RequireExternalExecutionEvent / ExternalExecutionResultEvent | `event/_event.py` (L391-L441) |
| EventType枚举（REQUIRE_USER_CONFIRM等常量） | `event/_event.py` |
| ToolCallBlock / ToolResultBlock / TextBlock | `message/` |
| DashScopeChatModel | `model/_dashscope/_model.py` |
| Agent.reply_stream()（事件流+HITL暂停恢复入口） | `agent/` |
| TracingMiddleware（执行追踪） | `middleware/_tracing.py` |

---

## 4. 官方示例参考

| 测试文件 | 覆盖场景 |
|---------|---------|
| `tests/permission_engine_test.py` | PermissionEngine规则优先级、Bash命令匹配、文件glob匹配、危险路径保护、只读命令检测、bypass_immune机制、建议规则生成 |
| `tests/permission_mode_test.py` | 5种PermissionMode的行为差异（DEFAULT/ACCEPT_EDITS/EXPLORE/BYPASS/DONT_ASK） |
| `tests/hitl_user_confirmation_test.py` | 单工具审批、顺序多工具审批、并发多工具审批、批量审批（一次确认多个工具）、ConfirmResult构造、UserConfirmResultEvent恢复 |
| `tests/hitl_external_execution_test.py` | 外部执行工具定义、RequireExternalExecutionEvent派发、ExternalExecutionResultEvent结果回传、顺序/并发外部执行 |
| `tests/hitl_mixed_interrupt.py` | 用户确认+外部执行混合中断场景、多轮暂停恢复 |

---

## 5. 文档链接

| 文档章节 | 位置 | 内容 |
|---------|------|------|
| 权限系统概述 | group_B5-8.md §3 (/building-blocks/permission-system) | Rules/Mode/Built-in Checks三层决策 |
| Permission Mode | group_B5-8.md §3.2 | 5种模式详解、初始化/运行时配置、工作目录设置 |
| Permission Rule | group_B5-8.md §3.3 | 规则字段、Bash前缀匹配、文件glob匹配、初始化/运行时配置规则、建议规则 |
| Built-in Checks | group_B5-8.md §3.4 | 工具自定义check_permissions、Safety check契约、只读命令列表、危险路径列表 |
| 外部执行Tool | group_B5-8.md §1.5 | is_external_tool定义、Human-in-the-Loop基础 |
| 中间件系统 | group_B5-8.md §4 (/building-blocks/middleware) | MiddlewareBase Hook机制、6个洋葱Hook+1个转换器Hook |
| Tool Middleware | group_B5-8.md §1.6 | ToolMiddlewareBase洋葱模型、工具级中间件挂载 |
| 源码映射（permission模块） | source_map_tools.md §3 | PermissionEngine/PermissionRule/PermissionContext/PermissionDecision完整字段表、_check_*流程说明 |
| 源码映射（middleware模块） | source_map_tools.md §4 | MiddlewareBase所有Hook签名、内置中间件一览 |

---

## 6. GerClaw适配要点

### 6.1 医疗审批分级

基于AgentScope权限系统，GerClaw设计三级审批体系：

| 风险等级 | 医疗操作示例 | PermissionBehavior | 审批人 | 响应时效 |
|---------|------------|-------------------|--------|---------|
| **低风险** | 药品说明书查询、ICD编码查询、临床指南检索、MMSE/GDS评分计算、病历只读查询 | ALLOW（自动通过） | 无需审批 | 即时 |
| **中风险** | 检查建议生成、随访计划制定、诊断建议（置信度≥70%）、患者教育材料生成 | ASK → 执业医师确认 | 值班医生 | 工作时间30分钟 |
| **高风险** | 处方开立、诊断修改（置信度<70%）、多重用药调整（>5种）、麻醉/精神/抗肿瘤药 | ASK（bypass_immune=True）→ 主治医师/主任审批 | 主治医师及以上 | 工作时间2小时 |
| **极高风险** | 急诊转诊触发、红旗症状处理、药物禁忌证冲突 | 外部工具（is_external_tool）→ 自动通知+人工确认 | 值班医生+急诊团队 | <5分钟 |

**bypass_immune=True的使用场景**：处方类工具（prescribe_drug）、诊断修改工具（modify_diagnosis）的check_permissions应返回bypass_immune=True的ASK决策，确保即使有人误配置了allow规则也无法绕过医生审批。

### 6.2 推荐配置

GerClaw生产环境推荐配置：`PermissionMode.DEFAULT` + 医疗规则集 + 自定义check_permissions：

```python
from agentscope.permission import (
    PermissionContext, PermissionMode, PermissionRule, PermissionBehavior,
)

# 推荐初始化配置
medical_context = PermissionContext(
    mode=PermissionMode.DEFAULT,  # 默认模式，最安全
    allow_rules={
        # 低风险查询工具：自动放行
        "query_drug_info": [PermissionRule(
            tool_name="query_drug_info", rule_content=None,
            behavior=PermissionBehavior.ALLOW, source="medicalPolicy",
        )],
        "query_icd_code": [PermissionRule(
            tool_name="query_icd_code", rule_content=None,
            behavior=PermissionBehavior.ALLOW, source="medicalPolicy",
        )],
        "calculate_score": [PermissionRule(
            tool_name="calculate_score", rule_content=None,
            behavior=PermissionBehavior.ALLOW, source="medicalPolicy",
        )],
    },
    ask_rules={
        # 中高风险操作：必须确认
        "prescribe_drug": [PermissionRule(
            tool_name="prescribe_drug", rule_content=None,
            behavior=PermissionBehavior.ASK, source="medicalPolicy",
        )],
        "modify_diagnosis": [PermissionRule(
            tool_name="modify_diagnosis", rule_content=None,
            behavior=PermissionBehavior.ASK, source="medicalPolicy",
        )],
        "order_test": [PermissionRule(
            tool_name="order_test", rule_content=None,
            behavior=PermissionBehavior.ASK, source="medicalPolicy",
        )],
    },
    deny_rules={
        # 绝对禁止Agent直接操作的
        "emergency_referral": [PermissionRule(
            tool_name="emergency_referral", rule_content=None,
            behavior=PermissionBehavior.DENY, source="medicalPolicy",
        )],
    },
)
```

**关键工具的check_permissions应实现bypass_immune安全检查**:
- prescribe_drug: 检查是否为受控药物（麻醉/精神类），剂量是否超老年人上限
- modify_diagnosis: 检查是否为危重诊断修改（如心梗、脑卒中）
- 触发红旗症状时返回bypass_immune=True的ASK

### 6.3 风险与应对：审批超时与紧急情况绕过机制

| 风险场景 | 问题 | 应对方案 |
|---------|------|---------|
| **审批超时**（医生未在规定时间响应） | 患者等待、流程阻塞 | 1. 超时定时器（如2小时未审批自动拒绝并通知医生）；2. 自动升级到上级医生；3. 超时结果通过UserConfirmResultEvent(confirmed=False)回传 |
| **紧急情况需绕过审批**（如心梗、脑卒中） | DEFAULT模式下ASK会阻塞急救流程 | 1. 检测红旗症状时自动切换PermissionMode.BYPASS（仅保留deny规则保护）；2. 急诊工具使用is_external_tool=True绕过Agent内部执行；3. BYPASS模式必须配置deny规则保护核心禁区 |
| **审批人离线**（夜间/节假日） | 无医生可审批 | 切换到PermissionMode.DONT_ASK模式（ASK自动转DENY），Agent仅提供建议不执行任何写操作；同时通知值班医生 |
| **误拒绝**（医生点错拒绝） | 正常操作被拒绝 | UserConfirmResultEvent(confirmed=False)后LLM收到拒绝结果，可重新生成建议；建议规则不写入引擎，下次同类操作仍需审批 |
| **规则膨胀**（大量suggested_rules累积） | allow_rules越来越多，可能过度授权 | 1. 规则设置过期时间（session级规则会话结束清除）；2. 定期审计allow_rules；3. 医疗核心工具（处方/诊断）不在suggested_rules中提供自动放行规则 |
| **bypass_immune被BYPASS模式跳过** | BYPASS模式下安全ASK被忽略 | BYPASS仅用于急救路径；必须配置deny规则作为最终护栏；BYPASS模式切换需记录审计日志并通知管理员 |

**紧急绕过示例（红旗症状触发）**:
```python
# 检测到红旗症状（胸痛+呼吸困难）
if has_red_flags(symptoms):
    # 切换到BYPASS模式，仅deny规则生效
    agent.state.permission_context.mode = PermissionMode.BYPASS
    # 添加紧急规则：允许急诊通知工具
    engine.add_rule(PermissionRule(
        tool_name="emergency_notify",
        rule_content=None,
        behavior=PermissionBehavior.ALLOW,
        source="emergency_override",
    ))
    # 记录审计日志
    log_emergency_override(patient_id, symptoms, doctor_id)
```

---

## 7. 可运行示例指引

| 示例文件 | 功能说明 | 运行前提 |
|---------|---------|---------|
| `agentscope-examples/07_harness_loop/permission_harness.py` | 演示PermissionEngine + PermissionRule配置：对开药(prescribe_drug)、修改诊断(modify_diagnosis)等危险操作设置ASK确认，对只读查询(query_drug_info)自动ALLOW；模拟5种医疗操作的权限检查流程（纯权限引擎演示，不需要LLM，不需要API Key） | `pip install agentscope` |
| `agentscope-examples/07_harness_loop/human_in_the_loop.py` | 演示完整HITL流程：Agent尝试开药→产生RequireUserConfirmEvent→模拟医生终端审批→传入UserConfirmResultEvent恢复reply→最终输出。使用DashScopeChatModel（需要DASHSCOPE_API_KEY环境变量） | `export DASHSCOPE_API_KEY=xxx && python human_in_the_loop.py` |

**permission_harness.py核心流程**:
1. 创建PermissionContext(DEFAULT模式) + 医疗规则集
2. 创建自定义医疗工具（query_drug_info只读/prescribe_drug危险/check_vital_signs只读/modify_diagnosis危险/order_exam中风险）
3. 直接调用PermissionEngine.check_permission()模拟5种工具调用
4. 演示不同PermissionMode切换（DEFAULT→EXPLORE→BYPASS→DONT_ASK）下的决策变化
5. 演示add_rule()动态添加规则后的决策变化

**human_in_the_loop.py核心流程**:
1. 创建DashScopeChatModel（从环境变量读Key）
2. 定义prescribe_drug工具（check_permissions返回ASK）
3. 创建Agent并绑定工具，配置PermissionContext.DEFAULT
4. 第一轮reply_stream：患者主诉高血压用药→Agent生成开药ToolCall→引擎返回ASK→捕获RequireUserConfirmEvent
5. 模拟医生审批终端（命令行交互）：展示药名/剂量→医生输入y/n
6. 构造UserConfirmResultEvent + ConfirmResult恢复执行
7. 第二轮reply_stream：Agent收到审批结果→执行工具→生成最终建议→输出
