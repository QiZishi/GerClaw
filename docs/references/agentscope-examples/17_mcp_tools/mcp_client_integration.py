# -*- coding: utf-8 -*-
"""GerClaw 医学 MCP 工具集 客户端集成示例。

本示例演示如何：

1. 使用 ``MCPClient`` + ``StdioMCPConfig`` 以 stdio 方式连接同目录下的
   ``mcp_medical_server.py`` MCP 医疗工具服务；
2. 将 MCP 客户端注册到 Agent 的 ``Toolkit``，使大模型（DashScope
   通义千问）可自动调用 ``get_drug_info`` / ``calculate_bmi`` 工具；
3. 模拟"张大爷咨询二甲双胍用药"的老年医疗咨询场景，Agent 会先计算
   BMI 评估老年营养状态，再查询药品信息，综合给出面向老年人的建议。

运行前置条件：

- 已安装 ``agentscope``、``dashscope``（含 ``openai`` SDK）、``mcp``
- 配置环境变量 ``DASHSCOPE_API_KEY``（从 DashScope 控制台获取）
- 同目录下存在 ``mcp_medical_server.py``

运行方式::

    export DASHSCOPE_API_KEY="sk-xxxx"
    python mcp_client_integration.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from pydantic import SecretStr

from agentscope.agent import Agent
from agentscope.mcp import MCPClient, StdioMCPConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import UserMsg
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit
from agentscope.state import AgentState


# ---------------------------------------------------------------------------
# 1. 路径与 API Key 配置
# ---------------------------------------------------------------------------
# 当前示例文件所在目录，用于定位 mcp_medical_server.py
_THIS_DIR = Path(__file__).resolve().parent
_SERVER_PATH = _THIS_DIR / "mcp_medical_server.py"

# 从环境变量读取 DashScope API Key，不硬编码
_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()
_MODEL_NAME = os.environ.get("DASHSCOPE_MODEL", "qwen-plus")


# ---------------------------------------------------------------------------
# 2. 主流程
# ---------------------------------------------------------------------------
async def main() -> None:
    """异步主入口：构建模型 → 连接 MCP → 创建 Agent → 模拟张大爷咨询。"""

    # 2.1 校验 API Key
    if not _API_KEY:
        print(
            "[错误] 未检测到 DASHSCOPE_API_KEY 环境变量。\n"
            "请先执行: export DASHSCOPE_API_KEY=\"sk-你的密钥\"",
            file=sys.stderr,
        )
        sys.exit(1)

    if not _SERVER_PATH.exists():
        print(
            f"[错误] 未找到 MCP 服务文件: {_SERVER_PATH}\n"
            "请确认 mcp_medical_server.py 与本脚本位于同一目录。",
            file=sys.stderr,
        )
        sys.exit(1)

    print("=" * 60)
    print("GerClaw 老年医疗 AI — 医学工具集 MCP 集成演示")
    print("=" * 60)
    print(f"使用模型: {_MODEL_NAME}")
    print(f"MCP 服务: {_SERVER_PATH.name}")
    print()

    # 2.2 构建 DashScope Chat 模型
    # DashScopeCredential 使用 pydantic SecretStr 包裹 API Key 避免日志泄露
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=SecretStr(_API_KEY)),
        model=_MODEL_NAME,
        stream=False,           # 示例使用非流式，便于一次性打印完整回复
        temperature=0.3,        # 医疗问答建议低温度以减少幻觉
    )

    # 2.3 创建 MCP 客户端（STDIO 必须 is_stateful=True）
    # 通过 StdioMCPConfig 指定以子进程方式执行 `python mcp_medical_server.py`
    mcp_client = MCPClient(
        name="medical_tools",          # 工具名前缀 mcp__medical_tools__*
        is_stateful=True,              # STDIO 必须为有状态模式
        mcp_config=StdioMCPConfig(
            command=sys.executable,    # 使用当前 Python 解释器，兼容虚拟环境
            args=[str(_SERVER_PATH)],
        ),
        execution_timeout=30.0,        # 医疗工具调用超时 30 秒
    )

    try:
        # 2.4 显式建立 MCP 连接（STDIO 会拉起子进程）
        print("[1/3] 正在连接医学 MCP 服务...")
        await mcp_client.connect()
        print(f"  连接成功: is_connected={mcp_client.is_connected}")

        # 列出 MCP 服务提供的工具（用于演示/日志）
        mcp_tools = await mcp_client.list_tools()
        tool_names = [t.name for t in mcp_tools]
        print(f"  MCP 工具列表: {tool_names}")
        print()

        # 2.5 构建 Toolkit，将 MCP 客户端注册到 basic 工具组
        # Toolkit(mcps=[...]) 会自动在首次 get_tool_schemas() 时拉取所有工具
        toolkit = Toolkit(mcps=[mcp_client])

        # 2.6 创建老年医疗 Agent
        system_prompt = (
            "你是 GerClaw 老年医疗 AI 助手，专门为 60 岁以上的老年患者"
            "提供通俗易懂、安全可靠的健康咨询服务。\n\n"
            "【服务规范】\n"
            "1. 回答使用中文，语气亲切、耐心、语速慢（文字表达简洁）。\n"
            "2. 涉及用药、检查结果时，必须优先调用 medical_tools 工具组"
            "提供的工具（get_drug_info / calculate_bmi 等），\n"
            "   不要凭记忆编造药品信息或数值分级。\n"
            "3. 对老年患者要主动提醒：药物剂量需遵医嘱、注意不良反应、"
            "不要自行停药/加量。\n"
            "4. 涉及 BMI / 肾功能等量化评估时，先调用计算工具，再结合"
            "老年人群特点解读。\n"
            "5. 结尾必须附加一句话：「以上建议仅供参考，具体诊疗请以"
            "医生面诊为准」。"
        )
        agent = Agent(
            name="GerClaw老年助手",
            system_prompt=system_prompt,
            model=model,
            toolkit=toolkit,
            state=AgentState(session_id="demo_zhang_daye_001"),
        )

        # 2.7 构造张大爷的咨询消息并调用 Agent
        # 场景：张大爷 72 岁，身高 170cm，体重 78kg，患 2 型糖尿病，
        # 想了解二甲双胍怎么吃、有什么注意事项
        user_message = UserMsg(
            name="张大爷",
            content=(
                "大夫您好，我姓张，今年 72 岁，身高 1 米 7，体重 78 公斤，"
                "有 2 型糖尿病。社区医院给我开了二甲双胍，我想问问这个药"
                "是治什么的？怎么吃？像我这年纪吃有啥要注意的不？"
                "对了，我这个体重算不算胖啊？"
            ),
        )

        print("[2/3] 张大爷发起咨询，Agent 正在思考并调用工具...")
        print("-" * 60)

        # agent.reply() 会执行 ReAct 循环：模型决策→调用工具→回填结果→
        # 继续推理→给出最终回答。工具调用过程通过 MCP stdio 通道完成。
        reply_msg = await agent.reply(user_message)

        # 2.8 输出最终回答
        print()
        print("[3/3] Agent 回复：")
        print("-" * 60)
        # reply_msg.content 在非流式下可能是 str 或 list[Block]
        if isinstance(reply_msg.content, str):
            print(reply_msg.content)
        else:
            for block in reply_msg.content:
                # 仅打印文本块，忽略 tool_call/tool_result 中间块
                if getattr(block, "type", None) == "text":
                    print(block.text)
        print("-" * 60)
        print("\n演示完成。")

    finally:
        # 2.9 关闭 MCP 连接（确保子进程被正确终止）
        if mcp_client.is_connected:
            await mcp_client.close()
            print("[清理] MCP 连接已关闭。")


if __name__ == "__main__":
    # asyncio.run 负责创建/关闭事件循环
    asyncio.run(main())
