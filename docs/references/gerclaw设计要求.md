# GerClaw 系统设计要求文档

---

## 1. 项目概述

### 1.1 项目定位

**GerClaw** 是一款面向老年患者与老年科医生的 Web 端 AI 双向诊疗平台，致力于提供专业、便捷、智能的医疗健康服务。

### 1.2 核心功能

| 端口 | 功能模块 | 说明 |
|------|---------|------|
| 医生端 | 辅助诊断与评估 | 辅助医生进行疾病诊断和健康评估 |
| 医生端 | 老年综合评估 (CGA) | 提供标准化的老年综合评估工具 |
| 医生端 | 用药审查 | 检查用药合理性、药物相互作用 |
| 患者端 | 语音对话采集 | 语音优先的简明对话方式采集健康信息 |
| 患者端 | 健康画像管理 | 管理和维护个人健康档案 |
| 通用 | 五大处方生成 | 药物处方、运动处方、营养处方、心理处方、康复处方 |
| 通用 | 访客/账号模式 | 所有人先到登录/注册入口；可显式选择无账号游客进入患者端，账号模式按角色进入独立持久化工作台 |

### 1.3 系统级别要求

本系统定位为企业级生产系统，需满足以下要求：

- **性能指标**：支撑日均万次活跃用户访问
- **可用性**：高可用架构，确保服务稳定运行
- **并发能力**：支持高并发场景处理
- **数据安全**：严格的数据加密与隐私保护机制
- **医疗合规**：准确性优先、可解释性、符合医疗行业合规要求

---

## 2. 技术架构

### 2.1 技术栈选型

| 层级 | 技术方案 | 说明 |
|------|---------|------|
| 前端框架 | Next.js 15 + React | 服务端渲染，优化首屏加载 |
| UI 组件 | Tailwind CSS + ShadCN | 原子化 CSS + 高质量组件库 |
| AI 集成 | Vercel AI SDK | 流式输出、模型调用封装 |
| 后端框架 | FastAPI | 高性能异步 Python 框架 |
| 智能体框架 | AgentScope | 多智能体编排与协作 |
| 部署平台 | ModelScope | Docker 容器化部署（需遵循 `modelscope-studio` 技能规范） |

#### 2.1.1 技术选型优先级准则

> ⚠️ **核心原则：本文档（gerclaw设计要求.md）是系统设计的最高准则。** 所有技术实现必须严格遵循本文档中定义的功能需求、交互规范和质量标准。

**技术选型三层优先级：**

```
第一层：gerclaw设计要求.md（本文档）
  → 系统功能的"做什么"和"做到什么标准"，是不可违反的需求基准

第二层：agentscope框架总览（agentscope参考/00_总览.md）
  → 技术实现的"怎么做"，优先使用 AgentScope 框架已提供的能力

第三层：技术选型推荐（gerclaw前期调研/GerClaw_技术选型推荐.md）
  → 仅当 AgentScope 框架预览中给出的功能实现不能满足本文档的设计要求时，
    才参考技术选型推荐中的替代方案来补齐缺失功能
```

**判断流程：**
1. 阅读本文档对应模块的设计要求，明确功能需求和质量标准
2. 查阅 `agentscope参考/` 下对应模块的参考文档，确认 AgentScope 是否已提供满足需求的能力
3. 若 AgentScope 能力满足需求 → **直接使用 AgentScope 实现**，不得引入额外技术栈
4. 若 AgentScope 能力存在缺口 → 参考技术选型推荐中的对应方案，选择最轻量的补充技术补齐缺口
5. 引入任何 AgentScope 之外的技术时，必须在代码注释和设计文档中说明：**为什么 AgentScope 不满足需求、引入了什么替代方案、对系统架构的影响**

**禁止行为：**
- 禁止跳过 AgentScope 直接使用技术选型推荐中的方案（如：AgentScope 已有 RAGMiddleware，不得直接引入 LlamaIndex）
- 禁止因为"更熟悉"某技术而绕过 AgentScope 的对应能力
- 禁止为了"看起来更先进"而引入不必要的技术栈

---

## 3. 界面设计规范（对齐 Trae Work）

> **设计参考基准**：前端交互与视觉效果对标 Trae Work（AI IDE 产品），保持一致的布局逻辑、交互模式和智能体执行可视化体验。

### 3.1 整体布局结构

采用**三栏可折叠布局**：

| 区域 | 位置 | 展开宽度 | 折叠宽度 | 说明 |
|------|------|---------|---------|------|
| 左侧边栏 | 左侧 | 260-280px | 60-70px | 导航、会话列表、功能入口，支持完全折叠为图标栏 |
| 主聊天区 | 中间 | 自适应（弹性） | 自适应 | 欢迎页、消息列表、输入框区域 |
| 右侧动态面板 | 右侧 | 320-400px | 0px（隐藏） | 按需展开：技能管理、处方预览、CGA评估、文件预览、引用详情等 |

**布局特性**：
- 侧边栏折叠时只显示图标，hover 显示 tooltip
- 右侧面板默认隐藏，功能触发时自动展开，关闭时自动收起
- 响应式设计：窄屏设备（平板/手机）自动收起两侧面板，优先展示聊天区
- 支持深色/浅色双主题切换，默认跟随系统偏好

### 3.2 左侧边栏设计

#### 3.2.1 顶部区域（自上而下）

| 序号 | 组件 | 样式与交互 |
|------|------|-----------|
| 1 | 系统标识区 | 系统图标 + "GerClaw" 文字 + 当前模式标签（医生端/患者端）<br>折叠状态下只显示图标 |
| 2 | 侧边栏控制按钮 | 位于标识区右侧，控制展开/折叠状态 |
| 3 | 新建对话按钮 | **突出主按钮样式**（带背景色，视觉权重最高），点击立即创建新会话<br>折叠状态下显示为 + 图标按钮 |
| 4 | 历史搜索框 | 位于新建按钮下方，带搜索图标，输入关键词实时过滤历史会话列表<br>折叠状态下隐藏 |
| 5 | 历史对话列表 | - **游客模式**：仅显示本次浏览器会话的对话；退出或下次进入不恢复，服务端仍可按隐私规则保留 Trace/Bad Case<br>- **账号模式**：按时间自动分组（今天/昨天/最近7天/更早），每组有标题分隔<br>- **会话项交互**：悬停显示操作按钮（重命名、删除、固定/收藏）<br>- 点击会话直接切换，保留完整上下文<br>- 折叠状态下只显示最近会话的图标 |
| 6 | 技能管理入口 | 历史列表下方，点击后**在右侧动态面板展开**技能管理界面，支持：<br>- 浏览系统预置技能<br>- 上传自定义技能（支持 `skill.md` 文件或包含 `skill.md` 的压缩包，系统自动解压安装）<br>- 通过自然语言描述生成自定义技能 |

#### 3.2.2 底部区域（自下而上）

| 序号 | 组件 | 样式与交互 |
|------|------|-----------|
| 1 | 用户信息区 | 用户头像（医生/患者/访客，根据身份动态切换）<br>点击展开菜单：账号信息（上传头像、修改用户名、修改密码）、帮助文档（子页面HTML渲染）、设置、退出登录<br>折叠状态下只显示头像 |
| 2 | 工作台切换 | 仅管理员可在管理、患者和医生工作台间切换；患者账号只能进入患者端，医生账号只能进入医生端，游客只能进入患者端。切换不授予跨患者数据或临床权限 |
| 3 | 老年模式开关 | 仅患者端显示，**默认开启**<br>切换后即时生效（不刷新页面），适老化调整详见 13.7 节 |
| 4 | 主题切换按钮 | 切换深色/浅色主题，即时生效 |

### 3.3 主聊天区设计

#### 3.3.1 欢迎页/空状态（新会话）

新会话时显示**完整欢迎页**：
- 中央区域：GerClaw Logo + 适配备选问候语（医生端/患者端不同）
- 功能快捷入口卡片：五大处方生成、老年综合评估、用药审查、查看健康画像等
- 示例提示词：根据当前模式（医生/患者）展示 3-4 个典型问题，点击直接发送
- 老年模式：字体放大，按钮更大，提示更明确

#### 3.3.2 消息展示

- **用户消息**：靠右对齐，气泡带主色调背景，右侧显示用户头像
- **AI 消息**：靠左对齐，气泡浅色/透明背景，左侧显示 GerClaw 头像
- **消息间距**：消息之间有适当间距，长消息自动滚动
- **Markdown 渲染**：完整支持 Markdown，包括代码块语法高亮+复制按钮+语言标签、表格、列表、引用、标题等，流式输出时实时渲染
- **医疗循证引用**：正文引用处显示 [1][2] 上标角标，点击角标展开引用详情卡片（标题、摘要、链接），右侧面板可查看所有引用列表
- **消息操作**：每条消息悬停时右上角显示操作按钮：
  - 复制（一键复制内容）
  - 重新生成（仅 AI 消息）
  - 语音朗读（TTS 播放，按钮变为暂停状态，显示播放进度）
  - 导出（针对医疗报告/评估结果）
- **智能滚动**：AI 回复时自动滚动到底部；用户手动上滚后不强制滚动，显示"回到底部"悬浮按钮

#### 3.3.3 智能体执行过程可视化

所有执行步骤实时可视化展示，对齐 Trae Work 体验：

| 可视化项 | 展示方式 | 交互细节 |
|---------|---------|---------|
| **思考过程** | 可折叠"思考过程"区块，浅灰/低对比度背景 | 默认折叠，有"思考中..."状态动画；点击展开查看完整推理过程 |
| **工具调用** | 独立卡片组件，工具图标+名称+状态徽章 | - 状态：运行中（旋转动画）→ 完成（绿色✓）→ 失败（红色✗）<br>- 默认折叠，点击展开显示格式化 JSON 参数 + 执行结果<br>- 显示执行耗时<br>- 失败状态提供"重试"按钮 |
| **多步骤流程** | 垂直时间线/步骤列表 | - 每个步骤：图标+名称+状态+耗时<br>- 步骤间有垂直连接线<br>- 当前执行步骤高亮动画<br>- 已完成打勾，失败标红（支持重试） |
| **联网搜索结果** | 独立卡片式展示 | 每条结果：标题+来源 favicon+摘要+链接；AI 正文用 [1][2] 角标引用；点击链接可在右侧面板预览 |
| **文档解析状态** | 文件标签+工具卡片双重反馈 | 上传后标签显示状态：上传中→解析中→完成/失败；解析完成自动作为上下文；失败提示+重试 |
| **流式输出** | 打字机效果 | 末尾闪烁光标，Markdown 边输出边渲染；生成过程中显示"停止生成"按钮 |

### 3.4 输入框区域设计

采用 **Trae 式内嵌式输入框**布局：

```
[标签区域：已加载技能/已上传文件（可点击×移除）]
┌─────────────────────────────────────────────────────────┐
│ [📎] [⚡技能] [💊处方] [📋评估]  输入文本...        [🎤/✈️] │
└─────────────────────────────────────────────────────────┘
[提示文字/免责声明]
```

| 位置 | 组件 | 交互说明 |
|------|------|---------|
| **标签区域**（输入框上方） | 已加载技能标签、已上传文件标签 | - 技能标签显示技能名，右侧×可移除<br>- 文件标签显示文件名+类型图标+大小，图片显示缩略图，右侧×可移除<br>- 标签区域可横向滚动 |
| **输入框左侧** | 功能按钮组（内嵌） | - 📎 文件上传：支持点击选择或拖拽文件到聊天区（拖拽时有高亮提示）<br>- ⚡ 技能：点击弹出技能列表选择加载<br>- 💊 处方：点击启动五大处方生成流程<br>- 📋 评估：点击启动 CGA 老年综合评估 |
| **输入框中间** | 文本输入区 | - 支持多行输入，自动增高（有最大高度限制，超出后内部滚动）<br>- Placeholder 根据模式（医生/患者/老年模式）显示不同提示文案<br>- 键盘快捷键：Enter 发送，Shift+Enter 换行 |
| **输入框右侧** | 发送/语音/停止按钮 | - 默认状态：🎤 麦克风图标（点击开始语音输入）<br>- 激活状态：有文本/文件/技能时切换为 ✈️ 纸飞机图标（发送）<br>- AI 生成中：显示 ⏹ 停止按钮（中断生成） |

#### 3.4.1 语音交互细节

**语音输入（ASR）**：
- 交互方式：点击开始 → 点击停止（非长按）
- 录音状态反馈：实时波形动画 + 录音时长计时
- 识别过程：实时转写预览，边说边显示识别结果
- 录音前自动请求麦克风权限，拒绝时给出明确引导

**语音合成（TTS）播放**：
- 每条 AI 消息右上角内嵌播放/暂停按钮
- 播放时显示简单进度指示
- 老年模式默认开启自动播放（可关闭）

### 3.5 右侧动态面板

右侧面板默认隐藏，以下场景自动展开：

| 触发场景 | 面板内容 |
|---------|---------|
| 点击技能管理入口 | 技能浏览、上传、自然语言生成界面 |
| 启动五大处方生成 | 处方生成向导/表单 → 最终报告预览（支持导出 PDF/Word/Markdown） |
| 启动 CGA 评估 | 评估量表展示：题目+语音朗读+选项卡片+进度条（如 3/20） |
| 点击文件/引用链接 | 文件预览、引用来源详情 |
| 查看健康画像 | 患者健康档案、历史数据、评估记录 |
| 点击引用角标 | 当前消息的所有引用来源列表 |

- 面板顶部有关闭按钮，点击收起面板
- 宽度可拖拽调整（320-500px 范围）
- 面板内支持滚动查看长内容

---

## 4. 核心功能模块

### 4.1 通用对话功能

系统基础对话功能交互体验对齐 Trae Work，包含以下能力：

