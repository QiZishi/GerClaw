# 06 Skill自进化机制 — AgentScope 开发参考索引

> **模块定位**：基于 AgentScope 的 Skill 系统（基于 Markdown 的指令集 + 动态加载器 + 中间件审计），映射 GerClaw 老年医疗 AI 平台的技能定义、注册发现、运行时查看与使用审计能力。
> **对应 GerClaw 需求文档**：`gerclaw前期调研/各部分调研/06_Skill自进化机制.md`
> **AgentScope 版本**：参考 `references/agentscope/src/agentscope/` 当前源码

---

## 1. 模块映射总览

GerClaw 的 Skill 自进化机制在 AgentScope 中的落地，可映射为如下 5 个核心构件：

| GerClaw 概念 | AgentScope 对应 | 作用 |
|-------------|----------------|------|
| 医疗 Skill 定义（SKILL.md + YAML Frontmatter） | `agentscope.skill.Skill` 数据类 + `SKILL.md` 文件 | 用 Markdown 目录承载技能指令，Frontmatter 提供 name/description 等元数据 |
| 技能目录动态加载/热更新 | `agentscope.skill.LocalSkillLoader` | 从本地目录（含子目录扫描）异步加载 SKILL.md，基于 mtime 缓存失效，支持热更新 |
| 自定义技能源（数据库/远程/注册中心） | `agentscope.skill.SkillLoaderBase` 抽象基类 | 继承后实现 `list_skills()` 即可接入任意技能源（如 GerClaw Skill Registry） |
| Agent 技能注册与运行时查看 | `agentscope.tool.Toolkit` 的 `skills_or_loaders` 参数 + 内置 `SkillViewer`（工具名 `"Skill"`） | 注册技能到 Toolkit；Agent 通过 Skill 工具读取技能全文，再按指令使用已有工具执行 |
| Skill 使用计数/审计/频率限制/审批 | `agentscope.middleware.MiddlewareBase` 自定义中间件，使用 `on_acting` 钩子拦截工具调用 | 洋葱模型拦截工具执行，实现审计日志、调用计数、限流、审批前置等横切关注点 |
| 技能提示词定制（医疗安全提醒） | `Toolkit(skill_instruction_template=...)` Jinja2 模板 | 自定义注入 system prompt 的技能列表片段，可加入医疗安全红线提示 |

**关键设计认知**：AgentScope 的 Skill **不是可直接调用的 Tool**。Skill 是 Markdown 指令集，Agent 必须先通过内置的 `Skill` 工具（SkillViewer）读取 SKILL.md 全文，再用已装备的 Tool 按指令步骤执行。这与 GerClaw"医生先查阅 SOP 再执行操作"的临床工作流高度吻合。

---

## 2. 核心 API 参考

### 2.1 Skill 数据类

**位置**：`src/agentscope/skill/_base.py`
**导入**：`from agentscope.skill import Skill`

```python
@dataclass
class Skill:
    name: str         # Frontmatter 中的 name 字段，技能唯一标识
    description: str  # Frontmatter 中的 description 字段，供模型选择技能时使用
    dir: str          # 技能目录绝对路径（可存放脚本/资源文件）
    markdown: str     # SKILL.md 正文（去除 Frontmatter 后的 Markdown 内容）
    updated_at: float # SKILL.md 最后修改时间戳（用于缓存失效）
```

**SKILL.md 格式要求**：
- 必须是一个目录，目录下包含 `SKILL.md` 文件
- SKILL.md 必须包含 YAML Frontmatter（`---` 包裹），至少声明 `name` 和 `description`
- Frontmatter 可扩展任意字段（如 GerClaw 医疗扩展字段：`medical.risk_level`、`version`、`tags` 等），但 LocalSkillLoader 当前仅解析 `name` 和 `description`，其余字段透传到 `markdown` 中不做处理
- 正文 Markdown 是 Agent 读取到的完整指令内容

