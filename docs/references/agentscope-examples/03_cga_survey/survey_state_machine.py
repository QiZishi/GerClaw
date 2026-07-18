# -*- coding: utf-8 -*-
"""
survey_state_machine.py — GerClaw CGA问卷状态机示例（自定义Tool + 中断恢复）

演示基于Agent状态+自定义Tool的问卷状态机，实现4个核心工具：
  - next_question(answer, score)：记录答案并前进
  - previous_question()：回退上一题
  - jump_to_section(section_name)：跳转到指定维度
  - get_progress()：获取当前进度
  - save_checkpoint()：保存断点
模拟场景：李奶奶(72岁)ADL做到第3题时孙子来访中断，2小时后恢复，回退修改答案，最后跳转到GDS。
支持模拟模式(无需API Key)和 --real 真实LLM模式。

运行：python survey_state_machine.py          # 模拟模式
     python survey_state_machine.py --real   # 需DASHSCOPE_API_KEY
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from typing import Any
from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import TextBlock, ToolChunk, UserMsg
from agentscope.model import DashScopeChatModel
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import ToolBase, Toolkit

# CGA简化量表数据
CGA = [
    {"id":"ADL","name":"日常活动能力","questions":[
        {"id":"ADL_Q1","text":"平时吃饭，您自己能把饭菜送到嘴里吗？","max":10},
        {"id":"ADL_Q2","text":"洗脸、刷牙、梳头您自己能做吗？","max":5},
        {"id":"ADL_Q3","text":"穿衣服、扣扣子您自己能行吗？","max":10},
    ]},
    {"id":"IADL","name":"工具性日常活动","questions":[
        {"id":"IADL_Q1","text":"您自己能拨打电话吗？","max":1},
    ]},
    {"id":"MMSE","name":"认知筛查","questions":[]},
    {"id":"GDS","name":"老年抑郁筛查","questions":[
        {"id":"GDS_Q1","text":"您对生活基本满意吗？","max":1},
        {"id":"GDS_Q2","text":"有没有觉得做什么事都没意思？","max":1},
    ]},
    {"id":"MNA","name":"营养评估","questions":[]},
]
SEC_IDX = {s["id"]:i for i,s in enumerate(CGA)}
TOTAL = sum(len(s["questions"]) for s in CGA)

def init_state(name="李奶奶"):
    return {"user_name":name,"sec":0,"qi":0,"answers":{},"history":[],
            "checkpoint":None,"done":False}

def cur_q(s):
    if s["done"]: return None
    sec = CGA[s["sec"]]
    return sec["questions"][s["qi"]] if s["qi"]<len(sec["questions"]) else None

# ---- Tool: 下一题 ----
class NextQ(ToolBase):
    name="next_question"; is_concurrency_safe=False; is_read_only=False; is_state_injected=True
    description="记录老人回答并前进到下一题。参数answer为回答摘要，score为得分。每次答题后必须调用。"
    input_schema={"type":"object","properties":{"answer":{"type":"string"},"score":{"type":"integer"}},"required":["answer","score"]}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,answer,score,_agent_state=None,**kw):
        s=_agent_state.middle_context.setdefault("survey",init_state())
        c=cur_q(s)
        if not c:return ToolChunk(content=[TextBlock(text="【已完成】")])
        s["answers"][c["id"]]={"answer":answer,"score":score}
        s["history"].append({"sec":s["sec"],"qi":s["qi"],"qid":c["id"]})
        s["qi"]+=1; trans=""
        sec=CGA[s["sec"]]
        if s["qi"]>=len(sec["questions"]):
            s["sec"]+=1;s["qi"]=0
            while s["sec"]<len(CGA) and not CGA[s["sec"]]["questions"]:s["sec"]+=1
            if s["sec"]>=len(CGA):
                s["done"]=True; total=sum(a["score"] for a in s["answers"].values())
                return ToolChunk(content=[TextBlock(text=f"【评估完成】总分{total}分，请反馈结果。")])
            trans=f"【维度切换】{sec['name']}完成→{CGA[s['sec']]['name']}\n"
        nq=cur_q(s); pct=len(s["answers"])/TOTAL*100
        return ToolChunk(content=[TextBlock(text=f"{trans}【当前题目】{nq['text']}\n进度{len(s['answers'])}/{TOTAL}({pct:.0f}%)，请口语化提问。")])

# ---- Tool: 上一题 ----
class PrevQ(ToolBase):
    name="previous_question"; is_concurrency_safe=False; is_read_only=False; is_state_injected=True
    description="老人要修改上一题答案时调用，回退到上一题重新回答。无参数。"
    input_schema={"type":"object","properties":{}}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,_agent_state=None,**kw):
        s=_agent_state.middle_context["survey"]
        if not s["history"]:return ToolChunk(content=[TextBlock(text="【无法回退】这是第一题。")])
        last=s["history"].pop(); s["answers"].pop(last["qid"],None)
        s["sec"],s["qi"],s["done"]=last["sec"],last["qi"],False
        q=cur_q(s); sn=CGA[s["sec"]]["name"]
        return ToolChunk(content=[TextBlock(text=f"【已回退】到{sn}：{q['text']}，请重新提问。")])

# ---- Tool: 跳转维度 ----
class JumpSec(ToolBase):
    name="jump_to_section"; is_concurrency_safe=False; is_read_only=False; is_state_injected=True
    description="跳转到指定维度ADL/IADL/MMSE/GDS/MNA。已答答案保留。"
    input_schema={"type":"object","properties":{"section_name":{"type":"string","enum":["ADL","IADL","MMSE","GDS","MNA"]}},"required":["section_name"]}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,section_name,_agent_state=None,**kw):
        s=_agent_state.middle_context["survey"]
        if section_name not in SEC_IDX:return ToolChunk(content=[TextBlock(text="无效维度")])
        s["sec"]=SEC_IDX[section_name]; s["qi"]=0; s["done"]=False
        while s["sec"]<len(CGA) and not CGA[s["sec"]]["questions"]:s["sec"]+=1
        if s["sec"]>=len(CGA):s["done"]=True;return ToolChunk(content=[TextBlock(text="【完成】")])
        sec=CGA[s["sec"]]; q=sec["questions"][0]
        return ToolChunk(content=[TextBlock(text=f"【跳转】到「{sec['name']}」，当前题：{q['text']}")])

# ---- Tool: 查看进度 ----
class GetProg(ToolBase):
    name="get_progress"; is_concurrency_safe=True; is_read_only=True; is_state_injected=True
    description="查询评估进度。老人问'还有多少题'时调用。无参数。"
    input_schema={"type":"object","properties":{}}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,_agent_state=None,**kw):
        s=_agent_state.middle_context["survey"]; n=len(s["answers"]); pct=n/TOTAL*100
        sn=CGA[s["sec"]]["name"] if s["sec"]<len(CGA) else "已完成"
        done_secs=[sec["name"] for sec in CGA if sec["questions"] and all(q["id"]in s["answers"] for q in sec["questions"])]
        return ToolChunk(content=[TextBlock(text=f"【进度】{n}/{TOTAL}题({pct:.0f}%)，已完成：{','.join(done_secs)or'无'}，当前：{sn}")])

# ---- Tool: 保存断点 ----
class SaveCP(ToolBase):
    name="save_checkpoint"; is_concurrency_safe=False; is_read_only=False; is_state_injected=True
    description="老人要休息时保存断点。无参数。"
    input_schema={"type":"object","properties":{}}
    async def check_permissions(self,ti,c):return PermissionDecision(PermissionBehavior.ALLOW,"","")
    async def __call__(self,_agent_state=None,**kw):
        s=_agent_state.middle_context["survey"]; c=cur_q(s)
        s["checkpoint"]={"sec":s["sec"],"qi":s["qi"],"answers":dict(s["answers"]),"history":list(s["history"]),
                         "qid":c["id"]if c else None,"qtext":c["text"]if c else None}
        return ToolChunk(content=[TextBlock(text=f"【断点已保存】{CGA[s['sec']]['name']}第{s['qi']+1}题，已答{len(s['answers'])}题，请礼貌道别。")])

SYS_PROMPT = """你是"小葛"，GerClaw老年健康助手，为72岁李奶奶做CGA评估。
规则：一次只问一个问题，用简单口语；回答后调next_question；想改答案调previous_question；
问进度调get_progress；要休息调save_checkpoint；要跳维度调jump_to_section。称呼"李奶奶"。"""

def build_agent(model=None):
    if not model:return None
    return Agent(name="小葛",system_prompt=SYS_PROMPT,model=model,
        toolkit=Toolkit(tools=[NextQ(),PrevQ(),JumpSec(),GetProg(),SaveCP()]),
        react_config=ReActConfig(max_iters=15,stop_on_reject=False))

# ---- 模拟演示 ----
async def sim():
    print("="*60); print(" CGA问卷状态机演示（模拟模式：李奶奶中断恢复场景）"); print("="*60)
    tools={"n":NextQ(),"p":PrevQ(),"j":JumpSec(),"g":GetProg(),"s":SaveCP()}
    state=AgentState(); state.middle_context["survey"]=init_state()
    async def call(name,**kw):
        ch=await tools[name](_agent_state=state,**kw)
        return "\n".join(b.text for b in ch.content if isinstance(b,TextBlock))
    def show(lbl):
        s=state.middle_context["survey"]; c=cur_q(s)
        print(f"\n--- [{lbl}] 维度:{CGA[s['sec']]['name']} Q{s['qi']+1} 已答:{len(s['answers'])}/{TOTAL} checkpoint:{'Y'if s['checkpoint']else'N'}")
    # 答3题
    print("\n[场景1] 开始评估，答ADL前3题")
    print("[李奶奶] 开始吧"); print("[小葛]（问吃饭）");await call("n",answer="自己能吃",score=10)
    print("[李奶奶] 洗漱自己来");await call("n",answer="洗漱自理",score=5)
    print("[李奶奶] 穿衣还行，扣扣子得帮忙");await call("n",answer="穿衣需帮扣",score=5)
    show("答3题后")
    # 中断
    print("\n[场景2] 孙子来访，中断"); print("[李奶奶] 我孙子来了，等会儿啊")
    await call("s"); cp=json.dumps(state.middle_context["survey"]["checkpoint"],ensure_ascii=False)
    print(f"[系统] checkpoint保存: qid={json.loads(cp)['qid']}")
    # 恢复
    print("\n[场景3] 2小时后回来，断点恢复")
    c=state.middle_context["survey"]["checkpoint"]
    state.middle_context["survey"]=init_state()
    state.middle_context["survey"].update({"sec":c["sec"],"qi":c["qi"],"answers":c["answers"],"history":c["history"]})
    print("[小葛] 李奶奶回来啦！上次说到穿衣服，接着聊？")
    print("[李奶奶] 等等，上一题我说错了，梳头有时候也得帮忙")
    await call("p"); show("回退修改ADL_Q2")
    print("[李奶奶] 梳头需要帮忙");await call("n",answer="梳头需帮",score=0)
    print(f"[进度查询] {await call('g')}")
    # 跳转GDS
    print("\n[场景4] 李奶奶想先聊心情，跳转到GDS")
    print("[李奶奶] 我最近心里闷得慌，先问问心情吧")
    await call("j",section_name="GDS"); show("跳转GDS")
    print("[李奶奶] 对什么都提不起兴趣");await call("n",answer="情绪低落",score=1)
    show("最终状态"); print("\n"+"="*60); print(" 演示完成：next/prev/jump/progress/save + 中断恢复")

async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--real",action="store_true")
    args=ap.parse_args()
    if args.real:
        key=os.environ.get("DASHSCOPE_API_KEY")
        if not key:print("需要DASHSCOPE_API_KEY",file=sys.stderr);sys.exit(1)
        model=DashScopeChatModel(credential=DashScopeCredential(api_key=key),model="qwen-plus",
            parameters=DashScopeChatModel.Parameters(temperature=0.3,max_tokens=512),stream=False)
        agent=build_agent(model); agent.state.middle_context["survey"]=init_state()
        msg=await agent.reply(UserMsg(name="李奶奶",content="开始吧"));print(msg.get_text_content())
    else:
        await sim()

if __name__=="__main__":asyncio.run(main())
