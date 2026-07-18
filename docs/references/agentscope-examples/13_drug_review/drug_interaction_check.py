# -*- coding: utf-8 -*-
"""
drug_interaction_check.py — GerClaw 药师Agent处方审查场景演示

将自定义DDITool + Beers PIM筛查(FunctionTool)集成到AgentScope Agent，
模拟张大爷(78岁)华法林+阿司匹林+氨氯地平多重用药审查场景。
DashScopeChatModel从DASHSCOPE_API_KEY环境变量读取Key。

运行: export DASHSCOPE_API_KEY=sk-xxx && python drug_interaction_check.py
"""

import asyncio, os, sys
from itertools import combinations

from agentscope.agent import Agent
from agentscope.credential import DashScopeCredential
from agentscope.message import TextBlock, UserMsg, Msg
from agentscope.model import DashScopeChatModel
from agentscope.permission import PermissionDecision, PermissionBehavior
from agentscope.tool import FunctionTool, ToolBase, ToolChunk, Toolkit

# ---- DDI 规则数据（简化版老年高危组合）----
SEV_CONTRA, SEV_MAJOR, SEV_MODERATE, SEV_MINOR = "contraindicated","major","moderate","minor"
SEV_ICON = {SEV_CONTRA:"🔴禁忌",SEV_MAJOR:"🔴严重",SEV_MODERATE:"🟡中度",SEV_MINOR:"🟢轻度"}

DDI_RULES = {
    ("华法林","阿司匹林"): {"severity":SEV_MAJOR,"mechanism":"阿司匹林抑制血小板+损伤胃黏膜，与华法林抗凝叠加",
        "consequence":"出血风险显著增加(消化道/颅内出血)","recommendation":"避免联用;必须联用则加PPI并密切监测INR","elderly_note":"≥75岁出血风险进一步升高"},
    ("华法林","胺碘酮"): {"severity":SEV_CONTRA,"mechanism":"胺碘酮抑制CYP2C9/CYP3A4减慢华法林代谢",
        "consequence":"INR急剧升高，严重出血","recommendation":"禁止联用;华法林减量30-50%"},
    ("ACEI","螺内酯"): {"severity":SEV_MODERATE,"mechanism":"ACEI与螺内酯均保钾，协同致高钾",
        "consequence":"高钾血症→心律失常","recommendation":"谨慎联用，定期监测血钾","elderly_note":"老年肾功能减退者高钾风险更高"},
    ("坦索罗辛","氨氯地平"): {"severity":SEV_MODERATE,"mechanism":"α1阻滞剂与CCB扩血管叠加","consequence":"体位性低血压、跌倒",
        "recommendation":"小剂量起始，提醒缓慢起身","elderly_note":"老年人跌倒风险极高"},
    ("苯二氮卓类","阿片类"): {"severity":SEV_MAJOR,"mechanism":"中枢抑制叠加","consequence":"呼吸抑制、过度镇静",
        "recommendation":"避免联用","elderly_note":"≥65岁均为Beers PIM"},
    ("硝酸甘油","西地那非"): {"severity":SEV_CONTRA,"mechanism":"NO供体协同扩血管","consequence":"严重低血压休克",
        "recommendation":"绝对禁忌!24h内不可联用"},
    ("喹诺酮","华法林"): {"severity":SEV_MODERATE,"mechanism":"喹诺酮抑制华法林代谢+减少VK合成",
        "consequence":"INR升高","recommendation":"加强INR监测"},
}
DRUG_CAT = {"依那普利":"ACEI","贝那普利":"ACEI","卡托普利":"ACEI","地西泮":"苯二氮卓类","阿普唑仑":"苯二氮卓类",
    "艾司唑仑":"苯二氮卓类","吗啡":"阿片类","羟考酮":"阿片类","布洛芬":"NSAIDs","双氯芬酸":"NSAIDs",
    "环丙沙星":"喹诺酮","左氧氟沙星":"喹诺酮","氨氯地平":"降压药","美托洛尔":"降压药"}
