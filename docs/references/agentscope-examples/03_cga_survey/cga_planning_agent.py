# -*- coding: utf-8 -*-
"""
cga_planning_agent.py — GerClaw CGA评估对话化示例（Plan模式 + system_prompt引导）

演示使用Agent的system_prompt引导CGA评估按 ADL→IADL→MMSE→GDS→MNA 顺序分步骤提问，
每次只问一个问题，答案记录到state.context。使用内置Plan工具管理维度进度，
自定义RecordAnswerTool记录答案到state.middle_context。
模拟场景：78岁王爷爷在社区做CGA初筛，"小葛"用聊天方式逐项询问。
运行：export DASHSCOPE_API_KEY="your-key" && python cga_planning_agent.py
"""
from __future__ import annotations
import asyncio, os, sys
from typing import Any
from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import TextBlock, UserMsg
from agentscope.model import DashScopeChatModel
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.state import Task
from agentscope.tool import ToolBase, ToolChunk, Toolkit, TaskCreate, TaskList, TaskUpdate, TaskGet

# CGA维度定义（简化条目）
CGA = [
    {"id":"ADL","name":"日常活动能力","desc":"吃饭穿衣洗漱如厕",
     "qs":[{"id":"ADL_Q1","text":"平时吃饭，您自己能把饭菜送到嘴里吗？","opts":{"完全独立":10,"需部分帮助":5,"需喂饭":0}},
           {"id":"ADL_Q2","text":"洗脸、刷牙、梳头您自己能做吗？","opts":{"完全独立":5,"需要帮助":0}},
           {"id":"ADL_Q3","text":"穿衣服、扣扣子您自己能行吗？","opts":{"完全独立":10,"需帮扣扣子":5,"完全需帮穿":0}}]},
    {"id":"IADL","name":"工具性日常活动","desc":"打电话购物做饭服药",
     "qs":[{"id":"IADL_Q1","text":"您自己能拨打电话吗？","opts":{"能自己打":1,"能接不会拨":0}}]},
    {"id":"MMSE","name":"认知筛查","desc":"记忆定向计算","qs":[]},
    {"id":"GDS","name":"抑郁筛查","desc":"近两周情绪","qs":[]},
    {"id":"MNA","name":"营养评估","desc":"食欲体重饮食","qs":[]},
]
TOTAL = sum(len(s["qs"]) for s in CGA if s["qs"])

class RecordAnswer(ToolBase):
    """记录答案并前进到下一题（状态注入式工具）。"""
    name="record_answer"; is_concurrency_safe=False; is_read_only=False; is_state_injected=True
    description="老人回答后调用此工具记录答案。参数answer为回答摘要，score为得分。返回下一题。"
    input_schema={"type":"object","properties":{"answer":{"type":"string"},"score":{"type":"integer"}},"required":["answer","score"]}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,answer,score,_agent_state=None,**kw):
        s=_agent_state.middle_context.setdefault("survey",_init())
        si,qi=s["si"],s["qi"]; sec=CGA[si]; q=sec["qs"][qi]
        s["answers"][q["id"]]={"answer":answer,"score":score}; s["cnt"]+=1
        qi+=1; trans=""
        if qi>=len(sec["qs"]):
            si+=1; qi=0
            for t in _agent_state.tasks_context.tasks:
                if t.metadata.get("scale")==sec["id"]:t.state="completed"
            while si<len(CGA) and not CGA[si]["qs"]:si+=1
            if si>=len(CGA):
                return ToolChunk(content=[TextBlock(text="【评估完成】所有维度已问完，请给出总结反馈。")])
            ns=CGA[si]
            for t in _agent_state.tasks_context.tasks:
                if t.metadata.get("scale")==ns["id"]:t.state="in_progress"
            trans=f"【维度切换】{sec['name']}完成，接下来：{ns['name']}（{ns['desc']}）。\n"
        s["si"],s["qi"]=si,qi
        nq=CGA[si]["qs"][qi]; pct=s["cnt"]/TOTAL*100
        return ToolChunk(content=[TextBlock(text=f"{trans}【下一题】{nq['text']}\n进度{s['cnt']}/{TOTAL}({pct:.0f}%)，请口语化提问。")])

