# -*- coding: utf-8 -*-
"""
message_blocks.py —— GerClaw老年医疗AI · 消息构建与多轮对话上下文演示

对应参考索引: agentscope参考/10_智能体设计.md §7.2
核心API: Msg工厂函数 UserMsg/AssistantMsg/SystemMsg (§2.2)
        ContentBlock: TextBlock/ThinkingBlock/DataBlock (§2.3)
        Msg.append_event() 从事件流增量构建消息 (§2.2)
        DashScopeChatModel构造 (§2.6)

功能: 演示Msg构建、TextBlock/ThinkingBlock/DataBlock组合、消息历史管理，
     使用append_event()从事件流重建消息，模拟医生-患者多轮问诊上下文。

运行: export DASHSCOPE_API_KEY=xxx && python message_blocks.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime

from agentscope.agent import Agent, ContextConfig, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.event import EventType
from agentscope.message import (
    AssistantMsg, DataBlock, Msg, SystemMsg, TextBlock, ThinkingBlock,
    URLSource, UserMsg,
)
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit

# ===== 老年医疗模拟数据（虚构，无真实PHI） =====
PATIENT = {"name": "张大爷", "age": 75, "gender": "男"}
PATIENT_RECORD = {
    "patient_id": "DEMO-0001",
    "name": PATIENT["name"], "age": PATIENT["age"], "gender": PATIENT["gender"],
    "vitals": {"BP": "150/95", "HR": "82", "FBG": "7.8mmol/L"},
    "diseases": ["高血压10年", "2型糖尿病5年"],
    "medications": ["氨氯地平5mg qd", "二甲双胍500mg bid"],
    "allergies": ["青霉素"],
    "chief_complaint": "近一周反复头晕，晨起明显，伴体位性黑矇",
    "updated": datetime.now().isoformat(),
}
SYSTEM_PROMPT = (
    "你是GerClaw老年医疗AI平台问诊助手，服务75岁左右老年患者及家属。"
    "用通俗语言，分点说明，诊断给依据和置信度，用药标注'请遵医嘱'，"
    "红旗症状（胸痛/呼吸困难/意识障碍）立即建议打120。"
)


def _sep(title: str) -> None:
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")


def _show_msg(msg: Msg, label: str = "") -> None:
    """打印消息摘要（角色、Block类型、文本预览）。"""
    tag = f"[{label}] " if label else ""
    role_cn = {"user": "用户", "assistant": "AI助手", "system": "系统"}.get(msg.role, msg.role)
    blocks = [b.type for b in msg.content]
    text = (msg.get_text_content() or "")[:80].replace("\n", " ")
    print(f"  {tag}{role_cn}({msg.name}) blocks={blocks} | {text}{'...' if len(msg.get_text_content() or '')>80 else ''}")


async def build_reply_from_stream(agent: Agent, user_msg: Msg) -> Msg:
    """通过reply_stream获取事件流，用append_event()增量构建完整回复Msg。"""
    reply = AssistantMsg(name=agent.name, content=[])
    print("  AI回复: ", end="", flush=True)
    async for ev in agent.reply_stream(user_msg):
        reply.append_event(ev)
        if ev.type == EventType.THINKING_BLOCK_DELTA:
            print(f"\033[90m{ev.delta}\033[0m", end="", flush=True)
        elif ev.type == EventType.TEXT_BLOCK_DELTA:
            print(ev.delta, end="", flush=True)
        elif ev.type == EventType.REPLY_END:
            print()
    return reply


def demo_block_construction() -> None:
    """演示各种ContentBlock的手动构建方式（不调用模型）。"""
    _sep("ContentBlock构建演示（不调用API）")

    # 1) TextBlock
    tb = TextBlock(text="张大爷您好，考虑体位性低血压可能性较大（约70%）。")
    print(f"  TextBlock: text={len(tb.text)}字")

    # 2) ThinkingBlock（推理过程）
    think = ThinkingBlock(thinking=(
        "患者75岁，高血压+糖尿病，晨起头晕+体位性黑矇，BP150/95。"
        "鉴别诊断：体位性低血压>高血压晨峰>药物副作用>颈椎病。"
    ))
    print(f"  ThinkingBlock: thinking={len(think.thinking)}字")

    # 3) DataBlock（结构化数据）
    db = DataBlock(
        source=URLSource(url="data:application/json,{}", media_type="application/json"),
        name="vital_signs",
    )
    print(f"  DataBlock: name={db.name}, media={db.source.media_type}")

    # 4) 组合AssistantMsg
    full = AssistantMsg(name="GerClaw", content=[think, tb, TextBlock(
        text="\n建议：1.监测卧立位血压 2.起床慢动作 3.尽快心内科复诊 请遵医嘱。")])
    print(f"  AssistantMsg: {len(full.content)}个Block, 文本总长{len(full.get_text_content() or '')}字")

    # 5) 角色约束验证
    try:
        Msg(name="x", role="user", content=[ThinkingBlock(thinking="test")])
        print("  [错误] user+ThinkingBlock应抛异常!")
    except ValueError:
        print("  角色约束验证通过: user消息不能含ThinkingBlock")

    # 6) 字符串自动包装
    simple = UserMsg(name="张大爷", content="谢谢大夫")
    print(f"  UserMsg(str自动包装): blocks={[b.type for b in simple.content]}")


async def main() -> None:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: 请设置 DASHSCOPE_API_KEY")
        sys.exit(1)

    _sep("GerClaw老年医疗AI · 消息构建与多轮对话演示")
    print(f"患者: {PATIENT['name']}，{PATIENT['age']}岁")

    # Block构建演示（不消耗API）
    demo_block_construction()

    # 构建模型和Agent
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-max", stream=True, max_retries=3, context_size=131072,
        parameters=DashScopeChatModel.Parameters(
            thinking_enable=True, temperature=0.3, max_tokens=2048),
    )
    agent = Agent(
        name="GerClaw助手", system_prompt=SYSTEM_PROMPT, model=model,
        toolkit=Toolkit(),
        context_config=ContextConfig(trigger_ratio=0.85, reserve_ratio=0.2),
        react_config=ReActConfig(max_iters=10, stop_on_reject=True),
    )

    # 构建消息历史
    history: list[Msg] = []

    # 系统消息
    sys_msg = SystemMsg(name="系统", content=SYSTEM_PROMPT)
    history.append(sys_msg)

    # 患者档案（DataBlock + TextBlock组合）
    record_json = json.dumps(PATIENT_RECORD, ensure_ascii=False)
    record_msg = UserMsg(name="EMR系统", content=[
        TextBlock(text=f"患者档案：{PATIENT['name']}{PATIENT['age']}岁，头晕一周。"),
        DataBlock(source=URLSource(
            url=f"data:application/json;base64,{record_json}",
            media_type="application/json"), name="patient_record"),
    ])
    history.append(record_msg)

    # 将历史注入Agent上下文
    for m in history:
        await agent.observe(m)

    # 多轮问诊
    _sep("多轮问诊对话")
    turns = [
        ("患者", "大夫我最近一周老是头晕，早上起床时最严重，站起来眼前发黑要扶墙。有高血压糖尿病一直吃药。"),
        (f"{PATIENT['name']}", "血压早上量150/95比平时高，昨天差点摔倒，晚上起夜两三次睡不好。"),
        ("家属（女儿）", "医生我是他女儿，请问需要调整降压药吗？现在吃氨氯地平5mg每天一次，能加量吗？"),
    ]
    for i, (speaker, text) in enumerate(turns, 1):
        print(f"\n── 第{i}轮 ──")
        umsg = UserMsg(name=speaker, content=text)
        _show_msg(umsg)
        reply = await build_reply_from_stream(agent, umsg)
        _show_msg(reply, "AI")
        history.extend([umsg, reply])

    # 历史总览
    _sep("对话历史总览")
    print(f"  总消息数: {len(history)}")
    for i, m in enumerate(history, 1):
        role = {"user": "U", "assistant": "A", "system": "S"}[m.role]
        txt = (m.get_text_content() or "")[:50].replace("\n", " ")
        print(f"  [{i:02d}] {role} {m.name:10s} | {txt}")

    _sep("演示结束")
    print("  所有患者数据均为虚构，医疗建议仅供参考，不能替代执业医师诊断。")


if __name__ == "__main__":
    asyncio.run(main())