**最小 SKILL.md 示例**：
```markdown
---
name: fall-risk-assessment
description: Use when assessing fall risk for elderly patients aged 60+. Triggers on admission screening, mobility complaints, or post-fall evaluation.
---

# 老年跌倒风险评估

## When to Use
- 60岁以上老年患者入院/入住养老院时
- 患者主诉步态不稳、头晕、近期跌倒史
- 术后首次下床活动前

## Core Protocol
1. 询问跌倒史（过去1年）
2. 使用Morse跌倒量表评估
3. 检查用药（镇静剂/降压药/利尿剂）
4. 评估环境危险因素
5. 给出风险等级和干预建议
```

### 2.2 SkillLoaderBase 基类

**位置**：`src/agentscope/skill/_base.py`
**导入**：`from agentscope.skill import SkillLoaderBase`

```python
class SkillLoaderBase(ABC):
    @abstractmethod
    async def list_skills(self) -> list[Skill]:
        """返回该加载器可提供的所有 Skill 列表"""
```

**自定义加载器示例**（如从 GerClaw Skill Registry 远程加载）：
```python
class RegistrySkillLoader(SkillLoaderBase):
    async def list_skills(self) -> list[Skill]:
        # 从远程注册中心拉取技能元数据+内容，构造 Skill 对象返回
        skills = await fetch_skills_from_registry()
        return [Skill(name=s["name"], description=s["description"],
                      dir=s.get("local_dir", ""), markdown=s["content"],
                      updated_at=s["updated_at"]) for s in skills]
```

### 2.3 LocalSkillLoader 本地目录加载器

**位置**：`src/agentscope/skill/_local_loader.py`
**导入**：`from agentscope.skill import LocalSkillLoader`

```python
class LocalSkillLoader(SkillLoaderBase):
    def __init__(self, directory: str, scan_subdir: bool = False) -> None:
        """
        Args:
            directory: 技能根目录绝对路径
            scan_subdir: 是否递归扫描子目录（默认 False，仅加载根目录 SKILL.md）
        """
```

**关键行为**：
- 扫描目录中所有包含 `SKILL.md` 的子目录
- 基于文件 mtime 实现缓存：文件未修改时直接返回缓存 Skill 对象
- 文件修改后下次 `list_skills()` 自动重新加载（热更新）
- 缺少 `name`/`description` 的 SKILL.md 会被跳过并打印 warning
- 并发加载所有 SKILL.md（`asyncio.gather`）

**典型用法**：
```python
from agentscope.skill import LocalSkillLoader
from agentscope.tool import Toolkit

# 加载 GerClaw 医疗技能目录（含子目录分类：fall_risk/、medication/、nutrition/）
loader = LocalSkillLoader(
    directory="/opt/gerclaw/skills/medical",
    scan_subdir=True,
)
toolkit = Toolkit(skills_or_loaders=[loader])
```

### 2.4 Toolkit 注册 skills_or_loaders 参数

**位置**：`src/agentscope/tool/_toolkit.py`
**导入**：`from agentscope.tool import Toolkit`

`Toolkit.__init__` 的 `skills_or_loaders` 参数接受三种类型混合列表：
1. **`str`（目录路径）**：自动包装为 `LocalSkillLoader(directory=path, scan_subdir=False)`
2. **`Skill` 对象**：直接注册的技能对象
3. **`SkillLoaderBase` 子类实例**：自定义加载器（如 LocalSkillLoader、RegistrySkillLoader）

```python
toolkit = Toolkit(
    tools=[...],                    # 基础工具
    skills_or_loaders=[
        "/path/to/skills",          # str -> 自动 LocalSkillLoader
        my_skill_obj,               # 直接 Skill 对象
        LocalSkillLoader(...),      # 自定义 LocalSkillLoader
        RegistrySkillLoader(...),   # 自定义远程加载器
    ],
)
```

**技能提示词获取**：
```python
instructions = await toolkit.get_skill_instructions()
# 返回 XML 格式的技能列表片段，可附加到 system prompt
# 无技能时返回 None
```

### 2.5 SkillViewer 内置工具（工具名 "Skill"）

**位置**：`src/agentscope/tool/_builtin/_skill.py`
**导入**：`from agentscope.tool import SkillViewer`（一般不需要手动导入，Toolkit 自动注册）

当 Toolkit 注册了任意技能时，会自动注册一个名为 `"Skill"` 的内置工具：