def _init():
    return {"user":"王爷爷","si":0,"qi":0,"cnt":0,"answers":{}}

SYSTEM_PROMPT = """你是"小葛"，GerClaw老年健康AI助手，为78岁王爷爷做CGA综合评估。

身份：社区老年科健康助手，亲切耐心，称呼"王爷爷"，不用医学术语。
评估顺序：ADL日常活动→IADL工具性活动→MMSE认知→GDS抑郁→MNA营养。
规则：
1. 一次只问一个问题，不用复合问。
2. 不念选项，用聊天方式提问，等老人自由回答。
3. 根据回答判断分数后必须调用record_answer记录。
4. 工具返回下一题文本，转换成自然口语问出来。
5. 答非所问先共情回应，再温和重复问题。
6. 每完成一个维度说一句鼓励的话。
开场：热情问候，说明来意（"花几分钟了解平时生活情况"），然后直接问ADL第一题。"""

async def main():
    key=os.environ.get("DASHSCOPE_API_KEY")
    if not key:print("[错误]请设置 DASHSCOPE_API_KEY",file=sys.stderr);sys.exit(1)
    model=DashScopeChatModel(credential=DashScopeCredential(api_key=key),model="qwen-plus",
        parameters=DashScopeChatModel.Parameters(temperature=0.3,max_tokens=512),stream=False)
    agent=Agent(name="小葛",system_prompt=SYSTEM_PROMPT,model=model,
        toolkit=Toolkit(tools=[RecordAnswer(),TaskCreate(),TaskList(),TaskUpdate(),TaskGet()]),
        react_config=ReActConfig(max_iters=10,stop_on_reject=False))
    # 预置Plan任务
    agent.state.tasks_context.tasks.extend([
        Task(id="1",subject="ADL日常活动评估",description="基本自理能力",state="in_progress",metadata={"scale":"ADL"}),
        Task(id="2",subject="IADL工具性活动评估",description="高阶能力",state="pending",blocked_by=["1"],metadata={"scale":"IADL"}),
        Task(id="3",subject="MMSE认知筛查",description="记忆定向计算",state="pending",blocked_by=["2"],metadata={"scale":"MMSE"}),
        Task(id="4",subject="GDS抑郁筛查",description="情绪状态",state="pending",blocked_by=["3"],metadata={"scale":"GDS"}),
        Task(id="5",subject="MNA营养评估",description="食欲体重",state="pending",blocked_by=["4"],metadata={"scale":"MNA"}),
    ])
    agent.state.middle_context["survey"]=_init()
    # 模拟3轮对话
    sim=["开始吧","吃饭没问题自己拿筷子吃","洗脸刷牙都自己来"]
    print("="*60);print(" GerClaw CGA评估对话演示（Plan模式）");print("="*60)
    for i,txt in enumerate(sim):
        print(f"\n[用户·第{i+1}轮] 王爷爷：{txt}");print("-"*40)
        msg=await agent.reply(UserMsg(name="王爷爷",content=txt))
        print(f"[助手·小葛]：{msg.get_text_content() or '(无文本)'}")
        sv=agent.state.middle_context.get("survey",{})
        if sv.get("answers"):
            print(f"\n[状态] 已答{sv['cnt']}题：")
            for qid,a in sv["answers"].items():print(f"  - {qid}: {a['answer']}→{a['score']}分")
    print("\n"+"="*60);print("Plan任务状态：")
    for t in agent.state.tasks_context.tasks:print(f"  [{t.state:>11}] {t.subject}")
    print("="*60);print("提示：完整状态机+中断恢复参见 survey_state_machine.py")

if __name__=="__main__":asyncio.run(main())
