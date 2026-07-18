# -*- coding: utf-8 -*-
"""
human_in_the_loop.py —— GerClaw老年医疗AI · 人机回环(HITL)医生审批演示

对应参考索引: agentscope参考/07_AgentHarness回路.md §7
核心API: Agent.reply_stream() + RequireUserConfirmEvent + UserConfirmResultEvent
        + ConfirmResult + PermissionEngine

功能: 演示完整医生审批流程：
  78岁高血压患者主诉头晕→Agent尝试开药→触发RequireUserConfirmEvent暂停
  →命令行模拟医生审批(y批准/n拒绝/a批准并记住规则)
  →传入UserConfirmResultEvent恢复reply→Agent执行工具并给出最终建议

运行: export DASHSCOPE_API_KEY=xxx && python human_in_the_loop.py
"""

import asyncio
import json
import os
import sys
from typing import Any

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.event import EventType, UserConfirmResultEvent, ConfirmResult
from agentscope.message import ToolCallBlock, UserMsg, SystemMsg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.permission import (
    PermissionContext, PermissionMode, PermissionRule,
    PermissionBehavior, PermissionDecision,
)
from agentscope.state import AgentState
from agentscope.tool import ToolBase, Toolkit, ToolChunk


# ---- 1. 医疗工具定义 ----

class PrescribeDrug(ToolBase):
    """处方开立 — 高风险，始终需医生确认；老年高风险药物bypass_immune。"""
    name = "prescribe_drug"
    description = "开立处方药物。参数: drug_name(药品名), dosage(剂量用法), indication(适应症), notes(注意事项)。调用后需医生审批。"
    input_schema = {"type": "object", "properties": {
        "drug_name": {"type": "string"}, "dosage": {"type": "string"},
        "indication": {"type": "string"}, "notes": {"type": "string"}},
        "required": ["drug_name", "dosage", "indication"]}
    is_concurrency_safe = False; is_read_only = False; is_external_tool = False; is_mcp = False

    async def check_permissions(self, tool_input, context):
        drug = tool_input.get("drug_name", "")
        if drug in {"地西泮", "苯海拉明", "阿米替林"}:  # Beers Criteria高风险
            return PermissionDecision(behavior=PermissionBehavior.ASK,
                message=f"Beers老年高风险药物({drug})需主治医师审批",
                decision_reason="beers_criteria", bypass_immune=True)
        return PermissionDecision(behavior=PermissionBehavior.PASSTHROUGH, message="处方需确认")

    async def __call__(self, drug_name, dosage, indication, notes="", **kw):
        return ToolChunk(content=[TextBlock(
            text=f"[处方已开立] {drug_name} {dosage} | 适应症:{indication} | 注意:{notes or '无'} | 状态:已审批通过")])


class QueryDrugInfo(ToolBase):
    """药品查询 — 只读低风险，自动ALLOW。"""
    name = "query_drug_info"
    description = "查询药品说明书（只读，自动放行）。参数: drug_name"
    input_schema = {"type": "object", "properties": {"drug_name": {"type": "string"}}, "required": ["drug_name"]}
    is_concurrency_safe = True; is_read_only = True; is_external_tool = False; is_mcp = False

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="只读查询自动放行")

    async def __call__(self, drug_name, **kw):
        return ToolChunk(content=[TextBlock(text=f"[药品信息]{drug_name}:老年患者需注意剂量调整,建议从小剂量起始。")])


# ---- 2. 模拟医生审批工作台 ----

async def doctor_console(agent, event) -> UserConfirmResultEvent:
    """命令行模拟医生审批。生产环境应替换为Web工作台推送+API回调。"""
    print(f"\n{'─'*58}\n\033[93m  ⚠ 医生审批工作台 — {len(event.tool_calls)}项待审批\033[0m")
    results = []
    for i, tc in enumerate(event.tool_calls, 1):
        try:
            inp = json.loads(tc.input) if isinstance(tc.input, str) else tc.input
        except Exception:
            inp = {"raw": tc.input}
        print(f"\n  [{i}/{len(event.tool_calls)}] {tc.name}")
        for k, v in inp.items():
            print(f"    · {k}: {v}")
        if tc.suggested_rules:
            print(f"    建议规则: {[sr.tool_name for sr in tc.suggested_rules]}")
        while True:
            ans = input("  审批(y批准/n拒绝/a批准并记住规则/q退出): ").strip().lower()
            if ans in ("y", "n", "a", "q"):
                break
        if ans == "q":
            sys.exit(0)
        confirmed = ans in ("y", "a")
        rules = None
        if ans == "a" and tc.suggested_rules:
            rules = [PermissionRule(tool_name=sr.tool_name, rule_content=sr.rule_content,
                behavior=PermissionBehavior.ALLOW, source="doctor_approved") for sr in tc.suggested_rules]
            print("  ✓ 批准并记住规则")
        elif confirmed:
            print("  ✓ 批准（仅本次）")
        else:
            print("  ✗ 拒绝")
        results.append(ConfirmResult(confirmed=confirmed,
            tool_call=ToolCallBlock(id=tc.id, name=tc.name, input=tc.input), rules=rules))
    print(f"{'─'*58}\n  提交审批结果，恢复Agent...\n")
    return UserConfirmResultEvent(reply_id=event.reply_id, confirm_results=results)