```json
{
  "type": "function",
  "function": {
    "name": "Skill",
    "description": "Retrieve a skill within the conversation...",
    "parameters": {
      "type": "object",
      "properties": {
        "skill": {"type": "string", "description": "The exact name of the skill to view."}
      },
      "required": ["skill"]
    }
  }
}
```

**Agent 调用方式**：
1. 模型从 system prompt 中看到可用技能列表（仅 name + description）
2. 模型决定使用某个技能时，调用 `Skill` 工具传入 `{"skill": "fall-risk-assessment"}`
3. SkillViewer 读取对应 SKILL.md 全文返回给模型
4. 模型按照指令步骤，使用已有工具执行任务

**错误处理**：技能不存在时返回 `"SkillNotFoundError: Skill 'xxx' not found."`

### 2.6 自定义 Middleware 实现审计/计数/限流

**位置**：`src/agentscope/middleware/_base.py`
**导入**：`from agentscope.middleware import MiddlewareBase`

MiddlewareBase 提供 5 个拦截钩子：

| 钩子 | 模式 | 拦截阶段 | 适合场景 |
|------|------|---------|---------|
| `on_reply` | 洋葱模型 | 整个回复流程 | 全局初始化/清理、Reply 级统计 |
| `on_reasoning` | 洋葱模型 | 推理/模型调用阶段 | 注入 HintBlock、强制 tool_choice |
| `on_acting` | 洋葱模型 | 单个工具执行 | **工具调用审计、计数、限流、权限检查** |
| `on_model_call` | 洋葱模型 | 原始模型 API 调用 | 模型层缓存、日志、费用统计 |
| `on_system_prompt` | 管道模式 | system prompt 转换 | 动态注入安全提示 |

**`on_acting` 钩子签名**（最常用于 Skill 审计）：
```python
async def on_acting(
    self,
    agent: Agent,
    input_kwargs: dict,   # 含 tool_call: ToolCallBlock（已通过权限校验）
    next_handler: Callable[..., AsyncGenerator],
) -> AsyncGenerator:
    """拦截工具执行。tool_call.name 为工具名，tool_call.input 为 JSON 字符串参数。"""
```

**注册中间件到 Agent**：
```python
agent = Agent(
    ...,
    middlewares=[
        SkillAuditMiddleware(),
        SkillRateLimitMiddleware(max_calls_per_hour=10),
    ],
)
```

**状态存储**：中间件状态保存在 `agent.state.middle_context[middleware_key]`，跨 HITL 中断和恢复持久化，ReplyEndEvent 时清理。中间件实例本身应无状态，可安全共享给多个 Agent。

### 2.7 skill_instruction_template 模板定制

**位置**：`src/agentscope/tool/_toolkit.py`（常量 `DEFAULT_SKILL_INSTRUCTION`）

Toolkit 构造时可传入自定义 Jinja2 模板，定制注入 system prompt 的技能列表片段：

```python
MEDICAL_SKILL_TEMPLATE = """<medical-skills>
你是GerClaw老年医疗AI平台的医生助手。以下是可用的临床技能SOP。

⚠️ 医疗安全红线：
- 所有技能输出为AI辅助建议，须经执业医师确认
- 检测到急症信号（胸痛/呼吸困难/意识障碍/FAST阳性）时立即建议拨打120
- 处方类决策必须获得医生审批后方可执行

# 可用临床技能：
{% for skill in skills %}
<skill>
<name>{{ skill.name }}</name>
<description>{{ skill.description }}</description>
<risk_level>{{ skill.risk_level }}</risk_level>
</skill>
{% endfor %}

使用方式：调用 `{{ skill_viewer }}` 工具传入技能名称，读取完整SOP后按步骤执行。
</medical-skills>
"""

toolkit = Toolkit(
    skills_or_loaders=[loader],
    skill_instruction_template=MEDICAL_SKILL_TEMPLATE,
)
```

**模板可用变量**：
- `skills`：技能列表，每个元素有 `.name`、`.description`、`.dir` 属性
- `skill_viewer`：内置 Skill 查看器工具名（即 `"Skill"`）