**输入支持**：
- 文本输入（多行，自动增高）
- 语音输入（点击式开始/停止，实时波形+转写预览）
- 文件上传（拖拽或点击，支持图片/PDF/Word/Markdown/文本，图片多模态理解）
- 技能加载（点击技能按钮选择预置/自定义技能，输入框上方显示标签）
- 快捷功能入口（输入框左侧：文件、技能、处方、评估）

**消息展示**：
- 用户消息右对齐（主色调气泡），AI 消息左对齐（浅色气泡）
- 完整 Markdown 渲染：代码块（语法高亮+复制按钮+语言标签）、表格、列表、引用、标题等
- 医疗循证引用：正文 [1][2] 上标角标，点击展开引用卡片，右侧面板查看引用列表
- 每条消息悬停显示操作按钮：复制、重新生成（仅AI）、语音朗读、导出（医疗报告）

**智能体执行过程**：
- 思考过程：可折叠"思考过程"区块（默认折叠，低对比度背景）
- 工具调用：独立卡片，工具图标+名称+状态徽章（运行中旋转→完成✓→失败✗），展开显示JSON参数+结果+耗时+重试
- 多步骤流程：垂直时间线，每步图标+名称+状态+耗时，当前步高亮动画
- 搜索/文档：卡片式展示，AI正文角标引用，点击右侧面板预览
- 流式输出：打字机效果，末尾光标闪烁，实时渲染Markdown，支持停止生成

**上下文管理**：
- 会话自动保存（账号模式）
- 支持新建对话、切换历史会话、重命名、删除、固定/收藏
- 已加载技能/已上传文件显示为标签，可单独移除
- 多轮对话上下文自动管理

**结果处理**：支持复制、语音朗读、导出（PDF/Word/Markdown）、重新生成、删除对话

### 4.2 智能体模型调用规范

#### 4.2.1 调用协议

支持三种调用协议，通过 `model_protocol` 配置项指定：

| 协议 | 适用模型 | AgentScope 模型类 | AgentScope 凭证类 |
|------|---------|-------------------|-------------------|
| `openai` | GPT-4o、Qwen（OpenAI 兼容模式）、DeepSeek、Moonshot 等 | `OpenAIChatModel` | `OpenAICredential` |
| `dashscope` | Qwen（原生模式）、通义千问系列 | `DashScopeChatModel` | `DashScopeCredential` |
| `anthropic` | Claude 系列、Qwen（Anthropic 兼容模式） | `AnthropicChatModel` | `AnthropicCredential` |

**通用要求：**
- 输出模式：流式输出 (Streaming)
- 多模态：支持图片 + 文本混合输入
- 思维链：选用的模型均需支持思考模式（thinking）
- 工具调用：支持 function calling / tool_use

##### AgentScope 模式（推荐）

AgentScope 通过 Credential + ChatModel 的组合统一三种协议，切换协议只需更换 Credential 和 Model 类：

```python
import os
from agentscope.model import OpenAIChatModel, DashScopeChatModel, AnthropicChatModel
from agentscope.credential import OpenAICredential, DashScopeCredential, AnthropicCredential

# OpenAI 协议
model_openai = OpenAIChatModel(
    credential=OpenAICredential(api_key=os.environ["OPENAI_API_KEY"]),
    model="gpt-4o",
    stream=True,
)

# DashScope 协议
model_dashscope = DashScopeChatModel(
    credential=DashScopeCredential(api_key=os.environ["DASHSCOPE_API_KEY"]),
    model="qwen-plus",
    stream=True,
)

# Anthropic 协议
model_anthropic = AnthropicChatModel(
    credential=AnthropicCredential(api_key=os.environ["ANTHROPIC_API_KEY"]),
    model="claude-sonnet-4-20250514",
    stream=True,
)
```

流式调用统一接口：

```python
import asyncio
from agentscope.message import UserMsg

async def stream_chat(model, prompt):
    msgs = [UserMsg(name="user", content=prompt)]
    async for chunk in await model(msgs):
        if chunk.is_last:
            print("Final:", chunk.content)  # 完整累积内容
        else:
            print("Delta:", chunk.content)  # 仅增量

asyncio.run(stream_chat(model_openai, "你好"))
```

每个 `ChatResponse` 包含若干 content block：`TextBlock`（文本）、`ThinkingBlock`（思维链）、`ToolCallBlock`（工具调用）、`DataBlock`（数据）。

##### 原生 API 流式调用（三种协议对比）

**OpenAI 协议：**

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)
completion = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"}
    ],
    stream=True,
    stream_options={"include_usage": True}
)
for chunk in completion:
    print(chunk.model_dump_json())
```

**DashScope 协议：**

```python
import os
import dashscope
dashscope.base_http_api_url = "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1"

responses = dashscope.Generation.call(
    api_key=os.getenv('DASHSCOPE_API_KEY'),
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "you are a helpful assistant"},
        {"role": "user", "content": "你是谁？"}
    ],
    result_format='message',
    stream=True,
    incremental_output=True
)
for response in responses:
    print(response)
```

**Anthropic 协议：**

```python
import os
import anthropic

client = anthropic.Anthropic(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/apps/anthropic",
)
stream = client.messages.create(
    model="qwen3.7-plus",
    max_tokens=1024,
    stream=True,
    messages=[{"role": "user", "content": "请简单介绍一下人工智能。"}],
    thinking={"type": "disabled"},
)
for chunk in stream:
    if chunk.type == "content_block_delta":
        if hasattr(chunk.delta, 'text'):
            print(chunk.delta.text, end="", flush=True)
```

**curl 对照：**

```bash
# OpenAI 协议
curl -X POST "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions" \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","messages":[{"role":"user","content":"你是谁？"}],"stream":true}'

# DashScope 协议
curl -X POST "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/text-generation/generation" \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-DashScope-SSE: enable" \
  -d '{"model":"qwen-plus","input":{"messages":[{"role":"user","content":"你是谁？"}]},"parameters":{"result_format":"message","incremental_output":true}}'

# Anthropic 协议
curl -X POST "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/apps/anthropic/v1/messages" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $DASHSCOPE_API_KEY" \
  -d '{"model":"qwen3.7-plus","max_tokens":1024,"stream":true,"messages":[{"role":"user","content":"你是谁？"}]}'
```

##### 图像 + 文本多模态输入

**OpenAI 协议（图片 URL）：**

```python
from openai import OpenAI
client = OpenAI(api_key="sk-xxx", base_url="https://.../compatible-mode/v1")

completion = client.chat.completions.create(
    model="qwen-vl-plus",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/image.jpeg"}},
        {"type": "text", "text": "这是什么？"}
    ]}]
)
```

**DashScope 协议（图片 URL）：**

```python
import dashscope
response = dashscope.MultiModalConversation.call(
    api_key="sk-xxx",
    model="qwen-vl-max",
    messages=[{"role": "user", "content": [
        {"image": "https://example.com/image.jpeg"},
        {"text": "这些是什么?"}
    ]}]
)
```

**Anthropic 协议（Base64 图片）：**

```python
import anthropic, base64
client = anthropic.Anthropic(api_key="sk-xxx")
with open("image.jpg", "rb") as f:
    img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
        {"type": "text", "text": "这是什么？"}
    ]}]
)
```

#### 4.2.2 前端页面集成

前端通过 JavaScript 直接调用大模型 API，实现浏览器端流式对话。三种协议均可通过 `fetch` + `ReadableStream` 实现 SSE 流式读取。

**OpenAI 协议（浏览器端流式调用）：**

```html
<!DOCTYPE html>
<html>
<body>
  <div id="output" style="white-space:pre-wrap;border:1px solid #ccc;padding:16px;min-height:200px;"></div>
  <input id="input" placeholder="输入消息..." style="width:80%">
  <button onclick="send()">发送</button>

<script>
const API_KEY = "your-api-key";
const BASE_URL = "https://api.openai.com/v1";

async function send() {
  const prompt = document.getElementById("input").value;
  const output = document.getElementById("output");
  output.textContent = "";

  const response = await fetch(`${BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${API_KEY}`
    },
    body: JSON.stringify({
      model: "gpt-4o",
      messages: [{ role: "user", content: prompt }],
      stream: true
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // 解析 SSE 格式：每行以 "data: " 开头
    const lines = buffer.split("\n");
    buffer = lines.pop(); // 保留未完成的行
    for (const line of lines) {
      if (line.startsWith("data: ") && line !== "data: [DONE]") {
        try {
          const json = JSON.parse(line.slice(6));
          const text = json.choices?.[0]?.delta?.content || "";
          output.textContent += text;
        } catch (e) { /* 忽略解析错误 */ }
      }
    }
  }
}
</script>
</body>
</html>
```

**Anthropic 协议（浏览器端流式调用）：**

```html
<script>
const API_KEY = "your-api-key";

async function sendAnthropic(prompt) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": API_KEY,
      "anthropic-version": "2023-06-01"
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1024,
      stream: true,
      messages: [{ role: "user", content: prompt }]
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const json = JSON.parse(line.slice(6));
          if (json.type === "content_block_delta" && json.delta?.text) {
            document.getElementById("output").textContent += json.delta.text;
          }
        } catch (e) {}
      }
    }
  }
}
</script>
```

**DashScope 协议（浏览器端流式调用）：**

```html
<script>
async function sendDashScope(prompt) {
  const response = await fetch(
    "https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer your-dashscope-key"
      },
      body: JSON.stringify({
        model: "qwen-plus",
        messages: [{ role: "user", content: prompt }],
        stream: true
      })
    }
  );
  // 解析方式与 OpenAI 协议完全相同（DashScope 兼容 OpenAI SSE 格式）
  const reader = response.body.getReader();
  // ... 同上 OpenAI 解析逻辑
}
</script>
```

> **注意**：浏览器端直接调用存在 API Key 暴露风险。生产环境应通过后端代理转发，前端仅与后端通信。

#### 4.2.3 执行过程可视化

前端需可视化展示以下执行信息，**交互体验对齐 Trae Work**，每项均可折叠展开/收起：

| 可视化项 | 数据来源 | 展示方式 | 交互细节（Trae Work 对齐） |
|---------|---------|---------|---------------------------|
| **思维链** (Chain of Thought) | `ThinkingBlock` / `thinking` 字段 | 可折叠"思考过程"区块，浅灰/低对比度背景 | - 默认折叠，显示"思考中..."状态动画<br>- 点击展开查看完整推理过程<br>- 思考完成后区块自动收起（可手动展开查看） |
| **工具调用** | `ToolCallBlock` / `tool_calls` 字段 | 独立卡片组件，工具图标+名称+状态徽章 | - 状态：运行中（旋转动画）→ 完成（绿色✓）→ 失败（红色✗）<br>- 默认折叠，点击展开显示格式化 JSON 参数 + 执行结果<br>- 显示执行耗时<br>- 失败状态提供"重试"按钮 |
| **子智能体加载** | Agent 团队编排过程 | 折叠树形结构，展示主智能体 → 子智能体的调用链 | - 每个子智能体节点显示名称+状态<br>- 展开显示子智能体执行详情<br>- 节点间用连接线表示调用关系 |
| **决策过程** | ReAct 循环的 Thought/Action/Observation | 垂直时间线/步骤列表 | - 每个步骤：图标+名称+状态+耗时<br>- 步骤间有垂直连接线<br>- 当前执行步骤高亮动画<br>- 已完成打勾，失败标红（支持重试） |
| **联网搜索结果** | 搜索工具返回 | 独立卡片式展示 | - 每条结果：标题+来源 favicon+摘要+链接<br>- AI 正文用 [1][2] 角标引用<br>- 点击链接可在右侧面板预览 |
| **文档解析状态** | 文件上传/解析工具 | 文件标签+工具卡片双重反馈 | - 上传后标签显示状态：上传中→解析中→完成/失败<br>- 解析完成自动作为上下文<br>- 失败提示+重试 |
| **流式文本输出** | `TextBlock` / `delta.content` | 打字机效果 | - 末尾闪烁光标<br>- Markdown 边输出边渲染<br>- 生成过程中显示"停止生成"按钮 |

**可视化数据流架构：**

```
后端 Agent (SSE/WebSocket)
    ↓ event: thinking     → 前端渲染思维链折叠块（"思考中..."动画）
    ↓ event: tool_call    → 前端渲染工具调用卡片（运行中旋转状态）
    ↓ event: tool_update  → 前端更新工具卡片状态（参数/进度）
    ↓ event: tool_result  → 前端更新工具结果（完成✓/失败✗，显示耗时）
    ↓ event: agent_start  → 前端渲染子智能体节点
    ↓ event: search_result→ 前端渲染搜索结果卡片
    ↓ event: file_status  → 前端更新文件标签状态
    ↓ event: text_delta   → 前端追加文本（打字机效果，实时Markdown渲染）
    ↓ event: done         → 前端标记完成，收起思考区块，显示消息操作按钮
```

#### 4.2.4 容错机制

实现多模型自动兜底策略。每个智能体配置 `model_preference` 指定主备模型：

| 优先级 | 配置字段 | 行为 |
|--------|---------|------|
| 主模型 | `primary` | 默认使用，失败时自动切换 |
| 备选 1 | `backup1` | 主模型超时/报错时自动切换 |
| 备选 N | `backup2`... | 依次降级 |

切换触发条件：API 超时（>30s）、HTTP 5xx、限频 429、模型不可用。切换时记录日志，恢复后不自动回切。

#### 4.2.5 上下文管理

- 实现上下文窗口管理（根据模型 `context_size` 自动截断/压缩）
- 实现记忆 (Memory) 管理机制（短期对话记忆 + 长期用户画像记忆）



### 4.3 语音模型调用规范

#### 4.3.1 语音识别 (ASR)

- **模型**：mimo-v2.5-asr
- **功能**：将用户语音输入转换为文本，支持中英文自动检测、方言识别（粤语、吴语、闽南语、四川话等）、噪声环境、远场拾音、重叠说话人等复杂声学场景
- **接口地址**：`POST https://api.xiaomimimo.com/v1/chat/completions`（OpenAI 兼容格式）
- **认证方式**：Header `api-key: $MIMO_API_KEY`