# ---- 3. HITL事件流驱动 ----

async def run_with_hitl(agent: Agent, msg: str):
    """执行Agent，在ASK暂停点触发医生审批，循环直到REPLY_END。"""
    inputs = UserMsg(name="患者", content=msg)
    while True:
        pending = None
        async for ev in agent.reply_stream(inputs=inputs):
            match ev.type:
                case EventType.MODEL_CALL_START:
                    print(f"\033[94m[AI推理 - {ev.model_name}]\033[0m")
                case EventType.THINKING_BLOCK_DELTA:
                    print(f"\033[90m{ev.delta}\033[0m", end="", flush=True)
                case EventType.TEXT_BLOCK_DELTA:
                    print(ev.delta, end="", flush=True)
                case EventType.TOOL_CALL_START:
                    print(f"\n\033[94m[调用工具: {ev.tool_call_name}]\033[0m")
                case EventType.REQUIRE_USER_CONFIRM:
                    pending = ev
                    print(f"\n\033[93m[暂停等待医生审批...]\033[0m")
                    break
                case EventType.REPLY_END:
                    print("\n\033[92m[回复完成]\033[0m")
                    return
        if pending is not None:
            inputs = await doctor_console(agent, pending)
        else:
            break


# ---- 4. 主函数 ----

async def main():
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: 请设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    print("\n" + "="*58)
    print("  GerClaw · Human-in-the-Loop 医生审批演示")
    print("="*58)

    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus", stream=True, max_retries=2,
        parameters=DashScopeChatModel.Parameters(temperature=0.3, max_tokens=2048),
    )

    # 医疗权限上下文：DEFAULT模式 + 查询ALLOW + 处方/检查ASK
    ctx = PermissionContext(mode=PermissionMode.DEFAULT,
        allow_rules={"query_drug_info": [PermissionRule(tool_name="query_drug_info",
            rule_content=None, behavior=PermissionBehavior.ALLOW, source="medicalPolicy")]},
        ask_rules={"prescribe_drug": [PermissionRule(tool_name="prescribe_drug",
            rule_content=None, behavior=PermissionBehavior.ASK, source="medicalPolicy")]},
        deny_rules={})

    agent = Agent(
        name="GerClaw处方助手",
        system_prompt=(
            "你是GerClaw老年医疗AI平台处方助手。可用工具："
            "1)query_drug_info:查询药品信息(自动放行);"
            "2)prescribe_drug:开处方(需医生审批)。"
            "流程:先查药品信息→再调用prescribe_drug→等审批→审批通过后给用药指导。"
            "回复中文,语气亲切适合老年人。每次处方都须标注'请遵医嘱'。"
        ),
        model=model,
        toolkit=Toolkit(tools=[PrescribeDrug(), QueryDrugInfo()]),
        state=AgentState(permission_context=ctx),
        react_config=ReActConfig(max_iters=8, stop_on_reject=False),
    )

    await agent.observe(SystemMsg(name="患者档案", content=(
        "王大爷,78岁男性,高血压15年(氨氯地平5mg/日,BP 145/90),"
        "2型糖尿病8年(二甲双胍500mg bid),无过敏史。"
        "近一周头晕加重,晨起明显,自测BP 160/95。")))

    patient_msg = "医生您好,我最近头晕厉害,早上更明显,血压160多,一直吃氨氯地平,是不是需要调药或加量?"
    print(f"\n\033[1m患者(王大爷,78岁):\033[0m\n{patient_msg}\n")
    print("─"*58)

    await run_with_hitl(agent, patient_msg)

    print("\n" + "="*58)
    print("  演示完毕。提示: 生产环境应将doctor_console替换为Web工作台。")
    print("="*58 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