> 注意：默认模板中的技能对象只有 name/description/dir 三个属性。如果需要在模板中使用自定义字段（如 risk_level），需要自行扩展 SkillLoader 或在加载后扩充 Skill 对象。

---

## 3. 源码路径索引

| 文件 | 路径 | 说明 |
|------|------|------|
| Skill 数据类 + SkillLoaderBase | `src/agentscope/skill/_base.py` | Skill dataclass 和加载器抽象基类 |
| LocalSkillLoader | `src/agentscope/skill/_local_loader.py` | 本地目录加载器，含 mtime 缓存、子目录扫描 |
| skill 包入口 | `src/agentscope/skill/__init__.py` | 导出 Skill, SkillLoaderBase, LocalSkillLoader |
| Toolkit（技能注册主入口） | `src/agentscope/tool/_toolkit.py` | 含 DEFAULT_SKILL_INSTRUCTION、技能注册、SkillViewer 自动挂载、get_skill_instructions |
| SkillViewer 内置工具 | `src/agentscope/tool/_builtin/_skill.py` | "Skill" 工具实现，读取 SKILL.md 全文 |
| ToolBase / ToolMiddlewareBase | `src/agentscope/tool/_base.py` | 工具协议基类（含工具级中间件，区别于 Agent 级中间件） |
| MiddlewareBase | `src/agentscope/middleware/_base.py` | Agent 级中间件基类，5 个钩子定义 |
| ReplyBudgetControlMiddleware | `src/agentscope/middleware/_budget.py` | 预算控制中间件（on_reply + on_reasoning 示例） |
| RAGMiddleware | `src/agentscope/middleware/_rag.py` | 检索增强中间件 |
| TracingMiddleware | `src/agentscope/middleware/_tracing/` | 调用链追踪中间件 |
| TTSMiddleware | `src/agentscope/middleware/_tts_middleware.py` | 语音合成中间件 |
| Mem0Middleware | `src/agentscope/middleware/_longterm_memory/_mem0/_middleware.py` | 长期记忆中间件 |
| StateChangeMiddleware | `src/agentscope/app/middleware/_state_change_middleware.py` | 应用层状态变更检测 |
| InboxMiddleware | `src/agentscope/app/middleware/_inbox_middleware.py` | 收件箱消息注入 |
| ToolOffloadMiddleware | `src/agentscope/app/middleware/_tool_offload_middleware.py` | 长时工具后台卸载 |

---

## 4. 官方示例参考

| 示例/测试 | 路径 | 演示内容 |
|----------|------|---------|
| skill_loader_test.py | `tests/skill_loader_test.py` | LocalSkillLoader 基本用法：根目录加载、子目录扫描、mtime 缓存机制、文件修改后热更新 |
| toolkit_skill_test.py | `tests/toolkit_skill_test.py` | Toolkit 注册技能的三种方式（str/Skill/Loader）、get_skill_instructions 输出格式、SkillViewer 调用成功/失败、ToolGroup 技能激活/隐藏 |

**关键测试模式（来自 toolkit_skill_test.py）**：

```python
# 三种注册方式混合使用
toolkit = Toolkit(
    skills_or_loaders=[
        skill_dir,                           # str 路径
        MockSkillLoader([loader_skill]),     # 自定义加载器
        direct_skill,                        # 直接 Skill 对象
    ],
)

# 获取技能提示词（附加到 system prompt）
instructions = await toolkit.get_skill_instructions()

# 调用 SkillViewer 读取技能内容
tool_call = ToolCallBlock(
    id="call_1",
    name="Skill",
    input=json.dumps({"skill": "my_skill"}),
)
state = AgentState()
async for result in toolkit.call_tool(tool_call, state):
    if isinstance(result, ToolResponse):
        print(result.content[0].text)  # SKILL.md 全文
```

---

## 5. 文档链接

| 文档 | 位置 | 内容 |
|------|------|------|
| Tool/Skill/MCP 章节（1.8 Skill 节） | `agentscope文档离线/group_B5-8.md` 第 497-552 行 | Skill 概念、注册方式、工作原理 |
| Tool Group 章节 | `agentscope文档离线/group_B5-8.md` 第 554-607 行 | ToolGroup 中技能的分组激活/停用 |
| 源码映射（Skill/Middleware 节） | `agentscope文档离线/source_map_tools.md` 第 537-559 行（SkillViewer）、第 851-1162 行（Middleware） | 源码路径索引、API 签名 |