BEERS_PIM = {  # Beers 2023 PIM简化列表
    "苯二氮卓类": {"drugs":["地西泮","阿普唑仑","艾司唑仑"],"risk":"跌倒/骨折/谵妄/认知损害","recommendation":"避免;换CBT-I或短效非苯二氮卓类"},
    "第一代抗组胺药": {"drugs":["苯海拉明","氯苯那敏"],"risk":"抗胆碱能:认知损害/便秘/尿潴留","recommendation":"换第二代抗组胺药"},
    "长期NSAIDs": {"drugs":["布洛芬","双氯芬酸"],"risk":"胃肠出血/肾损伤/心血管事件","recommendation":"避免长期;优选对乙酰氨基酚≤2g/日"},
}


# ---- DDITool 自定义工具 ----
class DDITool(ToolBase):
    """药物-药物交互(DDI)检查工具"""
    name = "check_drug_interactions"
    description = "检查药物列表中的DDI交互，返回严重级别/机制/后果/建议。输入drug_list(通用名列表)和可选patient_age。"
    is_concurrency_safe = True
    is_read_only = True

    def __init__(self):
        self.input_schema = {
            "type":"object",
            "properties":{
                "drug_list":{"type":"array","items":{"type":"string"},
                    "description":"药品通用名列表，如['华法林','阿司匹林']"},
                "patient_age":{"type":"integer","description":"患者年龄，≥75岁触发老年风险升级"}
            },
            "required":["drug_list"]
        }
        super().__init__()

    async def check_permissions(self, ti, ctx):
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="DDI只读查询")

    def _lookup(self, a, b):
        for k in [(a,b),(b,a)]:
            if k in DDI_RULES: return DDI_RULES[k]
        ca, cb = DRUG_CAT.get(a), DRUG_CAT.get(b)
        if ca and cb:
            for k in [(ca,cb),(cb,ca),(a,cb),(cb,a),(ca,b),(b,ca)]:
                if k in DDI_RULES:
                    r = dict(DDI_RULES[k]); r["match_type"]=f"类别匹配({ca}+{cb})"; return r
        return None

    def _check(self, drugs, age=None):
        results = []
        for a, b in combinations([d.strip() for d in drugs], 2):
            rule = self._lookup(a, b)
            if not rule: continue
            sev = rule["severity"]; upgraded = False
            if age and age >= 75 and sev == SEV_MODERATE:
                sev = SEV_MAJOR; upgraded = True
            results.append({"pair":[a,b],"severity":sev,"mechanism":rule["mechanism"],
                "consequence":rule["consequence"],"recommendation":rule["recommendation"],
                "elderly_note":rule.get("elderly_note",""),"upgraded":upgraded})
        order = {SEV_CONTRA:0,SEV_MAJOR:1,SEV_MODERATE:2,SEV_MINOR:3}
        results.sort(key=lambda x: order.get(x["severity"],99))
        return results

    async def call(self, drug_list, patient_age=None):
        if len(drug_list) < 2:
            return ToolChunk(content=[TextBlock(text="至少需要2种药物进行DDI检查")])
        interactions = self._check(drug_list, patient_age)
        lines = [f"## DDI检查结果 ({len(drug_list)}种药): {', '.join(drug_list)}",""]
        if not interactions:
            lines.append("✅ 未发现已知交互(仅覆盖内置规则库)")
        else:
            lines.append(f"发现**{len(interactions)}**组交互:\n")
            for i, r in enumerate(interactions, 1):
                icon = SEV_ICON.get(r["severity"], "")
                lines.append(f"### {i}. {icon} {r['pair'][0]}+{r['pair'][1]}")
                lines.append(f"- 机制: {r['mechanism']}\n- 后果: {r['consequence']}")
                lines.append(f"- 建议: {r['recommendation']}")
                if r.get("elderly_note"): lines.append(f"- 老年提示: {r['elderly_note']}")
                if r["upgraded"]: lines.append("- ⚠️ ≥75岁风险升级")
                lines.append("")
            lines.append("⚠️ AI辅助结果，需医生/药师确认")
        return ToolChunk(content=[TextBlock(text="\n".join(lines))])