**音频格式与限制：**

| 项目 | 说明 |
|------|------|
| 支持格式 | WAV、MP3 |
| 编码方式 | Base64 编码 |
| 大小限制 | Base64 字符串 ≤ 10MB |
| 采样率 | 建议 16kHz 及以上 |

**音频输入方式（二选一）：**
- **Data URL 格式**：`"data": "data:{MIME_TYPE};base64,$BASE64_AUDIO"`
- **纯 Base64 + format 字段**：`"data": "$BASE64_AUDIO", "format": "wav"`

**关键参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `asr_options.language` | string | 语言设置。`auto`（默认，自动检测）、`zh`（中文）、`en`（英文）。已知语言时建议手动指定以提高准确率 |

**流式调用说明：**

通过 `"stream": true` 启用流式输出，响应以 SSE（Server-Sent Events）逐 chunk 返回识别结果，遵循 OpenAI chat completion 响应格式。适用于实时语音识别、会议转录等需要低延迟的场景。

**Curl 流式请求示例：**

```curl
curl --location --request POST 'https://api.xiaomimimo.com/v1/chat/completions' \
--header "api-key: $MIMO_API_KEY" \
--header 'Content-Type: application/json' \
--data-raw '{
    "model": "mimo-v2.5-asr",
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": "data:audio/wav;base64,$BASE64_AUDIO"
                    }
                }
            ]
        }
    ],
    "asr_options": {
        "language": "auto"
    },
    "stream": true
}'
```

**Python 流式请求示例：**

```python
import os
import base64
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MIMO_API_KEY"),
    base_url="https://api.xiaomimimo.com/v1"
)

with open("audio_file.wav", "rb") as f:
    audio_bytes = f.read()
audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

completion = client.chat.completions.create(
    model="mimo-v2.5-asr",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": f"data:audio/wav;base64,{audio_base64}"
                    }
                }
            ]
        }
    ],
    extra_body={
        "asr_options": {
            "language": "auto"
        }
    },
    stream=True
)

for chunk in completion:
    print(chunk.model_dump_json())
```

> **参考文档**：https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/Speech-Recognition

#### 4.3.2 语音合成 (TTS)

- **模型**：mimo-v2.5-tts
- **音色**：`冰糖`（中文女声，柔和体贴，符合健康助手人设）
- **接口地址**：`POST https://api.xiaomimimo.com/v1/chat/completions`（OpenAI 兼容格式）
- **认证方式**：Header `api-key: $MIMO_API_KEY`

**请求结构说明：**

TTS 请求遵循 OpenAI chat completions 格式，消息结构有特殊要求：

| 字段 | 说明 |
|------|------|
| `messages[].role: "user"` | 可选。用于传入语气风格描述（自然语言控制），**不会被合成语音** |
| `messages[].role: "assistant"` | **必填**。待合成的目标文本放在此角色中 |
| `audio.format` | 音频格式。流式输出**必须使用 `pcm16`**，非流式可用 `wav` |
| `audio.voice` | 音色 ID，使用 `冰糖` |
| `stream` | `true` 启用流式输出 |

**可选音色列表：**

| 音色名 | ID | 语言 | 性别 |
|--------|----|------|------|
| 冰糖 | `冰糖` | 中文 | 女声 |
| 茉莉 | `茉莉` | 中文 | 女声 |
| 苏打 | `苏打` | 中文 | 男声 |
| 白桦 | `白桦` | 中文 | 男声 |
| Mia | `Mia` | 英文 | 女声 |
| Chloe | `Chloe` | 英文 | 女声 |
| Milo | `Milo` | 英文 | 男声 |
| Dean | `Dean` | 英文 | 男声 |

**流式调用说明：**

- 流式输出**必须指定 `audio.format` 为 `pcm16`**，输出为 24kHz PCM16LE 单声道音频
- 每个 chunk 中 `chunk.choices[0].delta.audio.data` 包含 Base64 编码的 PCM 音频片段
- 客户端需逐 chunk 解码并拼接为完整音频
- `mimo-v2.5-tts` 已支持低延迟实时流式输出

**风格控制方式：**

1. **自然语言控制**（`user` 角色）：用自由文本描述期望的语气、语速、情感。例如："用温柔体贴的语调，语速适中，像在关心一位老人的健康状况"
2. **音频标签控制**（`assistant` 角色文本内嵌）：在合成文本中嵌入风格标签，如 `(温柔)您今天感觉怎么样？`，支持括号格式 `()`、`（）`、`[]`

**Curl 流式请求示例：**

```curl
curl --location --request POST 'https://api.xiaomimimo.com/v1/chat/completions' \
--header "api-key: $MIMO_API_KEY" \
--header 'Content-Type: application/json' \
--data-raw '{
    "model": "mimo-v2.5-tts",
    "messages": [
        {
            "role": "user",
            "content": "用温柔体贴的语调，语速适中，像在关心一位老人的健康状况"
        },
        {
            "role": "assistant",
            "content": "您好，今天的血压测量结果是120比80，属于正常范围，非常不错呢。记得按时吃药，有任何不舒服随时告诉我。"
        }
    ],
    "audio": {
        "format": "pcm16",
        "voice": "冰糖"
    },
    "stream": true
}'
```

**Python 流式请求示例：**

```python
import base64
import os
import numpy as np
import soundfile as sf
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("MIMO_API_KEY"),
    base_url="https://api.xiaomimimo.com/v1"
)

completion = client.chat.completions.create(
    model="mimo-v2.5-tts",
    messages=[
        {
            "role": "user",
            "content": "用温柔体贴的语调，语速适中，像在关心一位老人的健康状况"
        },
        {
            "role": "assistant",
            "content": "您好，今天的血压测量结果是120比80，属于正常范围，非常不错呢。记得按时吃药，有任何不舒服随时告诉我。"
        }
    ],
    audio={
        "format": "pcm16",
        "voice": "冰糖"
    },
    stream=True
)

# 24kHz PCM16LE mono audio
collected_chunks: np.ndarray = np.array([], dtype=np.float32)

for chunk in completion:
    if not chunk.choices:
        continue
    delta = chunk.choices[0].delta
    audio = getattr(delta, "audio", None)

    if audio is not None:
        assert isinstance(audio, dict), f"Expected audio to be a dict, got {type(audio)}"
        pcm_bytes = base64.b64decode(audio["data"])
        np_pcm = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        collected_chunks = np.concatenate((collected_chunks, np_pcm))
        print(f"Received audio chunk of size {len(pcm_bytes)} bytes")

# Save the collected audio to a file
os.makedirs("tmp", exist_ok=True)
sf.write("tmp/output.wav", collected_chunks, samplerate=24000)
print("Audio saved to tmp/output.wav")
```

> **参考文档**：https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5

### 4.4 嵌入与重排模型调用规范

#### 4.4.1 嵌入模型

- **模型**：BAAI/bge-m3
- **服务提供商**：SiliconFlow
- **调用示例**：
```curl
curl -X POST https://api.siliconflow.cn/v1/embeddings \
  -H "Authorization: Bearer $SILICONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input": "Hello, world!",
    "model": "Qwen/Qwen3-VL-Embedding-8B"
  }'


```


```python
import requests
import os

response = requests.post(
    "https://api.siliconflow.cn/v1/embeddings",
    headers={
        "Authorization": f"Bearer {os.environ.get('SILICONFLOW_API_KEY')}",
        "Content-Type": "application/json"
    },
    json={
        "input": "Hello, world!",
        "model": "BAAI/bge-m3"
    }
)
```

#### 4.4.2 重排模型

- **模型**：BAAI/bge-reranker-v2-m3
- **服务提供商**：SiliconFlow
- **调用示例**：
```curl
curl -X POST https://api.siliconflow.cn/v1/rerank \
  -H "Authorization: Bearer $SILICONFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "BAAI/bge-reranker-v2-m3",
    "query": "Apple",
    "documents": ["apple", "banana", "fruit", "vegetable"],
    "return_documents": true,
    "top_n": 4
  }'
```

```python
import os
import requests

response = requests.post(
    "https://api.siliconflow.cn/v1/rerank",
    headers={
        "Authorization": f"Bearer {os.environ.get('SILICONFLOW_API_KEY')}",
        "Content-Type": "application/json"
    },
    json={
        "model": "BAAI/bge-reranker-v2-m3",
        "query": "Apple",
        "documents": ["apple", "banana", "fruit", "vegetable"],
        "return_documents": True,
        "top_n": 4
    }
)
```

### 4.5 配置管理

所有外部服务配置通过 `.env` 文件管理，禁止硬编码。配置分为两大类：**智能体模型配置**和**工具服务配置**。

#### 4.5.1 智能体模型配置

每个智能体模型由 5 个属性定义：

| 属性 | 字段名 | 说明 |
|------|--------|------|
| 服务地址 | `url` | API 端点（base_url） |
| 密钥 | `api_key` | 认证密钥 |
| 模型名 | `model_name` | 模型标识符（如 `qwen-plus`、`gpt-4o`） |
| 调用协议 | `model_protocol` | `openai` / `dashscope` / `anthropic` |
| 优先级 | `model_preference` | `primary`（主模型）/ `backup1` / `backup2` ... |

**配置示例：**

```env
# === 智能体模型配置 ===
# 主模型 — OpenAI 协议
AGENT_PRIMARY_URL=https://api.openai.com/v1
AGENT_PRIMARY_API_KEY=sk-xxx
AGENT_PRIMARY_MODEL=gpt-4o
AGENT_PRIMARY_PROTOCOL=openai
AGENT_PRIMARY_PREFERENCE=primary

# 备选 1 — DashScope 协议
AGENT_BACKUP1_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AGENT_BACKUP1_API_KEY=sk-xxx
AGENT_BACKUP1_MODEL=qwen-plus
AGENT_BACKUP1_PROTOCOL=dashscope
AGENT_BACKUP1_PREFERENCE=backup1

# 备选 2 — Anthropic 协议
AGENT_BACKUP2_URL=https://api.anthropic.com
ANTHROPIC_API_KEY=sk-ant-xxx
AGENT_BACKUP2_MODEL=claude-sonnet-4-20250514
AGENT_BACKUP2_PROTOCOL=anthropic
AGENT_BACKUP2_PREFERENCE=backup2
```

**AgentScope 加载方式：**

```python
import os
from agentscope.model import OpenAIChatModel, DashScopeChatModel, AnthropicChatModel
from agentscope.credential import OpenAICredential, DashScopeCredential, AnthropicCredential

PROTOCOL_MAP = {
    "openai": (OpenAICredential, OpenAIChatModel),
    "dashscope": (DashScopeCredential, DashScopeChatModel),
    "anthropic": (AnthropicCredential, AnthropicChatModel),
}

def load_model(prefix: str):
    """根据配置前缀加载模型，如 prefix='AGENT_PRIMARY'"""
    url = os.environ[f"{prefix}_URL"]
    api_key = os.environ[f"{prefix}_API_KEY"]
    model_name = os.environ[f"{prefix}_MODEL"]
    protocol = os.environ[f"{prefix}_PROTOCOL"]

    cred_cls, model_cls = PROTOCOL_MAP[protocol]
    credential = cred_cls(api_key=api_key)
    if hasattr(credential, 'base_url'):
        credential.base_url = url
    return model_cls(credential=credential, model=model_name, stream=True)

# 加载主备模型
primary_model = load_model("AGENT_PRIMARY")
backup1_model = load_model("AGENT_BACKUP1")
backup2_model = load_model("AGENT_BACKUP2")
```

#### 4.5.2 工具服务配置

除智能体模型外，以下工具服务需单独配置：

| 服务 | 必需配置项 | 说明 |
|------|-----------|------|
| ASR（语音识别） | `MIMO_API_KEY`、`ASR_MODEL` | MiMo ASR 服务 |
| TTS（语音合成） | `MIMO_API_KEY`、`TTS_MODEL`、`TTS_VOICE` | MiMo TTS 服务 |
| Embedding（嵌入） | `SILICONFLOW_API_KEY`、`EMBEDDING_MODEL` | SiliconFlow 嵌入服务 |
| Rerank（重排） | `SILICONFLOW_API_KEY`、`RERANK_MODEL` | SiliconFlow 重排服务 |
| AnySearch（联网搜索） | `ANYSEARCH_API_KEY`（可选） | AnySearch 搜索服务 |
| Tavily（备用搜索） | `TAVILY_API_KEY` | Tavily 搜索服务 |

**配置示例：**

```env
# === 语音服务 ===
MIMO_API_KEY=your-mimo-key
ASR_MODEL=mimo-v2.5-asr
TTS_MODEL=mimo-v2.5-tts
TTS_VOICE=冰糖

# === 嵌入与重排 ===
SILICONFLOW_API_KEY=your-siliconflow-key
EMBEDDING_MODEL=BAAI/bge-m3
RERANK_MODEL=BAAI/bge-reranker-v2-m3

# === 联网搜索 ===
ANYSEARCH_API_KEY=your-anysearch-key   # 可选，匿名可用
TAVILY_API_KEY=your-tavily-key
```

### 4.6 Agent Harness 编排模块

**职责**：管理智能体生命周期、ReAct 推理循环、多智能体协作调度、上下文组装、安全检查点。

**输入输出接口：**