---

## 6. GerClaw 适配要点

### 6.1 医疗 Skill 设计规范

基于 GerClaw 需求文档的双层 Schema 设计，在 AgentScope SKILL.md 基础上扩展医疗字段：

**SKILL.md Frontmatter 必须包含的医疗字段**：
```yaml
---
name: fall-risk-assessment          # 技能唯一标识（kebab-case）
description: "Use when assessing fall risk for elderly patients..."  # CSO 原则：只写触发条件
display_name: "老年跌倒风险评估"     # 中文名
version: "1.2.0"                    # 语义化版本
category: "健康评估"                 # 分类标签
author: "GerClaw Medical Team"

# === 医疗必填字段 ===
medical:
  applicable_population:
    age_range: ">=60"
    conditions: ["fall_risk_screening", "mobility_assessment"]
    contraindications: ["pediatric", "acute_trauma"]  # 禁忌症
  risk_level: "medium"              # low | medium | high | critical
  requires_approval: false          # 是否需要审批
  approval_role: "nurse"            # physician | pharmacist | nurse | admin | none
  # 适应症（SKILL.md 正文 When to Use 章节详细列出）
  # 禁忌症（SKILL.md 正文 Do NOT use when 章节详细列出）
  # 操作步骤（SKILL.md 正文 Core Protocol 章节步骤化）
  compliance:
    disclaimer: "本工具为辅助决策工具，不替代医生临床判断。"
    evidence_level: "B"
    guideline_references:
      - "Morse Fall Scale (MFS)"
      - "中国老年人跌倒风险评估专家共识2023"
---
```

**SKILL.md 正文结构（医疗版）**：
1. `# 技能名称`
2. `## Overview` — 1-2 句话核心原则
3. `## When to Use` — 触发场景列表 + `**Do NOT use when:**` 禁忌症
4. `## Medical Safety Guardrails` — 安全红线、必须转诊/升级的情况
5. `## Core Protocol` — 标准操作步骤（前置检查→评估→决策→输出→记录）
6. `## Quick Reference Table` — 常见场景速查表
7. `## Examples` — 1 个高质量完整示例
8. `## Escalation Rules` — 升级到医生/急诊的触发条件
9. `## References` — 临床指南引用

**关键原则**：
- **CSO 原则**：`description` 字段只写触发条件（"Use when..."），不写工作流步骤，防止模型走捷径不读正文
- **Token 效率**：高频 SKILL.md 正文控制在 200 词以内，重型参考资料分文件存放在技能目录
- **安全红线前置**：Medical Safety Guardrails 章节必须放在正文靠前位置

### 6.2 推荐配置

```python
from agentscope.skill import LocalSkillLoader
from agentscope.tool import Toolkit

# 医疗技能目录组织结构：
# /opt/gerclaw/skills/
#   ├── assessment/           # 评估类（跌倒、营养、认知）
#   │   ├── fall-risk/SKILL.md
#   │   └── nutrition/SKILL.md
#   ├── medication/           # 用药类（相互作用、剂量调整）
#   │   └── drug-interaction/SKILL.md
#   ├── emergency/            # 急救类（胸痛、卒中）
#   │   └── stroke-fast/SKILL.md
#   └── education/            # 健康宣教类
#       └── diet-advice/SKILL.md

medical_loader = LocalSkillLoader(
    directory="/opt/gerclaw/skills",
    scan_subdir=True,   # 递归扫描子目录分类
)

toolkit = Toolkit(
    tools=[...],  # Bash/Read/Write/自定义医疗工具
    skills_or_loaders=[medical_loader],
    skill_instruction_template=MEDICAL_SKILL_TEMPLATE,  # 加入医疗安全提示
)
```