# ---- Beers PIM 检查函数(FunctionTool包装) ----
def beers_pim_check(drug_list: list[str], patient_age: int = 75) -> str:
    """检查老年患者用药是否违反Beers Criteria 2023 PIM标准。
    Args:
        drug_list: 用药通用名列表; patient_age: 年龄,<65岁不筛查
    """
    if patient_age < 65: return f"患者{patient_age}岁,Beers仅适用于≥65岁老年人。"
    findings = []
    for cat, info in BEERS_PIM.items():
        for d in info["drugs"]:
            if any(d in p or p in d for p in drug_list):
                findings.append({"drug":d,"category":cat,"risk":info["risk"],"recommendation":info["recommendation"]}); break
    lines = [f"## Beers 2023 PIM筛查 (年龄:{patient_age}岁)",""]
    if not findings: lines.append("✅ 未发现Beers PIM")
    else:
        lines.append(f"发现**{len(findings)}**项PIM:\n")
        for i,f in enumerate(findings,1):
            lines.append(f"### {i}. 🔴 {f['drug']}({f['category']})")
            lines.append(f"- 风险:{f['risk']}\n- 建议:{f['recommendation']}\n")
    return "\n".join(lines)


# ---- 主函数 ----
async def main():
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: 请先设置 DASHSCOPE_API_KEY 环境变量")
        print("纯工具演示请运行: python ddi_custom_tool.py")
        sys.exit(1)

    # 初始化模型
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus",
        parameters=DashScopeChatModel.Parameters(temperature=0.3),
    )

    # 构建工具集(FunctionTool默认ASK权限，覆写为ALLOW)
    ddi_tool = DDITool()
    beers_tool = FunctionTool(beers_pim_check, name="beers_pim_check",
        description="Beers 2023老年PIM筛查", is_read_only=True)
    async def _allow(*a, **kw): return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="Beers只读查询")
    beers_tool.check_permissions = _allow
    toolkit = Toolkit(tools=[ddi_tool, beers_tool])

    # 创建药师Agent
    system_prompt = """你是GerClaw老年医疗AI平台的临床药师智能体。
对老年患者处方进行安全审查，流程：
1. 调用check_drug_interactions检查DDI交互
2. 调用beers_pim_check进行Beers PIM筛查
3. 综合结果生成结构化报告，用🔴(严重/禁忌)🟡(中度)🟢(提示)分级
4. 每个问题给出:机制+后果+建议+监测指标
5. 最后提示:AI结果需医生/药师确认"""

    pharmacist = Agent(name="临床药师", system_prompt=system_prompt,
                       model=model, toolkit=toolkit)

    # 张大爷场景
    scenario = """请审查以下处方:
患者:张大爷,男,78岁,诊断:房颤+高血压+冠心病,eGFR=55(轻度下降)
用药:①华法林2.5mg QD ②阿司匹林100mg QD ③氨氯地平5mg QD
主诉:近期起床偶有头晕,1周前牙龈出血较多。
请做DDI检查和Beers筛查,给出完整审查报告。"""

    print("="*56); print("GerClaw 老年用药审查系统"); print("="*56)
    print("患者:张大爷,78岁 | 用药:华法林+阿司匹林+氨氯地平")
    print("药师Agent审查中...\n")
    user_msg = UserMsg(name="医生", content=scenario)
    final_msg = None
    async for event in pharmacist.reply_stream(inputs=user_msg):
        if isinstance(event, Msg): final_msg = event
    print("="*56,"\n📋 用药审查报告\n"+"="*56)
    if final_msg:
        for block in final_msg.content:
            if hasattr(block,'text'): print(block.text)
    print("\n"+"="*56,"\n⚠️ AI辅助生成，需医生/药师最终确认\n"+"="*56)

if __name__ == "__main__":
    asyncio.run(main())