```python
class AgentHarness(Protocol):
    """Agent Harness 核心编排接口"""

    async def process_message(
        self,
        user_message: str,
        session_id: str,
        context: AgentContext,
        stream_callback: Callable[[StreamEvent], None],
    ) -> AgentResponse:
        """
        处理用户消息，返回 AI 响应

        输入：
            user_message: 用户输入文本
            session_id: 会话标识
            context: 上下文信息（用户画像、记忆、已加载技能、已上传文件等）
            stream_callback: 流式事件回调（用于 SSE 推送到前端）
        输出：
            AgentResponse: 包含最终文本、工具调用记录、引用来源等
        """
        ...

    async def assemble_context(
        self,
        session_id: str,
        user_id: str,
        loaded_skills: list[str],
        uploaded_files: list[str],
    ) -> AgentContext:
        """
        组装智能体上下文

        输入：会话ID、用户ID、已加载技能列表、已上传文件列表
        输出：AgentContext（系统指令 + 工具Schema + 用户画像 + 记忆召回 + 对话历史）
        """
        ...

class StreamEvent:
    """SSE 流式事件定义"""
    event_type: str  # thinking | tool_call | tool_result | agent_start | text_delta | done
    data: dict       # 事件数据
    timestamp: float # 事件时间戳
```

**AgentScope 对应能力：**
- `Agent` / `ReActConfig`：智能体核心类和 ReAct 推理配置
- `Msg` / `TextBlock` / `ToolUseBlock`：消息与内容块
- `Toolkit` / `FunctionTool`：工具注册与调用
- `PermissionEngine`：权限控制引擎（人机回环）

**模块内部结构：**
```
agent_harness/
├── __init__.py
├── harness.py           # AgentHarness 主类实现
├── context.py           # 上下文组装逻辑（9源上下文）
├── react_loop.py        # ReAct 推理循环封装
├── team.py              # 多智能体团队调度（Coordinator-Expert）
├── safety.py            # 安全检查点（诊断拦截、PHI过滤、免责声明）
├── stream_events.py     # SSE 事件类型定义与序列化
├── protocols.py         # 接口定义（Protocol/ABC）
└── README.md            # 模块说明文档
```

**开发要求：**
- 安全检查点必须在每次工具调用前后执行
- 流式事件必须覆盖完整的执行过程（思考→工具调用→结果→文本输出→完成）
- 错误处理：工具调用失败自动重试（最多3次），超时自动降级
- 每个子模块可被独立替换（如替换 react_loop.py 的实现而不影响其他模块）

### 4.7 RAG 检索模块

**职责**：本地知识库检索、文档向量化、混合检索（向量+关键词+重排）。

**输入输出接口：**

```python
class RAGModule(Protocol):
    """RAG 检索模块接口"""

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """
        检索相关文档片段

        输入：
            query: 查询文本（自然语言）
            top_k: 返回结果数量
            filters: 过滤条件（如文档类型、时间范围）
        输出：
            list[RetrievalResult]: 检索结果列表，每个结果包含：
                - content: 文档片段文本
                - source: 来源（文件名、章节、页码）
                - score: 相关性分数
                - metadata: 元数据（文档类型、更新时间等）
        """
        ...

    async def index_document(
        self,
        file_path: str,
        doc_type: str,
    ) -> IndexResult:
        """
        将文档索引到向量库

        输入：文件路径、文档类型
        输出：索引结果（成功/失败、文档ID、分块数量）
        """
        ...

class RetrievalResult:
    content: str
    source: str
    score: float
    metadata: dict
```

**AgentScope 对应能力：**
- `RAGMiddleware`：RAG 检索增强中间件
- `KnowledgeBase`：知识库管理
- `EmbeddingModel`：嵌入模型调用

**技术实现要点：**
- 嵌入模型：BAAI/bge-m3（通过 SiliconFlow API，见 4.4.1 节）
- 重排模型：BAAI/bge-reranker-v2-m3（通过 SiliconFlow API，见 4.4.2 节）
- 本地知识库路径：`/Users/qizs/conclusion/gerclaw/本地知识库/md`
- 检索优先级：本地知识库 > 联网搜索 > 模型自身知识（见 10.2 节）
- 若 AgentScope 的 RAGMiddleware 不能满足混合检索需求，参考技术选型推荐 2.5 节的 Qdrant + BGE-M3 方案

**模块内部结构：**
```
rag/
├── __init__.py
├── rag_module.py        # RAGModule 主类实现
├── embedder.py          # 嵌入模型调用封装
├── reranker.py          # 重排模型调用封装
├── indexer.py           # 文档索引逻辑（分块、向量化、存储）
├── retriever.py         # 检索逻辑（混合检索、过滤、排序）
├── protocols.py         # 接口定义
└── README.md
```

### 4.8 Memory 记忆模块

**职责**：管理短期对话记忆和长期用户画像记忆，支持上下文窗口管理。

**输入输出接口：**

```python
class MemoryModule(Protocol):
    """记忆模块接口"""

    async def get_short_term(
        self,
        session_id: str,
        max_turns: int = 20,
    ) -> list[Message]:
        """
        获取短期对话记忆（当前会话历史）

        输入：会话ID、最大轮次
        输出：消息列表（按时间正序）
        """
        ...

    async def get_long_term(
        self,
        user_id: str,
        query: str | None = None,
    ) -> UserProfile:
        """
        获取长期用户画像记忆

        输入：用户ID、可选查询（用于相关性召回）
        输出：用户画像（基本信息、过敏史、用药列表、诊断记录等）
        """
        ...

    async def save_message(
        self,
        session_id: str,
        message: Message,
    ) -> None:
        """
        保存单条消息到记忆

        输入：会话ID、消息对象
        """
        ...

    async def extract_and_update_profile(
        self,
        user_id: str,
        conversation: list[Message],
    ) -> None:
        """
        从对话中提取关键信息并更新用户画像

        输入：用户ID、对话记录
        自动提取：过敏信息、用药变化、新诊断、体征数据等
        """
        ...

    async def compress_context(
        self,
        messages: list[Message],
        max_tokens: int,
    ) -> list[Message]:
        """
        压缩上下文以适应模型窗口

        输入：原始消息列表、最大 token 数
        输出：压缩后的消息列表（保留关键信息，摘要旧对话）
        """
        ...
```

**AgentScope 对应能力：**
- `Mem0Middleware`：长期记忆中间件
- `ContextConfig`：上下文压缩配置
- `Agent.state`：智能体状态管理

**技术实现要点：**
- 短期记忆：存储在 PostgreSQL 的会话消息表中
- 长期记忆：结构化字段（PostgreSQL JSONB）+ 向量检索（Qdrant）
- 上下文窗口管理：根据模型 `context_size` 自动截断/压缩（见 4.2.5 节）

**模块内部结构：**
```
memory/
├── __init__.py
├── memory_module.py     # MemoryModule 主类实现
├── short_term.py        # 短期记忆管理（会话历史）
├── long_term.py         # 长期记忆管理（用户画像）
├── extractor.py         # 记忆提取器（从对话中提取关键信息）
├── compressor.py        # 上下文压缩器
├── protocols.py         # 接口定义
└── README.md
```

### 4.9 Skill 技能模块

**职责**：技能注册、发现、加载、执行，支持预置技能和自定义技能。

**输入输出接口：**

```python
class SkillModule(Protocol):
    """技能模块接口"""

    async def list_skills(
        self,
        user_id: str | None = None,
    ) -> list[SkillInfo]:
        """
        获取可用技能列表

        输入：可选用户ID（区分系统技能和用户自定义技能）
        输出：技能信息列表（名称、描述、版本、参数Schema）
        """
        ...

    async def load_skill(
        self,
        skill_id: str,
    ) -> Skill:
        """
        加载技能到当前会话

        输入：技能ID
        输出：Skill 对象（包含工具定义和执行逻辑）
        """
        ...

    async def register_skill(
        self,
        skill_definition: SkillDefinition,
    ) -> str:
        """
        注册新技能

        输入：技能定义（名称、描述、参数Schema、执行逻辑）
        输出：技能ID
        """
        ...

    async def execute_skill(
        self,
        skill_id: str,
        params: dict,
    ) -> SkillResult:
        """
        执行技能

        输入：技能ID、执行参数
        输出：执行结果
        """
        ...

    async def generate_skill_from_nl(
        self,
        description: str,
    ) -> SkillDefinition:
        """
        通过自然语言描述生成技能定义

        输入：自然语言描述
        输出：结构化的技能定义
        """
        ...
```

**AgentScope 对应能力：**
- `SkillLoader`：技能加载器
- `ToolMiddlewareBase`：工具中间件基类
- `Toolkit` / `FunctionTool`：工具注册与调用

**技术实现要点：**
- 技能定义格式：`skill.md` 文件（Markdown + YAML frontmatter 定义元数据和参数）
- 支持上传 `skill.md` 文件或包含 `skill.md` 的压缩包（见 3.2.1 节技能管理入口）
- 通过自然语言描述生成自定义技能（LLM 辅助生成 skill.md）

**模块内部结构：**
```
skill/
├── __init__.py
├── skill_module.py      # SkillModule 主类实现
├── registry.py          # 技能注册中心（发现、版本管理）
├── loader.py            # 技能加载器（解析 skill.md、构建 Tool）
├── executor.py          # 技能执行器
├── generator.py         # 自然语言技能生成器
├── protocols.py         # 接口定义
└── README.md
```

### 4.10 Search 联网搜索模块

**职责**：联网搜索医疗健康信息，支持 AnySearch 和 Tavily 双通道。

**输入输出接口：**

```python
class SearchModule(Protocol):
    """联网搜索模块接口"""

    async def search(
        self,
        query: str,
        max_results: int = 5,
        domain: str | None = None,
    ) -> list[SearchResult]:
        """
        联网搜索

        输入：
            query: 搜索查询（自然语言）
            max_results: 最大结果数
            domain: 可选垂直领域（health/academic 等）
        输出：
            list[SearchResult]: 搜索结果列表，每个结果包含：
                - title: 标题
                - snippet: 摘要
                - url: 来源链接
                - source: 来源名称
                - published_date: 发布日期（如有）
        """
        ...

    async def extract_content(
        self,
        url: str,
    ) -> str:
        """
        提取网页全文内容

        输入：网页 URL
        输出：Markdown 格式的网页正文
        """
        ...
```

**AgentScope 对应能力：**
- `WebSearchTool`：联网搜索工具
- 可通过自定义搜索 Tool 封装 AnySearch/Tavily

**技术实现要点：**
- 主用：AnySearch（见 11.2 节），JSON-RPC 2.0 协议
- 备用：Tavily（见 11.3 节），自动降级
- 搜索结果必须标注来源 URL 和发布时间
- 老年综合评估模块不启用联网搜索（见 7.7 节）

**模块内部结构：**
```
search/
├── __init__.py
├── search_module.py     # SearchModule 主类实现
├── anysearch.py         # AnySearch API 封装
├── tavily_search.py     # Tavily API 封装
├── content_extractor.py # 网页内容提取
├── protocols.py         # 接口定义
└── README.md
```

### 4.11 Voice 语音模块

**职责**：语音识别（ASR）和语音合成（TTS），支持流式处理。

**输入输出接口：**

```python
class VoiceModule(Protocol):
    """语音模块接口"""

    async def transcribe(
        self,
        audio_data: bytes,
        format: str = "wav",
        language: str = "auto",
    ) -> TranscriptionResult:
        """
        语音识别（ASR）

        输入：音频数据（bytes）、格式、语言
        输出：转写结果（文本、置信度、时间戳）
        """
        ...

    async def synthesize(
        self,
        text: str,
        voice: str = "冰糖",
        style: str | None = None,
    ) -> AsyncIterator[bytes]:
        """
        语音合成（TTS），流式返回

        输入：待合成文本、音色、风格描述
        输出：PCM16 音频数据流（24kHz 单声道）
        """
        ...
```

**技术实现要点：**
- ASR 模型：mimo-v2.5-asr（见 4.3.1 节）
- TTS 模型：mimo-v2.5-tts，音色 `冰糖`（见 4.3.2 节）
- 流式 TTS 输出必须使用 `pcm16` 格式
- 语音输入交互：点击开始 → 点击停止（非长按）

**模块内部结构：**
```
voice/
├── __init__.py
├── voice_module.py      # VoiceModule 主类实现
├── asr.py               # ASR 封装（mimo-v2.5-asr）
├── tts.py               # TTS 封装（mimo-v2.5-tts）
├── audio_utils.py       # 音频格式转换工具
├── protocols.py         # 接口定义
└── README.md
```

### 4.12 Privacy 隐私安全模块

**职责**：PHI 脱敏、数据加密、审计日志、安全过滤。

**输入输出接口：**

```python
class PrivacyModule(Protocol):
    """隐私安全模块接口"""

    async def desensitize(
        self,
        text: str,
        context: str = "api_call",
    ) -> str:
        """
        文本 PHI 脱敏

        输入：原始文本、上下文（api_call / log / storage）
        输出：脱敏后文本（身份证→[REDACTED]、姓名→患者 等）
        """
        ...

    async def filter_input(
        self,
        user_input: str,
    ) -> FilterResult:
        """
        输入安全过滤

        输入：用户原始输入
        输出：过滤结果（是否安全、过滤后文本、拦截原因）
        """
        ...

    async def append_disclaimer(
        self,
        ai_output: str,
        output_type: str = "general",
    ) -> str:
        """
        追加免责声明

        输入：AI 输出文本、输出类型（general / prescription / assessment）
        输出：带免责声明的文本
        """
        ...
```

**AgentScope 对应能力：**
- `Workspace`：工作区沙箱
- `MiddlewareBase.on_reply`：中间件回复钩子（可用于脱敏）

**技术实现要点：**
- PHI 脱敏：正则匹配（身份证、手机号）+ NER 模型（姓名、住址）
- 调用第三方模型 API 前必须脱敏
- 每次 AI 输出必须追加免责声明（见 9.2 节）

**模块内部结构：**
```
privacy/
├── __init__.py
├── privacy_module.py    # PrivacyModule 主类实现
├── phi_detector.py      # PHI 检测器（正则+NER）
├── desensitizer.py      # 脱敏执行器
├── input_filter.py      # 输入安全过滤
├── disclaimer.py        # 免责声明管理
├── audit_logger.py      # 审计日志记录
├── protocols.py         # 接口定义
└── README.md
```