**技能分组建议**（使用 ToolGroup）：
```python
from agentscope.tool import ToolGroup

toolkit = Toolkit(
    tools=[basic_tools...],
    tool_groups=[
        ToolGroup(
            name="emergency",
            description="急救技能组（胸痛/卒中/跌倒急救）",
            instructions="检测到急症信号时立即激活，优先使用急救技能。",
            skills_or_loaders=[LocalSkillLoader("/opt/gerclaw/skills/emergency", scan_subdir=True)],
        ),
        ToolGroup(
            name="medication",
            description="用药安全技能组",
            instructions="涉及处方/用药建议时激活，所有建议需经医生确认。",
            skills_or_loaders=[LocalSkillLoader("/opt/gerclaw/skills/medication", scan_subdir=True)],
        ),
    ],
)
```

### 6.3 风险与应对

| 风险 | 说明 | 应对措施 |
|------|------|---------|
| **Skill 版本管理** | AgentScope 原生 Skill 无版本字段，SKILL.md 被直接覆盖 | 在 Frontmatter 增加 `version` 字段；用 Git 管理技能目录；通过自定义 RegistrySkillLoader 实现版本查询和回滚 |
| **过期 Skill 禁用** | LocalSkillLoader 会加载目录中所有 SKILL.md，无法标记禁用 | 1) 在 Frontmatter 增加 `enabled: false` 字段，自定义 Loader 过滤；2) 将过期 Skill 移到 `_disabled/` 目录；3) Middleware 层拦截调用已禁用 Skill |
| **Skill 热更新缓存** | LocalSkillLoader 基于 mtime 缓存，文件更新后下次 list_skills 自动重载 | 生产环境更新 Skill 后，需触发 toolkit 重新获取技能指令；高风险 Skill 更新建议走灰度发布 |
| **模型绕过 Skill 直接回答** | 模型可能不调用 Skill 工具就直接回答医学问题 | 1) system prompt 强调必须使用 Skill；2) Middleware 检测高风险领域对话未使用 Skill 时注入 HintBlock 提醒；3) 关键词触发强制 Skill 使用 |
| **Skill 内容注入/篡改** | SKILL.md 是本地文件，若被篡改可能导致危险指令 | 1) 技能目录设置只读权限；2) 对高风险 Skill 做数字签名校验；3) Middleware 审计日志记录所有 Skill 查看行为 |
| **并发安全** | 多个 Agent 共享同一个 Toolkit/LocalSkillLoader | LocalSkillLoader 使用 asyncio.gather 并发加载，缓存读写在事件循环内是安全的；Middleware 状态存储在 agent.state.middle_context 中，天然隔离 |
| **审批流程缺失** | AgentScope Skill 无原生审批机制 | 通过自定义 Middleware 在 on_acting 中拦截高风险工具调用，对接 GerClaw 审批系统（医生审批后才放行 next_handler） |

---

## 7. 可运行示例指引

本模块配套 2 个可运行 Python 示例，位于 `agentscope-examples/06_skill_evolution/` 目录：

| 示例文件 | 演示内容 |
|---------|---------|
| `custom_medical_skill.py` | 创建"老年跌倒风险评估"Skill：用 tempfile 临时创建 SKILL.md 和相关资源文件 → LocalSkillLoader 加载 → 获取技能指令 → Agent（或手动模拟）通过 SkillViewer 查看技能说明 → 执行评估流程。支持 DashScope 模型真实推理（需 `DASHSCOPE_API_KEY`），无 Key 时演示本地流程。 |
| `skill_middleware.py` | 自定义 Middleware 继承 MiddlewareBase：实现 `on_acting` 钩子拦截工具调用，完成 3 个功能——(1) Skill 使用计数统计、(2) 审计日志（谁在何时调用了哪个技能/工具）、(3) 使用频率限制（超过阈值拒绝调用）。配合跌倒风险 Skill 演示完整流程。 |

**运行方式**：
```bash
# 示例 1：自定义医疗 Skill
cd agentscope-examples/06_skill_evolution
export DASHSCOPE_API_KEY="your-key"   # 可选，无 Key 时跳过模型推理
python custom_medical_skill.py

# 示例 2：Skill 中间件审计/限流
python skill_middleware.py
```

**依赖要求**：
- agentscope（已安装在开发环境）
- Python 3.10+
- `aiofiles`、`python-frontmatter`（agentscope 依赖，已包含）
- DashScope API Key（可选，用于真实模型推理演示）
