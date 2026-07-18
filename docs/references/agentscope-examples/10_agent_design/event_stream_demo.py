# -*- coding: utf-8 -*-
"""
event_stream_demo.py —— GerClaw老年医疗AI · AgentScope流式事件演示

对应参考索引: agentscope参考/10_智能体设计.md §7.1
核心API: Agent.reply_stream() → AsyncGenerator[AgentEvent] (§2.1, §2.4)
        DashScopeChatModel构造 (§2.6)

功能: 演示reply_stream()流式输出，监听ThinkingBlock/TextBlock/ToolCall等
     AgentEvent事件，模拟75岁老年患者（张大爷）问诊的逐字输出和思考过程展示。

运行: export DASHSCOPE_API_KEY=xxx && python event_stream_demo.py
"""

import asyncio
import os
import sys
import time

from agentscope.agent import Agent, ContextConfig, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.event import EventType
from agentscope.message import UserMsg, SystemMsg
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit

# ===== 老年医疗模拟数据（虚构，无真实PHI） =====
PATIENT = {"name": "张大爷", "age": 75}
PROFILE = (
    f"患者：{PATIENT['name']}，{PATIENT['age']}岁，男性。"
    f"既往史：高血压10年（氨氯地平5mg/日），2型糖尿病5年（二甲双胍500mg bid）。"
    f"过敏：青霉素。"
)
CONSULTATION_TURNS = [
    "大夫您好，我最近一个礼拜总是头晕，早上起床的时候晕得厉害，"
    "有时候站起来眼前发黑，要扶着墙才好。我有高血压和糖尿病，一直吃药。",
    "头晕的时候感觉天旋地转的，昨天早上差点摔倒。血压早上量150/95，比平时高。"
    "最近睡眠不好，晚上起夜两三次。",
]


def _sep(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


async def stream_turn(agent: Agent, msg: str, turn: int) -> dict:
    """执行单轮流式问诊，分类处理AgentEvent事件，返回统计信息。"""
    stats = {"thinking": 0, "text": 0, "model_calls": 0}
    _sep(f"第 {turn} 轮")
    print(f"\n{PATIENT['name']}: {msg}\n")
    print("GerClaw助手: ", end="", flush=True)

    async for ev in agent.reply_stream(UserMsg(name="患者", content=msg)):
        match ev.type:
            case EventType.MODEL_CALL_START:
                stats["model_calls"] += 1
                print(f"\n\033[94m[AI分析中 - {ev.model_name}]\033[0m\n", end="", flush=True)
            case EventType.THINKING_BLOCK_START:
                print("\n\033[90m[思考] ", end="", flush=True)
            case EventType.THINKING_BLOCK_DELTA:
                stats["thinking"] += len(ev.delta)
                print(f"\033[90m{ev.delta}\033[0m", end="", flush=True)
            case EventType.THINKING_BLOCK_END:
                print("\n\033[0m", end="", flush=True)
            case EventType.TEXT_BLOCK_DELTA:
                stats["text"] += len(ev.delta)
                print(ev.delta, end="", flush=True)
                await asyncio.sleep(0.008)  # 模拟逐字效果
            case EventType.TOOL_CALL_START:
                print(f"\n\033[94m[调用工具: {ev.tool_call_name}]\033[0m ", end="", flush=True)
            case EventType.REQUIRE_USER_CONFIRM:
                print(f"\n\033[93m[需医生确认: {len(ev.tool_calls)}项]\033[0m", flush=True)
            case EventType.EXCEED_MAX_ITERS:
                print("\n\033[91m[推理轮次超限，建议转人工]\033[0m", flush=True)
            case EventType.REPLY_END:
                print()  # 收尾换行
    return stats


async def main() -> None:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: 请先设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    _sep("GerClaw老年医疗AI · 流式事件演示")
    print(f"患者: {PATIENT['name']}，{PATIENT['age']}岁 | 模型: qwen-max(思考模式)")
    print("说明: 灰色=AI思考过程，白色=对患者回复，蓝色=系统状态")

    # 构建模型（启用流式+思考模式）
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-max",
        stream=True,
        max_retries=3,
        context_size=131072,
        parameters=DashScopeChatModel.Parameters(
            thinking_enable=True, temperature=0.3, max_tokens=2048,
        ),
    )

    # 构建GerClaw问诊Agent（老年友好配置）
    agent = Agent(
        name="GerClaw问诊助手",
        system_prompt=(
            "你是GerClaw老年医疗AI平台的问诊助手，服务75岁左右老年患者。"
            "用通俗易懂的语言回答，避免专业术语，分点说明。"
            "诊断结论给依据和置信度，用'可能性较大'等概率表述。"
            "用药建议标注'请遵医嘱，建议咨询医生确认'。"
            "发现红旗症状（胸痛/呼吸困难/意识障碍）立即建议打120。"
        ),
        model=model,
        toolkit=Toolkit(),
        context_config=ContextConfig(trigger_ratio=0.85, reserve_ratio=0.2),
        react_config=ReActConfig(max_iters=10, stop_on_reject=True),
    )

    # 注入患者档案（不触发推理）
    await agent.observe(SystemMsg(name="患者档案", content=PROFILE))

    # 执行多轮问诊
    t0 = time.time()
    totals = {"thinking": 0, "text": 0, "model_calls": 0}
    for i, turn_msg in enumerate(CONSULTATION_TURNS, 1):
        s = await stream_turn(agent, turn_msg, i)
        for k in totals:
            totals[k] += s[k]

    # 统计摘要
    _sep("问诊统计")
    print(f"  轮次: {len(CONSULTATION_TURNS)}  耗时: {time.time()-t0:.1f}s")
    print(f"  模型调用: {totals['model_calls']}次  思考字数: {totals['thinking']}  回复字数: {totals['text']}")
    print("\n提示: 本演示医疗建议仅供参考，不能替代执业医师诊断。")


if __name__ == "__main__":
    asyncio.run(main())