### 4.13 五大处方生成模块

**职责**：五大处方（药物、运动、营养、心理、康复）的生成、校验、导出。

**输入输出接口：**

```python
class PrescriptionModule(Protocol):
    """五大处方模块接口"""

    async def collect_info(
        self,
        session_id: str,
        user_message: str,
        collected_fields: dict,
    ) -> CollectionResult:
        """
        信息收集（从对话中提取处方所需字段）

        输入：会话ID、用户消息、已收集字段
        输出：CollectionResult（新提取的字段、缺失字段列表、是否信息完整）
        """
        ...

    async def generate_prescription(
        self,
        patient_info: dict,
        evidence_sources: list[str],
    ) -> PrescriptionReport:
        """
        生成五大处方报告

        输入：患者信息（完整字段）、循证来源列表
        输出：处方报告（结构化 JSON，严格遵循模板）
        """
        ...

    async def validate_report(
        self,
        report: PrescriptionReport,
    ) -> ValidationResult:
        """
        校验处方报告（格式校验 + 内容校验 + 循证校验 + 安全校验）

        输入：处方报告
        输出：校验结果（是否通过、错误列表）
        """
        ...

    async def export_report(
        self,
        report: PrescriptionReport,
        format: str = "markdown",
    ) -> bytes:
        """
        导出处方报告

        输入：处方报告、导出格式（markdown / pdf / word）
        输出：文件内容（bytes）
        """
        ...
```

**技术实现要点：**
- 模板路径：`/Users/qizs/conclusion/gerclaw/输入输出/五大处方报告模板.md`
- 智能体产出结果必须是 JSON 格式的结构化数据（见 6.1 节）
- 生成流程：信息解析 → 字段模板填充 → 健康诊断 → 处方生成 → JSON 输出 → 四重校验 → Markdown 报告

**模块内部结构：**
```
prescription/
├── __init__.py
├── prescription_module.py  # PrescriptionModule 主类实现
├── collector.py            # 信息收集器（对话字段提取）
├── generator.py            # 处方生成器（LLM + 模板填充）
├── validator.py            # 校验器（格式/内容/循证/安全四重校验）
├── exporter.py             # 导出器（Markdown/PDF/Word）
├── templates/              # JSON 模板目录
├── protocols.py            # 接口定义
└── README.md
```

### 4.14 CGA 评估模块

**职责**：老年综合评估量表管理、对话化采集、自动计分、报告生成。

**输入输出接口：**

```python
class CGAModule(Protocol):
    """CGA 评估模块接口"""

    async def get_scales(
        self,
    ) -> list[ScaleInfo]:
        """
        获取可用评估量表列表

        输出：量表信息列表（名称、描述、题目数量、预计时长）
        """
        ...

    async def get_question(
        self,
        scale_id: str,
        current_index: int,
        answers: dict,
    ) -> Question:
        """
        获取当前题目（支持跳转逻辑）

        输入：量表ID、当前题目索引、已答题目
        输出：题目信息（文字、选项、分值、语音文本）
        """
        ...

    async def submit_answer(
        self,
        scale_id: str,
        question_index: int,
        answer: str | int,
        session_answers: dict,
    ) -> AnswerResult:
        """
        提交答案

        输入：量表ID、题目索引、答案、会话已有答案
        输出：AnswerResult（下一题索引、是否完成、进度百分比）
        """
        ...

    async def calculate_score(
        self,
        scale_id: str,
        answers: dict,
    ) -> ScoreResult:
        """
        计算评估得分

        输入：量表ID、所有答案
        输出：得分、分级、结果解读
        """
        ...

    async def generate_report(
        self,
        assessment_results: list[ScoreResult],
        patient_info: dict,
    ) -> AssessmentReport:
        """
        生成综合评估报告

        输入：所有量表评估结果、患者信息
        输出：综合评估报告
        """
        ...
```

**AgentScope 对应能力：**
- `Agent.state`：智能体状态管理（评估进度持久化）
- 自定义 Tool：量表评分工具
- ReAct 循环：对话化提问逻辑

**技术实现要点：**
- 量表定义使用 JSON DSL（题目列表、选项/分值、跳转逻辑、分级阈值）
- 评分逻辑必须由确定性代码执行，LLM 仅负责问题表述和答案理解
- 评估量表路径：`/Users/qizs/conclusion/gerclaw/问卷量表`
- 不启用联网搜索（见 7.7 节）

**模块内部结构：**
```
cga/
├── __init__.py
├── cga_module.py        # CGAModule 主类实现
├── scale_manager.py     # 量表管理器（加载、查询量表定义）
├── question_engine.py   # 题目引擎（跳转逻辑、对话化表述）
├── scorer.py            # 评分引擎（确定性计算）
├── report_generator.py  # 评估报告生成器
├── scales/              # 量表 JSON 定义文件目录
├── protocols.py         # 接口定义
└── README.md
```

### 4.15 文档解析模块

**职责**：上传文档的解析，调用 MinerU API 将文档转为 Markdown。

**输入输出接口：**

```python
class DocumentModule(Protocol):
    """文档解析模块接口"""

    async def parse_document(
        self,
        file_path: str | None = None,
        file_url: str | None = None,
        options: ParseOptions | None = None,
    ) -> ParseResult:
        """
        解析文档

        输入：本地文件路径或远程URL、解析选项
        输出：ParseResult（Markdown 内容、解析状态、错误信息）
        """
        ...

    async def get_parse_status(
        self,
        task_id: str,
    ) -> ParseStatus:
        """
        查询解析状态

        输入：任务ID
        输出：解析状态（waiting-file/uploading/pending/running/done/failed）
        """
        ...
```

**技术实现要点：**
- 使用 MinerU Agent 轻量解析 API（见 5.2.2 节）
- 文件限制：10MB、20 页
- 支持格式：PDF、图片、Docx、PPTx、Xlsx

**模块内部结构：**
```
document/
├── __init__.py
├── document_module.py   # DocumentModule 主类实现
├── mineru_client.py     # MinerU API 客户端
├── file_handler.py      # 文件上传/格式检测
├── protocols.py         # 接口定义
└── README.md
```

### 4.16 前后端打通方案

#### 4.16.1 数据流架构

```
用户操作 → 前端 (Next.js) → HTTP/SSE → 后端 (FastAPI)
                                              ↓
                                     Agent Harness 编排层
                                              ↓
                    ┌─────────┬─────────┬─────────┬─────────┐
                    │ RAG模块  │ Memory  │ Skill   │ Search  │
                    └────┬────┴────┬────┴────┬────┴────┬────┘
                         ↓         ↓         ↓         ↓
                    AgentScope 核心引擎 (Agent + Model + Tool)
                         ↓
                    外部服务 (LLM API / ASR / TTS / Embedding / MinerU)
                         ↓
                    后端 (FastAPI) → SSE 流式响应 → 前端渲染
```

#### 4.16.2 前后端通信协议

**1. 普通对话请求（SSE 流式）：**

```
前端 → 后端：
POST /api/chat
Content-Type: application/json
{
    "session_id": "uuid",
    "message": "用户输入文本",
    "loaded_skills": ["skill-id-1", "skill-id-2"],
    "uploaded_files": ["file-id-1"]
}

后端 → 前端（SSE 流式）：
event: thinking
data: {"content": "让我分析一下您的症状..."}

event: tool_call
data: {"tool_name": "rag_search", "params": {"query": "..."}, "status": "running"}

event: tool_result
data: {"tool_name": "rag_search", "result": {...}, "status": "done", "duration_ms": 230}

event: text_delta
data: {"content": "根据"}

event: text_delta
data: {"content": "您的描述"}

event: done
data: {"full_text": "根据您的描述...", "references": [...]}
```

**2. 语音消息请求：**

```
前端 → 后端：
POST /api/chat/voice
Content-Type: multipart/form-data
- audio: [音频文件]
- session_id: "uuid"
- format: "wav"

后端处理流程：
1. 调用 ASR 模块转写音频 → 得到文本
2. 将文本作为用户消息走正常对话流程
3. SSE 流式返回 AI 回复

后端额外返回 ASR 结果：
event: asr_result
data: {"text": "转写的文本", "confidence": 0.95}
```

**3. 五大处方生成请求：**

```
前端 → 后端：
POST /api/prescriptions/generate
{
    "session_id": "uuid",
    "patient_info": {
        "name": "...",
        "age": 72,
        ...
    }
}

后端 → 前端（SSE 流式）：
event: thinking
data: {"content": "正在分析患者信息..."}

event: prescription_progress
data: {"step": "collecting", "collected": 5, "total": 12}

event: prescription_progress
data: {"step": "generating", "phase": "药物处方"}

event: prescription_result
data: {"report": {...}, "markdown": "..."}
```

#### 4.16.3 前端渲染对应关系

| 后端 SSE 事件 | 前端渲染组件 |
|--------------|-------------|
| `thinking` | 可折叠"思考过程"区块（默认折叠，浅灰背景） |
| `tool_call` | 工具调用卡片（图标+名称+状态徽章，运行中旋转） |
| `tool_result` | 更新工具卡片状态（完成✓/失败✗，显示耗时） |
| `agent_start` | 子智能体节点（折叠树形结构） |
| `text_delta` | 打字机效果文本追加（实时 Markdown 渲染） |
| `asr_result` | 语音识别结果展示（可编辑纠正） |
| `prescription_progress` | 右侧面板处方进度更新 |
| `prescription_result` | 右侧面板处方报告预览 |
| `done` | 标记完成，显示消息操作按钮 |

---

## 5. 输入输出处理规范

### 5.1 通用要求

- 所有输入输出必须通过格式校验
- 所有输入输出必须进行安全过滤，防止敏感信息泄露

### 5.2 输入规范

#### 5.2.1 输入类型支持

| 类型 | 说明 |
|------|------|
| 文本 | 直接文本输入 |
| 图片 | 支持图片上传 |
| 语音 | 需通过 ASR 转换为文本（需获取设备麦克风权限） |
| 文档 | 支持 PDF、Word、Excel、PPT、Markdown、TXT 格式 |

#### 5.2.2 文档解析

使用 MinerU Agent 轻量解析 API 进行文档解析。所有上传文档必须使用 MinerU 解析，解析结果作为智能体输入的一部分。

##### 概述

MinerU Agent 轻量解析接口专为 AI Agent 场景设计，提供快速、免登录的文档解析能力。

**核心特性：**
- **无需登录**：通过 IP 限频防滥用，无需 Token
- **轻量快速**：PDF/图片使用 pipeline 轻量模型，Word/PPT 使用 Office 原生 API 解析
- **统一输出**：仅输出 Markdown 格式，返回 CDN 链接
- **双模式提交**：URL 解析和文件上传为独立接口，文件上传采用签名上传模式

**文件限制：**

| 限制项 | 限制值 |
|--------|--------|
| 文件大小上限 | 10 MB |
| 页数上限 | 20 页 |
| 支持文件类型 | PDF、图片（png/jpg/jpeg/jp2/webp/gif/bmp）、Docx、PPTx、Xlsx |

##### API 1：URL 解析接口

提交远程文件 URL 进行解析，异步返回 `task_id`，需轮询查询结果。

```
POST https://mineru.net/api/v1/agent/parse/url
```

**请求参数（JSON）：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| url | string | 是 | 远程文件 URL，支持 PDF、图片、Docx、PPTx、Xlsx |
| file_name | string | 否 | 文件名（含扩展名），用于判断文件类型 |
| language | string | 否 | 解析语言，默认 `ch`，仅对 PDF 生效 |
| enable_table | bool | 否 | 是否开启表格识别，默认 `true`，仅对 PDF 生效 |
| is_ocr | bool | 否 | 是否开启 OCR，默认 `false`，仅对 PDF 生效 |
| enable_formula | bool | 否 | 是否开启公式识别，默认 `true`，仅对 PDF 生效 |
| page_range | string | 否 | 页码范围，仅对 PDF 有效，支持 `1-10` 或 `5` 格式 |

**响应示例：**
```json
{
  "code": 0,
  "data": { "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605" },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

##### API 2：本地文件上传接口（签名上传）

采用签名上传模式：先获取上传 URL，再 PUT 上传文件，后端自动解析。

```
POST https://mineru.net/api/v1/agent/parse/file
```

**请求参数（JSON）：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| file_name | string | 是 | 文件名（含扩展名） |
| language | string | 否 | 解析语言，默认 `ch`，仅对 PDF 生效 |
| enable_table | bool | 否 | 是否开启表格识别，默认 `true`，仅对 PDF 生效 |
| is_ocr | bool | 否 | 是否开启 OCR，默认 `false`，仅对 PDF 生效 |
| enable_formula | bool | 否 | 是否开启公式识别，默认 `true`，仅对 PDF 生效 |
| page_range | string | 否 | 页码范围，仅对 PDF 有效 |

**响应示例：**
```json
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "file_url": "https://oss-mineru.openxlab.org.cn/agent/a90e6ab6-...pdf?Expires=..."
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

客户端使用 `PUT` 方法将文件上传到 `file_url`，上传完成后后端自动开始解析。

##### API 3：查询解析结果

通过 `task_id` 查询解析状态和结果，完成时返回 Markdown CDN 链接。

```
GET https://mineru.net/api/v1/agent/parse/{task_id}
```

**响应参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| data.task_id | string | 任务 ID |
| data.state | string | 状态：`waiting-file` / `uploading` / `pending` / `running` / `done` / `failed` |
| data.markdown_url | string | Markdown 结果 CDN 链接，`done` 时有效 |
| data.err_msg | string | 错误信息，`failed` 时有效 |

**响应示例（完成）：**
```json
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b459-b62fe4c6b43605",
    "state": "done",
    "markdown_url": "https://cdn-mineru.openxlab.org.cn/pdf/a90e6ab6-.../full.md"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

##### 完整使用示例（Python）

```python
import requests
import time

BASE_URL = "https://mineru.net/api/v1/agent"

def parse_by_url(url, language="ch", page_range=None, enable_table=True, is_ocr=False, enable_formula=True):
    """通过 URL 提交文档解析任务并等待结果。"""
    data = {"url": url, "language": language, "enable_table": enable_table, "is_ocr": is_ocr, "enable_formula": enable_formula}
    if page_range:
        data["page_range"] = page_range
    resp = requests.post(f"{BASE_URL}/parse/url", json=data)
    result = resp.json()
    if result["code"] != 0:
        print(f"提交失败: {result['msg']}")
        return None
    task_id = result["data"]["task_id"]
    print(f"任务已提交, task_id: {task_id}")
    return poll_result(task_id)

def parse_by_file(file_path, language="ch", page_range=None, enable_table=True, is_ocr=False, enable_formula=True):
    """通过文件上传提交文档解析任务并等待结果。"""
    file_name = file_path.split("/")[-1]
    data = {"file_name": file_name, "language": language, "enable_table": enable_table, "is_ocr": is_ocr, "enable_formula": enable_formula}
    if page_range:
        data["page_range"] = page_range
    resp = requests.post(f"{BASE_URL}/parse/file", json=data)
    result = resp.json()
    if result["code"] != 0:
        print(f"提交失败: {result['msg']}")
        return None
    task_id = result["data"]["task_id"]
    file_url = result["data"]["file_url"]
    print(f"任务已创建, task_id: {task_id}")
    with open(file_path, "rb") as f:
        put_res = requests.put(file_url, data=f)
        print(f"文件上传状态: {put_res.status_code}")
    return poll_result(task_id)

def poll_result(task_id, timeout=300, interval=3):
    """轮询查询解析结果。"""
    state_labels = {"uploading": "文件下载中", "pending": "排队中", "running": "解析中", "waiting-file": "等待文件上传"}
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/parse/{task_id}")
        result = resp.json()
        state = result["data"]["state"]
        elapsed = int(time.time() - start)
        if state == "done":
            markdown_url = result["data"]["markdown_url"]
            print(f"[{elapsed}s] 解析完成, Markdown 下载链接: {markdown_url}")
            md_resp = requests.get(markdown_url)
            return md_resp.text
        if state == "failed":
            print(f"[{elapsed}s] 解析失败: {result['data'].get('err_msg', '未知错误')}")
            return None
        print(f"[{elapsed}s] {state_labels.get(state, state)}...")
        time.sleep(interval)
    print(f"轮询超时 ({timeout}s)，请稍后手动查询 task_id: {task_id}")
    return None

# 使用示例
content = parse_by_url("https://cdn-mineru.openxlab.org.cn/demo/example.pdf")
```

> **参考文档**：https://mineru.net/apiManage/docs


### 5.3 输出规范

#### 5.3.1 输出类型支持

| 类型 | 说明 |
|------|------|
| 文本 | 默认输出格式 |
| 语音 | 通过 TTS 合成，用户可点击播放按钮收听 |
| 文档导出 | 支持 PDF、Word、Markdown、TXT 格式下载 |
| 预览 | 支持实时编辑预览（参照豆包实现） |

---

## 6. 五大处方模块

### 6.1 模板规范

- **模板路径**：`/Users/qizs/conclusion/gerclaw/输入输出/五大处方报告模板.md`
- **特别声明**：该md文件的内容为最终前端展示出来的模板，实际系统由智能体产出的结果应该是json格式的结构化数据，需要从这个md文件里提取出json模板，智能体在生成五大处方时必须严格遵循这个json模板的结构和字段要求。
- **输出格式**：结构化 JSON
- **内容要求**：
  - 严格遵循模板结构
  - 符合医疗循证要求，禁止虚假信息
  - 每个处方字段必须包含循证来源字段（可追溯）

### 6.2 报告生成流程

```
患者信息输入 → 信息解析与提取 → 输入字段模板填充 → 健康问题诊断 
→ 处方分析生成 → JSON 数据输出 → 格式校验 → 内容校验 → 循证校验 
→ 安全校验 → Markdown 报告生成 → 前端预览 → 导出
```

### 6.3 报告结构要求

| 章节 | 内容要求 |
|------|---------|
| 患者信息摘要 | 患者基本信息概览 |
| 健康诊断 | 身体状况评估、疑似疾病诊断 |
| 五大处方 | 药物/运动/营养/心理/康复处方详细内容 |
| 引用列表 | 所有循证来源和参考文本，与正文引用标记一一对应 |
| 免责声明 | 大模型生成内容免责声明 |

### 6.4 交互设计（医生端+患者端通用）

五大处方生成采用**对话流程 + 右侧动态面板预览**的交互模式（对齐 Trae Work）：

**入口触发**：
- 输入框左侧 💊 处方按钮
- 欢迎页快捷入口卡片"五大处方生成"
- 对话中自然语言触发（如"帮我生成处方"）

**交互流程**：
1. **信息收集阶段**：主聊天区进行对话收集患者信息，右侧面板显示：
   - 已收集字段实时预览（表单形式）
   - 缺失字段高亮提示
   - 进度指示（如"已收集 5/12 项"）
2. **信息补全阶段**：系统自动检测缺失字段，通过多轮对话补充（上限 10 轮），右侧面板实时更新
3. **生成阶段**：信息完整后自动触发生成，主聊天区显示智能体执行过程（思考→工具调用→多步骤时间线）
4. **结果预览阶段**：生成完成后右侧面板展示完整处方报告：
   - 支持 Markdown 渲染
   - 支持目录导航（点击跳转对应章节）
   - 支持导出（PDF/Word/Markdown）
   - 支持语音朗读（老年模式默认开启）
5. **对话区同步**：AI 在主聊天区给出摘要回复，包含关键结论和"查看完整报告"按钮

**医生端差异化**：
- 右侧面板提供编辑功能：医生可直接修改处方内容
- 提供"应用于患者"按钮：确认后发送给患者端
- 显示患者历史处方对比

**患者端差异化（老年模式默认开启）**：
- 语音交互优先：所有问题自动语音朗读，支持语音回答
- 按钮更大、字体更大、对比度更高
- 关键结论用语音播报
- 简化操作步骤，减少文字输入

### 6.5 患者端功能

#### 6.5.1 首次对话流程

1. 用户通过输入框 💊 按钮或欢迎页入口启动
2. 右侧面板自动展开，显示处方生成向导
3. 系统通过对话收集信息（语音优先，支持文本/文件上传）
4. 右侧面板实时预览已收集信息，显示进度
5. 检测缺失字段，设计情景对话进行多轮补充（上限 10 轮）
6. 信息完整后进入处方生成流程，主聊天区展示执行可视化
7. 生成完成后右侧面板展示完整报告，支持语音朗读和导出

#### 6.5.2 全语音对话模式

- 启动方式：点击输入框语音按钮后说"开始五大处方评估"，或点击处方按钮后选择"全语音模式"
- 系统根据预设对话路线进行语音提问
- 动态调整对话路线，适应患者回答
- 语音提问需考虑老年患者认知特点（语速稍慢、用词简单、重复关键信息）
- 患者可随时按任意键或说"重复"重听问题
- 关键信息系统会二次确认（如"您刚才说您有高血压，对吗？"）

#### 6.5.3 参考数据

- **患者数据**：`/Users/qizs/conclusion/gerclaw/输入输出/hzj`（PDF 格式）
- **信息汇总**：`/Users/qizs/conclusion/gerclaw/输入输出/hzj`（CSV 格式）
- **结构化数据**：`/Users/qizs/conclusion/gerclaw/输入输出/hzj_case.json`

---

## 7. 老年综合评估模块

### 7.1 功能概述

该模块在医生端和患者端运行方式一致，提供标准化的老年综合评估服务。

### 7.2 评估流程

```
选择评估量表 → 加载量表问题 → 逐题展示（文字+语音） 
→ 用户作答（点击选项/语音输入） → 答案写入缓存 → 
→ 全部完成 → 分析评估结果 → 生成评估报告 → 预览/导出
```

### 7.3 交互设计（右侧面板量表模式，对齐 Trae Work）

CGA 评估采用**右侧动态面板 + 对话辅助**的交互模式：

**入口触发**：
- 输入框左侧 📋 评估按钮
- 欢迎页快捷入口"老年综合评估"
- 对话中自然语言触发（如"我要做CGA评估"）

**右侧面板布局（展开宽度 400-500px）**：

| 区域 | 位置 | 组件与交互 |
|------|------|-----------|
| **顶部进度区** | 面板顶部 | - 量表名称 + 题目进度（如"ADL 评估：3/10"）<br>- 进度条可视化（已完成绿色，当前蓝色，未完成灰色）<br>- 放弃/关闭按钮 |
| **问题展示区** | 面板中部（滚动区域） | - 问题文字：大字体、高对比度<br>- 问题序号 + 总分值标注<br>- 🔊 语音朗读按钮（默认自动播放）<br>- 语音波形动画（播放时显示） |
| **选项展示区** | 问题下方 | - 选项以大卡片形式展示（老年模式：卡片更大、间距更大）<br>- 每个选项：选项文字 + 分值标签<br>- 点击卡片即选中，选中后高亮显示<br>- 支持语音输入：点击🎤按钮说出选项内容 |
| **导航区** | 面板底部 | - 上一题/下一题按钮（下一题在选中选项后激活）<br>- 题目导航点：快速跳转到任意题目<br>- 已答题目显示✓，未答显示空心，当前显示蓝色边框 |

**对话区联动**：
- 主聊天区显示评估引导和实时反馈（如"您已完成 3/10 题，继续加油！"）
- 支持通过对话补充信息（上传病历、补充说明）
- 完成所有题目后，主聊天区显示智能体分析过程（思考→生成报告）
- 最终评估报告在右侧面板预览，支持导出（PDF/Word/Markdown）和语音朗读

**老年模式适配**：
- 字体放大至 18-20px
- 按钮最小尺寸 48×48px
- 选项卡片间距 ≥ 16px
- 颜色对比度 ≥ 4.5:1
- 所有问题自动语音朗读
- 选项自动重复播放（可关闭）
- 选中后语音确认（如"您选择了'能够独立完成'，对吗？"）
- 简化操作，减少选择错误

### 7.4 音频资源管理

- 问题和选项的语音需预先录制为音频文件
- 存储路径：待定（建议 `/assets/audio/cga/`）
- 避免重复调用 TTS 模型

### 7.5 数据存储

- 每个量表的回答结果存储为缓存 JSON 文件
- 评估报告支持 PDF、Word、Markdown、TXT 格式导出

### 7.6 评估量表

- **现有量表**：`/Users/qizs/conclusion/gerclaw/问卷量表`
- **要求**：根据老年综合评估定义，调研并补充其他评估量表

### 7.7 特殊说明

> ⚠️ 老年综合评估模块**不启用联网搜索**

---

## 8. 用户与权限管理

### 8.1 用户模式

| 模式 | 特性 |
|------|------|
| 游客模式 | 用户先在登录页显式选择“以游客身份进入患者端”；仅患者端服务；仅本次浏览器会话保留历史，下一次进入不恢复。后台仍按隐私规则保留 Trace/Bad Case，供受控质量改进使用 |
| 账号模式 | 从同一登录页登录或注册；按患者/医生角色加载对应端并保存独立历史。管理员可切换工作台，但不因此取得跨患者临床访问权限 |

### 8.2 登录流程

```
系统首页（强制登录入口） → 选择登录方式：
├── 以游客身份进入患者端 → 创建仅当前浏览器会话有效的患者范围身份
├── 账号登录 → 验证凭证 → 根据角色进入对应端
└── 注册账号 → 填写信息（账号/密码/角色） → 完成注册
```

### 8.3 账号功能

- 查看历史对话数据
- 查看历史五大处方报告
- 查看历史老年综合评估报告
- 个人信息管理

---

## 9. 系统安全与合规

### 9.1 安全防护

| 措施 | 说明 |
|------|------|
| 沙箱执行 | 工具调用在隔离沙箱环境中执行 |
| 数据脱敏 | 敏感信息进行脱敏处理 |
| 密钥管理 | 通过环境变量注入，禁止硬编码 |
| 传输安全 | 全链路 HTTPS 加密 |

### 9.2 合规要求

- 页面底部显示大模型生成提醒
- 每次输出内容底部标注"内容由 AI 生成，仅供参考"
- 提示用户对生成内容进行甄别，身体不适请及时就医

---

## 10. 本地知识库

### 10.1 知识源

- **路径**：`/Users/qizs/conclusion/gerclaw/本地知识库/md`
- **格式**：Markdown 文献文件

### 10.2 检索优先级

```
本地知识库（最高优先级） > 联网搜索 > 模型自身知识
```

---

## 11. 联网搜索

### 11.1 搜索工具

| 优先级 | 工具 | 配置要求 |
|--------|------|---------|
| 主用 | AnySearch | 配置 `ANYSEARCH_API_KEY` |
| 备用 | Tavily Search | 配置 Tavily API Key |

### 11.2 AnySearch 集成

- **要求**：强制使用 AnySearch 进行联网搜索，失败时自动降级至 Tavily
- **API 端点**：`POST https://api.anysearch.com/mcp`
- **协议**：JSON-RPC 2.0
- **认证方式**：Header `Authorization: Bearer $ANYSEARCH_API_KEY`（可选，匿名可用但限频较低）
- **依赖**：仅需 `curl` + `jq`，无 Python 依赖

#### 协议格式

所有请求统一为 JSON-RPC 2.0 格式，通过 `method: "tools/call"` 调用不同工具：

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "<工具名>",
    "arguments": { ... }
  }
}
```

响应结构：
- 成功：`response.result.content[0].text`（Markdown 格式文本）
- 失败：`response.error.message`

#### 核心工具

| 工具名 (`params.name`) | 用途 | 说明 |
|------------------------|------|------|
| `search` | 通用/垂直搜索 | 单次返回最多 10 条结果 |
| `batch_search` | 批量搜索 | 并行最多 5 个查询，适合多角度调查 |
| `extract` | URL 内容提取 | 抓取网页全文转 Markdown，最大 50000 字符 |
| `get_sub_domains` | 领域发现 | 查询垂直领域可用的 sub_domain 和参数，**垂直搜索前必须先调用** |

#### 支持的垂直领域

`general`、`resource`、`social_media`、`finance`、`academic`、`legal`、`health`、`business`、`security`、`ip`、`code`、`energy`、`environment`、`agriculture`、`travel`、`film`、`gaming`

#### 1. 通用搜索

```bash
curl -s -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANYSEARCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search",
      "arguments": {
        "query": "老年人跌倒预防措施",
        "max_results": 5
      }
    }
  }' | jq -r '.result.content[0].text'
```

#### 2. 垂直领域搜索

**第一步：发现子域**

```bash
curl -s -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANYSEARCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_sub_domains",
      "arguments": {
        "domain": "health"
      }
    }
  }' | jq -r '.result.content[0].text'
```

返回 Markdown 表格，包含 `sub_domain`、`description`、`params`（可用结构化参数）。

**第二步：搜索（使用返回的 sub_domain）**

```bash
curl -s -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANYSEARCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "search",
      "arguments": {
        "query": "二甲双胍最新临床指南",
        "domain": "health",
        "sub_domain": "health.drug"
      }
    }
  }' | jq -r '.result.content[0].text'
```

#### 3. 批量搜索

最多并行 5 个查询，每个查询可独立指定 domain/sub_domain：

```bash
curl -s -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANYSEARCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "batch_search",
      "arguments": {
        "queries": [
          {"query": "老年肌少症诊断标准"},
          {"query": "肌少症运动干预指南", "domain": "academic", "sub_domain": "academic.paper"}
        ]
      }
    }
  }' | jq -r '.result.content[0].text'
```

#### 4. URL 内容提取

抓取网页全文并转为 Markdown，仅支持 HTML 页面：

```bash
curl -s -X POST "https://api.anysearch.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ANYSEARCH_API_KEY" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "extract",
      "arguments": {
        "url": "https://example.com/guideline.html"
      }
    }
  }' | jq -r '.result.content[0].text'
```

#### 参数速查表

**search arguments：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索查询，自然语言 |
| `domain` | string | 否 | 垂直领域名，省略则通用搜索 |
| `sub_domain` | string | 否 | 子域，需先调 `get_sub_domains` 获取 |
| `sub_domain_params` | object | 否 | 结构化参数，如 `{"ticker":"AAPL"}` |
| `max_results` | int | 否 | 1-10，默认 10 |

**batch_search arguments：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `queries` | object[] | 是 | 查询数组，最多 5 项。每项含 `query`（必填），可选 `domain`/`sub_domain`/`sub_domain_params` |

**extract arguments：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 网页 URL，必须 `http://` 或 `https://` 开头 |

**get_sub_domains arguments：**

| 参数 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `domain` | string | 否 | 单个领域名 |
| `domains` | string[] | 否 | 批量查询（最多 5 个），优先级高于 `domain` |

> **参考文档**：https://www.anysearch.com/docs


### 11.3 Tavily 集成

```python
from tavily import TavilyClient
import os

client = TavilyClient(os.environ.get("TAVILY_API_KEY"))

# 搜索
response = client.search(query="", search_depth="advanced")

# 提取
response = client.extract(urls=[""])

# 爬取
response = client.crawl(url="", extract_depth="advanced")
```
```javascript
// To install: npm i @tavily/core
const { tavily } = require('@tavily/core');
const client = tavily({ apiKey: "${TAVILY_API_KEY}" });
// 搜索
client.search("", {
    searchDepth: "advanced"
})
.then(console.log);
// 提取
client.extract([""])
.then(console.log);
// 爬取
client.crawl("", {
    extractDepth: "advanced"
})
.then(console.log);
```

```curl
curl -X POST https://api.tavily.com/search \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer ${TAVILY_API_KEY}' \
-d '{
    "query": "",
    "search_depth": "advanced"
}'
```

```curl
curl -X POST https://api.tavily.com/extract \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer ${TAVILY_API_KEY}' \
-d '{
    "urls": [
        ""
    ]
}'
```

```curl
curl -X POST https://api.tavily.com/crawl \
-H 'Content-Type: application/json' \
-H 'Authorization: Bearer ${TAVILY_API_KEY}' \
-d '{
    "url": "",
    "extract_depth": "advanced"
}'

```
---

## 12. 数据存储规范

### 12.1 存储内容

| 数据类型 | 存储要求 |
|---------|---------|
| 交互数据 | 用户输入、模型输出、工具调用、联网搜索、技能调用、思维链、决策过程 |
| 执行 Trace | 完整的执行链路追踪，JSON 格式 |
| 处方报告 | 初始生成版本 + 最终导出版本 |
| 评估报告 | 初始生成版本 + 最终导出版本 |

### 12.2 数据用途

- 系统故障排查与修复
- 系统性能评估与优化
- 数据飞轮建设
- 历史数据查询与复用

---

## 13. UI 设计规范（视觉设计系统）

> **设计参考基准**：视觉风格与交互体验对齐 Trae Work，保持专业、简洁、现代的 AI 产品设计语言。

### 13.1 颜色系统

采用医疗行业专业配色，支持深色/浅色双主题：

**浅色主题（默认）**：

| 用途 | 色值 | 说明 |
|------|------|------|
| 主色调（品牌色） | `#2563EB`（蓝色系） | 主按钮、链接、激活状态、进度条 |
| 成功状态 | `#10B981`（绿色） | 完成、成功、正确选项 |
| 警告状态 | `#F59E0B`（橙色） | 提示、注意、加载中 |
| 错误状态 | `#EF4444`（红色） | 失败、错误、删除 |
| 背景色 | `#FFFFFF` / `#F8FAFC` | 页面背景/面板背景 |
| 侧边栏背景 | `#F1F5F9` | 左侧边栏背景 |
| 文本主色 | `#0F172A` | 标题、正文 |
| 文本次要 | `#475569` | 辅助文字、说明 |
| 文本弱化 | `#94A3B8` | 占位符、禁用状态 |
| 边框色 | `#E2E8F0` | 分割线、边框 |
| 悬浮背景 | `#F1F5F9` | 鼠标悬停背景 |

**深色主题**：

| 用途 | 色值 |
|------|------|
| 主色调 | `#3B82F6` |
| 背景色 | `#0F172A` / `#1E293B` |
| 侧边栏背景 | `#1E293B` |
| 文本主色 | `#F8FAFC` |
| 文本次要 | `#CBD5E1` |
| 边框色 | `#334155` |

**医生端 vs 患者端差异化**：
- 医生端：主色调偏冷蓝（`#2563EB`），专业严谨
- 患者端：主色调偏暖蓝（`#0EA5E9`），亲和友好
- 老年模式：颜色对比度自动提升至 WCAG AAA 标准

### 13.2 字体排版

| 层级 | 字号（普通/老年模式） | 字重 | 用途 |
|------|---------------------|------|------|
| 大标题 | 24px / 28px | 600 (SemiBold) | 页面标题、欢迎页标题 |
| 标题1 | 20px / 24px | 600 | 面板标题、消息标题 |
| 标题2 | 18px / 22px | 500 (Medium) | 章节标题、卡片标题 |
| 正文 | 14px / 18px | 400 (Regular) | 正文内容、按钮文字 |
| 辅助文字 | 12px / 16px | 400 | 说明文字、时间戳、Tooltip |
| 小字 | 11px / 14px | 400 | 标签、角标、状态文字 |

- **字体族**：系统字体栈 `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **代码字体**：`"SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, monospace`
- **行高**：正文 1.6，标题 1.3，代码 1.5
- **段落间距**：正文段落间距 12px

### 13.3 间距与圆角

**间距系统（4px 基准）**：

| Token | 值 | 用途 |
|-------|----|------|
| `xs` | 4px | 图标与文字间距、紧凑内边距 |
| `sm` | 8px | 小间距、标签内边距 |
| `md` | 12px | 常规内边距、元素间距 |
| `lg` | 16px | 卡片内边距、消息间距 |
| `xl` | 24px | 区块间距、面板内边距 |
| `2xl` | 32px | 大区块间距、页面边距 |

**圆角系统**：

| Token | 值 | 用途 |
|-------|----|------|
| `sm` | 4px | 小按钮、标签、输入框 |
| `md` | 8px | 卡片、按钮、消息气泡 |
| `lg` | 12px | 大卡片、面板、模态框 |
| `full` | 9999px | 头像、圆形按钮、徽章 |

### 13.4 阴影层级

| 层级 | 阴影值 | 用途 |
|------|--------|------|
| `sm` | `0 1px 2px 0 rgb(0 0 0 / 0.05)` | 按钮悬浮、小卡片 |
| `md` | `0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)` | 卡片悬浮、下拉菜单 |
| `lg` | `0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)` | 模态框、弹出面板 |
| `xl` | `0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)` | 大型弹窗、右侧面板 |

### 13.5 动画与过渡

| 属性 | 时长 | 缓动函数 | 用途 |
|------|------|---------|------|
| 快速过渡 | 150ms | `ease-out` | 按钮悬浮、颜色变化、折叠展开 |
| 常规过渡 | 200ms | `ease-in-out` | 面板展开/收起、侧边栏折叠 |
| 慢速过渡 | 300ms | `ease-in-out` | 页面切换、模态框出现 |
| 旋转动画 | 1s 无限循环 | `linear` | 加载状态、运行中指示器 |
| 脉冲动画 | 2s 无限循环 | `ease-in-out` | 思考中、录音中、打字光标 |

- 所有可交互元素必须有 hover/active 状态过渡
- 侧边栏/面板折叠使用平滑宽度动画
- 智能体执行状态变化要有明确的视觉反馈动画
- 老年模式下动画速度适当放慢（1.5x），避免快速闪烁

### 13.6 组件规范

**按钮**：
- 主按钮：主色调背景+白色文字，圆角 `md`
- 次要按钮：边框+浅色背景
- 图标按钮：正方形/圆形，hover 有背景色
- 按钮最小尺寸：普通模式 32×32px，老年模式 48×48px

**输入框**：
- 内嵌式设计（Trae 风格），与背景融合
- 聚焦时有主色调边框高亮
- 支持多行自动增高
- 圆角 `lg`，内边距 `md`

**卡片**：
- 浅色背景 + 细边框（浅色主题）或深色背景 + 细边框（深色主题）
- 圆角 `md`/`lg`
- hover 时轻微上浮 + 阴影增强

**工具调用卡片**：
- 折叠状态：工具图标+名称+状态徽章，单行紧凑显示
- 展开状态：显示参数 JSON（语法高亮）+ 执行结果 + 耗时
- 状态颜色：运行中（蓝色+旋转）、完成（绿色✓）、失败（红色✗）

### 13.7 适老化设计（患者端老年模式）

| 特性 | 普通模式 | 老年模式 |
|------|---------|---------|
| 适用端 | - | 仅患者端，默认开启 |
| 切换方式 | - | 左侧边栏底部开关按钮 |
| 基础字号 | 14px | 18px |
| 按钮最小尺寸 | 32px | 48px |
| 颜色对比度 | ≥ 4.5:1 (AA) | ≥ 7:1 (AAA) |
| 行高 | 1.6 | 1.8 |
| 点击区域 | - | 所有可点击元素 ≥ 48×48px |
| 语音交互 | 可选 | 默认开启自动朗读、语音优先 |
| 动画速度 | 1x | 0.7x（放慢） |
| 确认机制 | 单次点击 | 关键操作二次确认 |
| 文字提示 | 简洁 | 更详细、通俗易懂 |
| 自动播放 | 关闭 | AI 回复默认自动语音播报 |

### 13.8 响应式设计断点

| 断点 | 宽度 | 布局调整 |
|------|------|---------|
| 桌面端 | ≥ 1280px | 三栏完整显示（侧边栏+聊天区+右侧面板） |
| 小屏桌面 | 1024-1279px | 右侧面板默认收起，按需展开 |
| 平板端 | 768-1023px | 左侧边栏默认折叠为图标栏，右侧面板覆盖式展开 |
| 手机端 | < 768px | 侧边栏抽屉式展开，右侧面板全屏覆盖，优先展示聊天区 |

- 所有断点下核心对话功能必须可用
- 手机端语音交互优先级提升
- 右侧面板在小屏设备上采用全屏覆盖模式

### 13.9 交互细节

- 所有图标需显示 Tooltip 提示文字（折叠侧边栏时必须显示）
- 鼠标悬停时显示功能说明（延迟 300ms 显示）
- 点击反馈：按钮点击时有轻微缩放（0.98）或颜色变化
- 加载状态：所有异步操作必须有加载指示器（旋转/骨架屏/脉冲）
- 错误状态：错误信息必须清晰可见，提供操作建议（如"重试"按钮）
- 空状态：新会话、无搜索结果等场景要有友好的空状态提示和引导
- 滚动：聊天区滚动平滑，长内容自动滚动到底部（用户手动滚动后暂停自动滚动）
- 无障碍：支持键盘导航（Tab/Enter/Esc）、屏幕阅读器、焦点可见

---

## 14. 开发原则

### 14.1 架构原则

- **系统化思维**：企业级系统架构设计
- **模块化设计**：RAG、Memory、Skill、Search、Voice、Privacy 等模块解耦，每个模块定义清晰的输入输出接口（Protocol/ABC），模块间通过依赖注入解耦，模块内部可独立替换实现、独立测试、独立优化
- **可扩展性**：便于后续迭代升级，新模块可插拔式接入
- **技术选型优先级**：以本文档为需求基准，优先使用 AgentScope 框架已提供的能力，仅当 AgentScope 不能满足设计要求时才引入外部技术栈（详见 2.1.1 节）

### 14.2 模块化设计规范

> **核心要求：Agent Harness 的各功能模块必须采用模块化设计，以便后期由不同开发人员负责优化。每个模块必须留好输入输出接口，模块内部允许后来的开发人员进一步优化——但这不意味着当前开发可以敷衍了事，当前的开发必须认真完成，不能只是做个 Demo 样例。**

**模块化架构总览：**

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI 应用层                            │
│  (REST API 路由、SSE 流式响应、中间件链、静态资源服务)              │
├─────────────────────────────────────────────────────────────────┤
│                     Agent Harness 编排层                         │
│  (智能体调度、ReAct 循环、上下文组装、安全检查点)                    │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│  RAG     │  Memory  │  Skill   │  Search  │  Voice   │  Privacy │
│  检索模块 │  记忆模块 │  技能模块 │  搜索模块 │  语音模块 │  隐私模块 │
├──────────┴──────────┴──────────┴──────────┴──────────┴──────────┤
│                     AgentScope 核心引擎                          │
│  (Agent、Model、Message、Tool、Middleware、Permission)            │
├─────────────────────────────────────────────────────────────────┤
│                     外部服务适配层                                │
│  (LLM API、ASR/TTS、Embedding/Rerank、搜索API、文档解析)          │
└─────────────────────────────────────────────────────────────────┘
```

**设计规范：**

1. **接口先行**：每个模块必须定义清晰的输入输出接口（Python Protocol / ABC），接口定义与实现分离
2. **依赖注入**：模块间通过依赖注入（而非硬编码 import）解耦，便于替换和测试
3. **单一职责**：每个模块只负责一件事，模块内部高内聚，模块间低耦合
4. **可替换性**：任何模块的内部实现都可以被替换，只要新实现满足相同的输入输出接口
5. **独立测试**：每个模块必须能独立运行单元测试，不依赖其他模块的运行状态
6. **文档完整**：每个模块必须有 README 说明模块职责、接口定义、配置方式、使用示例

### 14.3 质量原则

- **生产级代码**：所有模块必须达到可部署标准，不允许 Demo 质量的临时代码
- **接口先行**：先定义接口（Protocol），再实现功能，确保模块可替换
- **多模型兜底**：主模型失败自动切换备用模型
- **严格循证**：所有医疗相关内容必须有循证来源
- **合规优先**：大模型生成内容需有免责声明
- **独立可测**：每个模块必须能独立运行单元测试，不依赖其他模块的运行状态

### 14.4 代码质量标准

| 维度 | 要求 |
|------|------|
| 类型安全 | 全量使用 Python Type Hints，所有函数签名必须有类型注解 |
| 接口定义 | 每个模块必须有 Protocol/ABC 定义的输入输出接口 |
| 错误处理 | 所有外部调用（API/数据库/文件）必须有 try-except 和降级策略 |
| 日志记录 | 关键操作必须有结构化日志（使用 Python logging，包含 request_id、session_id） |
| 单元测试 | 每个模块的核心逻辑必须有单元测试，测试覆盖率 ≥ 80% |
| 文档注释 | 每个类和公共方法必须有 docstring，说明职责、参数、返回值 |
| 代码风格 | 遵循 PEP 8，使用 ruff 格式化，使用 mypy 类型检查 |

### 14.5 模块间集成规范

| 规范 | 说明 |
|------|------|
| 依赖注入 | 模块间通过构造函数注入依赖，不使用全局单例 |
| 接口隔离 | 模块只依赖其他模块的 Protocol 接口，不依赖具体实现 |
| 事件驱动 | 模块间异步通信通过事件总线或回调函数，避免直接调用 |
| 配置外部化 | 所有配置通过 .env 文件或配置类注入，不硬编码 |

---

## 15. 设计约束

### 15.1 安全约束

- 禁止硬编码敏感信息（API Key 等）
- 必须通过 `.env` 文件注入环境变量
- 禁止将 `.env` 文件提交至 Git 仓库
- 可提交 `.env.example` 示例文件（仅包含变量名）

### 15.2 测试约束（两阶段 Mock 策略）

- **UI 构建阶段（第一个计划）**：允许使用 Mock 数据用于交互调试与布局验证
- **功能实现阶段（第二个计划起）**：禁止使用 Mock，所有测试必须真实调用模型服务和工具服务
- 开发初期将所有环境变量存放在 `.env` 文件中
- Mock 数据必须集中放置在 `src/data/mock/` 目录，便于第二阶段一次性删除

---

## 16. 开发规划

### 16.1 第一阶段：MVP（适配 IGA Page 部署）

#### 目标

完成**符合 IGA Page 部署规范**的前端页面设计与 Demo 开发，确保 Demo 可无缝部署至 IGA Page 平台并稳定运行，同时验证核心交互与大模型能力体验。

#### 产出

- 基于 `gerclaw-main` 文件夹构建的子项目，严格遵循 IGA Page 的工程目录规范、资源引用规则与部署配置要求；
- 包含 IGA Page 部署所需的完整配置文件（如部署清单、环境适配配置、资源映射文件等）；
- 可直接提交至 IGA Page 平台的部署包（或可一键构建部署包的脚本）。

#### 特性

1. **视觉与交互一致性**：前端页面视觉与交互逻辑与最终系统完全一致，且适配 IGA Page 的页面渲染规则、响应式约束与组件兼容要求；

2. **深度环境适配**：
   - 遵循 IGA Page 的资源加载规范（如静态资源 CDN 映射、跨域策略适配）；
   - 兼容 IGA Page 的运行时环境（如环境变量注入方式、API 请求代理规则）；
   - 满足 IGA Page 的性能与安全校验要求（如资源体积限制、脚本执行权限规范）；

3. **核心功能可用**：
   - 模型调用逻辑适配 IGA Page 的前端代码执行规则，确保无跨域、权限类运行异常；
   - 语音输入/合成、文件上传等交互能力适配 IGA Page 的设备权限调用规范；

4. **演示能力完整**：Demo 在 IGA Page 部署后，可完整展示医生端/患者端核心交互流程（对话、处方生成入口、评估量表展示等），且数据交互符合 IGA Page 的存储/缓存规则。

#### IGA Page 部署适配要求

- Demo 开发阶段需同步输出《IGA Page 部署手册》，包含部署步骤、环境变量配置说明、常见问题排查方案；
- 前端代码中模型调用部分需预留与 IGA Page 平台 API 网关的对接接口，便于后续联调；
- 测试验证环节需以 IGA Page 的线上运行环境为基准，确保 Demo 在该环境下的功能完整性与稳定性。

### 16.2 第二阶段：产品落地

#### 16.2.1 总体目标

- **目标**：完成系统后端开发，实现全栈功能，代码质量达到生产部署标准
- **产出**：完整的 Docker 化系统，所有模块可独立运行、可独立测试、可独立优化
- **质量标准**：每个模块必须有完整的输入输出接口定义、单元测试、错误处理和文档说明——这不是 Demo，是可交付的生产代码
- **技术选型准则**：以本文档为需求基准，优先使用 AgentScope 框架能力，仅当 AgentScope 不能满足设计要求时才引入外部技术栈（详见 2.1.1 节）
- **模块化要求**：各功能模块必须模块化设计，留好输入输出接口（详见 14.2 节），各模块的详细接口定义见 4.6~4.15 节

#### 16.2.2 开发步骤与里程碑

**步骤一：基础设施搭建（第 1 周）**
- [ ] FastAPI 项目脚手架（目录结构、依赖管理、配置加载）
- [ ] 数据库初始化（PostgreSQL 表结构、Redis 连接）
- [ ] 前端项目集成（Next.js 构建产物通过 FastAPI 静态文件服务）
- [ ] Docker 化配置（Dockerfile、docker-compose.yml）
- [ ] 环境变量配置（.env.example 模板）

**步骤二：核心引擎对接（第 2-3 周）**
- [ ] Agent Harness 模块实现（ReAct 循环、上下文组装、SSE 事件流）——接口定义见 4.6 节
- [ ] 模型调用封装（AgentScope ChatModel 统一接口、多模型兜底）——配置方式见 4.5 节
- [ ] Memory 模块实现（短期记忆存取、上下文压缩）——接口定义见 4.8 节
- [ ] 前后端对话流打通（SSE 流式对话完整链路）——通信协议见 4.16 节

**步骤三：功能模块开发（第 4-6 周）**
- [ ] RAG 模块实现（知识库索引、混合检索、重排）——接口定义见 4.7 节
- [ ] Search 模块实现（AnySearch + Tavily 双通道）——接口定义见 4.10 节
- [ ] Skill 模块实现（技能注册、加载、执行）——接口定义见 4.9 节
- [ ] Voice 模块实现（ASR + TTS 流式处理）——接口定义见 4.11 节
- [ ] Privacy 模块实现（PHI 脱敏、输入过滤、免责声明）——接口定义见 4.12 节
- [ ] Document 模块实现（MinerU 文档解析）——接口定义见 4.15 节

**步骤四：业务功能集成（第 7-8 周）**
- [ ] 五大处方模块实现（信息收集、处方生成、四重校验、导出）——接口定义见 4.13 节
- [ ] CGA 评估模块实现（量表管理、对话化采集、自动计分、报告）——接口定义见 4.14 节
- [ ] 用户与会话管理（登录、历史会话、健康画像）
- [ ] 前端右侧面板对接（处方预览、CGA 评估界面、引用详情）

**步骤五：集成测试与部署（第 9 周）**
- [ ] 全链路集成测试（对话→工具调用→结果渲染完整流程）
- [ ] Docker 镜像构建与测试
- [ ] 通过 `modelscope-studio` 技能部署至 ModelScope
- [ ] 性能测试与优化

#### 16.2.3 部署方案

**Docker 化部署：**

```yaml
# docker-compose.yml 结构
services:
  gerclaw-app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres
      - redis
      - qdrant

  postgres:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage
```

**部署目标**：通过 `modelscope-studio` 技能部署至 ModelScope 平台，遵循其 Docker 容器化部署规范。

---

## 17. 参考资料（必须完整阅读！不得有遗漏！）

> ⚠️ **三份核心文档的优先级关系（详见 2.1.1 节）：**
> 1. **本文档（gerclaw设计要求.md）**：需求基准，定义"做什么"和"做到什么标准"——**最高优先级**
> 2. **AgentScope 框架总览**：技术实现参考，定义"怎么做"——**优先使用其已有能力**
> 3. **技术选型推荐**：补充方案，仅当 AgentScope 不能满足需求时参考——**最低优先级，按需引用**

| 资料 | 路径 | 用途 | 优先级 |
|------|------|------|--------|
| AgentScope 框架总览 | `/Users/qizs/conclusion/gerclaw/agentscope参考/00_总览.md` | 智能体框架学习入口，技术实现首选参考 | 高（技术实现首选） |
| AgentScope 参考文档（15个模块） | `/Users/qizs/conclusion/gerclaw/agentscope参考/` | 各功能模块对应的 AgentScope 能力映射 | 高（按模块查阅） |
| AgentScope 示例代码 | `/Users/qizs/conclusion/gerclaw/agentscope-examples/` | 可运行的示例代码，开发时对照参考 | 高（运行验证） |
| 技术选型推荐 | `/Users/qizs/conclusion/gerclaw/gerclaw前期调研/GerClaw_技术选型推荐.md` | 仅当 AgentScope 不能满足需求时的补充方案 | 低（按需引用） |
| 五大处方模板 | `/Users/qizs/conclusion/gerclaw/输入输出/五大处方报告模板.md` | 处方报告结构参考 | - |
| 患者数据样例 | `/Users/qizs/conclusion/gerclaw/输入输出/hzj*` | 输入字段模板参考 | - |
| 评估量表 | `/Users/qizs/conclusion/gerclaw/问卷量表` | 老年综合评估参考 | - |
| 本地知识库 | `/Users/qizs/conclusion/gerclaw/本地知识库/md` | RAG 知识源 | - |
| MinerU 技能 | `/Users/qizs/.claude/skills/mineru` | 文档解析工具 | - |
| AnySearch 技能 | `/Users/qizs/.claude/skills/anysearch-skill-main` | 联网搜索工具 | - |

---

## 18. 补充说明

本文件未详尽描述的功能，需参考以下资料获取详细信息：

1. 上述参考资料中的功能描述与设计思路
2. **UI/UX 交互与视觉效果对标 Trae Work 产品实现**（三栏布局、智能体执行可视化、输入框交互、工具调用卡片等）
3. 医疗行业相关合规要求与最佳实践
4. 适老化设计参考 WCAG 2.1 AAA 标准
5. 所有医疗内容必须包含循证来源字段（EvidenceSource），禁止编造医学信息
6. 每次 AI 输出底部必须强制追加免责声明："内容由 AI 生成，仅供参考。身体不适请及时就医。"
7. **模块化设计是硬性要求**：Agent Harness 的各功能模块（RAG、Memory、Skill、Search、Voice、Privacy 等）必须模块化设计，留好输入输出接口，便于后期由不同开发人员负责优化（详见 14.2 节，各模块接口定义见 4.6~4.15 节）
8. **技术选型必须遵循优先级准则**：以本文档为需求基准，优先使用 AgentScope 框架能力，仅当 AgentScope 不能满足设计要求时才引入外部技术栈（详见 2.1.1 节）。禁止跳过 AgentScope 直接使用技术选型推荐中的方案
9. **当前开发必须认真完成**：模块化设计允许后续优化，但这不意味着当前开发可以敷衍了事。每个模块必须达到生产级代码质量——完整的接口定义、错误处理、单元测试和文档说明，不允许 Demo 质量的临时代码
