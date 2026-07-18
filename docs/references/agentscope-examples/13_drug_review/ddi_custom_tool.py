# -*- coding: utf-8 -*-
"""
ddi_custom_tool.py — GerClaw 自定义 DDI 药物交互检查工具演示

继承 AgentScope ToolBase + ParamsBase 实现 DDI 检查工具，
内置简化老年高危 DDI 规则表，含审计日志中间件。
纯工具演示，不需要 LLM / API Key，直接运行即可。

运行: python ddi_custom_tool.py
"""

import asyncio
import json
from datetime import datetime
from itertools import combinations
from typing import Any, AsyncGenerator, Callable

from agentscope.tool import ToolBase, ToolChunk, ToolMiddlewareBase, ParamsBase
from agentscope.message import TextBlock
from agentscope.permission import PermissionContext, PermissionDecision, PermissionBehavior

# ---- 严重级别常量 ----
SEV_CONTRA, SEV_MAJOR, SEV_MODERATE, SEV_MINOR = "contraindicated", "major", "moderate", "minor"
SEV_ICON = {SEV_CONTRA: "🔴禁忌", SEV_MAJOR: "🔴严重", SEV_MODERATE: "🟡中度", SEV_MINOR: "🟢轻度"}

# ---- DDI 规则表: (药A, 药B) → (级别, 机制, 后果, 建议, 老年提示) ----
DDI_RULES: dict[tuple[str, str], dict] = {
    ("华法林", "阿司匹林"): {"severity": SEV_MAJOR,
        "mechanism": "阿司匹林抑制血小板+损伤胃黏膜，与华法林抗凝叠加",
        "consequence": "出血风险显著增加(消化道出血、颅内出血)",
        "recommendation": "避免联用;必须联用则加PPI并密切监测INR",
        "elderly_note": "≥75岁出血风险进一步升高"},
    ("华法林", "胺碘酮"): {"severity": SEV_CONTRA,
        "mechanism": "胺碘酮抑制CYP2C9/CYP3A4，减慢华法林代谢",
        "consequence": "INR急剧升高，严重出血",
        "recommendation": "禁止联用;华法林减量30-50%，3天后复查INR"},
    ("ACEI", "螺内酯"): {"severity": SEV_MODERATE,
        "mechanism": "ACEI与螺内酯均保钾，协同致高钾",
        "consequence": "高钾血症→心律失常甚至心脏骤停",
        "recommendation": "谨慎联用，定期监测血钾",
        "elderly_note": "老年肾功能减退者高钾风险更高"},
    ("坦索罗辛", "氨氯地平"): {"severity": SEV_MODERATE,
        "mechanism": "α1阻滞剂与CCB扩血管作用叠加",
        "consequence": "体位性低血压、头晕、跌倒",
        "recommendation": "小剂量起始，提醒缓慢起身",
        "elderly_note": "老年人跌倒风险极高"},
    ("硝酸甘油", "西地那非"): {"severity": SEV_CONTRA,
        "mechanism": "NO供体协同扩血管", "consequence": "严重低血压、休克、可致死",
        "recommendation": "绝对禁忌!西地那非前后24h禁用硝酸酯类"},
    ("辛伐他汀", "酮康唑"): {"severity": SEV_CONTRA,
        "mechanism": "酮康唑强抑制CYP3A4", "consequence": "横纹肌溶解、急性肾衰",
        "recommendation": "禁止联用;换用瑞舒伐他汀/普伐他汀"},
    ("苯二氮卓类", "阿片类"): {"severity": SEV_MAJOR,
        "mechanism": "中枢抑制叠加", "consequence": "呼吸抑制、过度镇静",
        "recommendation": "避免联用;最低剂量短疗程",
        "elderly_note": "≥65岁两者均为Beers PIM"},
    ("二甲双胍", "NSAIDs"): {"severity": SEV_MODERATE,
        "mechanism": "NSAIDs影响肾灌注+二甲双胍乳酸酸中毒风险",
        "consequence": "肾功能损伤、乳酸酸中毒",
        "recommendation": "肾功能不全者避免联用，监测肾功能"},
    ("喹诺酮", "华法林"): {"severity": SEV_MODERATE,
        "mechanism": "喹诺酮抑制华法林代谢+杀灭肠道菌减少VK",
        "consequence": "抗凝效应增强，INR升高",
        "recommendation": "联用期间加强INR监测"},
    ("地高辛", "维拉帕米"): {"severity": SEV_MAJOR,
        "mechanism": "维拉帕米抑制P-gp，地高辛浓度升高60-80%",
        "consequence": "心动过缓/房室传导阻滞/地高辛中毒",
        "recommendation": "地高辛减量50%，监测血药浓度"},
}

# 药物→类别映射（用于类别级交互检测）
DRUG_CAT = {
    "依那普利":"ACEI","贝那普利":"ACEI","卡托普利":"ACEI","赖诺普利":"ACEI",
    "地西泮":"苯二氮卓类","阿普唑仑":"苯二氮卓类","艾司唑仑":"苯二氮卓类",
    "劳拉西泮":"苯二氮卓类","氯硝西泮":"苯二氮卓类",
    "吗啡":"阿片类","羟考酮":"阿片类","芬太尼":"阿片类","可待因":"阿片类",
    "布洛芬":"NSAIDs","双氯芬酸":"NSAIDs","萘普生":"NSAIDs","吲哚美辛":"NSAIDs",
    "环丙沙星":"喹诺酮","左氧氟沙星":"喹诺酮","莫西沙星":"喹诺酮",
    "氢氯噻嗪":"利尿剂","呋塞米":"利尿剂","托拉塞米":"利尿剂",
    "氨氯地平":"降压药","硝苯地平":"降压药","美托洛尔":"降压药","缬沙坦":"降压药",
}


# ---- ParamsBase 参数定义 ----
class DDICheckParams(ParamsBase):
    drug_list: list[str]  # 待审查药品通用名列表
    patient_age: int | None = None  # 患者年龄(用于老年风险升级)


# ---- 审计日志中间件 ----
class AuditLogMW(ToolMiddlewareBase):
    async def on_tool_call(self, tool, input_kwargs, next_handler):
        t0 = datetime.now()
        drugs = input_kwargs.get("drug_list", [])
        age = input_kwargs.get("patient_age")
        print(f"[审计] 调用{tool.name} | 药物:{drugs} | 年龄:{age or '未知'}")
        try:
            async for chunk in next_handler(**input_kwargs):
                yield chunk
            print(f"[审计] {tool.name}完成, 耗时{(datetime.now()-t0).total_seconds():.3f}s")
        except Exception as e:
            print(f"[审计] {tool.name}异常: {e}")
            raise


# ---- DDITool 自定义工具 ----
class DDITool(ToolBase):
    """药物-药物交互(DDI)检查工具"""
    name = "check_drug_interactions"
    description = "检查药物列表中的DDI交互，返回严重级别/机制/后果/建议，适用于老年处方审查"
    input_schema = DDICheckParams.model_json_schema()
    is_concurrency_safe = True
    is_read_only = True

    def __init__(self):
        super().__init__(middlewares=[AuditLogMW()])

    async def check_permissions(self, tool_input, context):
        return PermissionDecision(behavior=PermissionBehavior.ALLOW, message="DDI检查为只读查询")

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
            sev = rule["severity"]
            upgraded = False
            if age and age >= 75 and sev == SEV_MODERATE:
                sev = SEV_MAJOR; upgraded = True
            results.append({"pair":[a,b],"severity":sev,"mechanism":rule["mechanism"],
                "consequence":rule["consequence"],"recommendation":rule["recommendation"],
                "elderly_note":rule.get("elderly_note",""),"upgraded":upgraded,
                "match_type":rule.get("match_type","精确匹配")})
        order = {SEV_CONTRA:0,SEV_MAJOR:1,SEV_MODERATE:2,SEV_MINOR:3}
        results.sort(key=lambda x: order.get(x["severity"],99))
        return results

    def _format(self, interactions, drugs):
        lines = ["="*56, "📋 DDI药物交互检查报告", "="*56,
                 f"审查药物({len(drugs)}种): {', '.join(drugs)}", ""]
        if not interactions:
            lines.append("✅ 未发现已知交互(仅覆盖内置规则库)")
            return "\n".join(lines)
        lines.append(f"发现{len(interactions)}组交互:")
        for i, r in enumerate(interactions, 1):
            icon = SEV_ICON.get(r["severity"], r["severity"])
            lines.append(f"\n--- {i}. {icon}: {r['pair'][0]}+{r['pair'][1]} ---")
            lines.append(f"  机制: {r['mechanism']}\n  后果: {r['consequence']}")
            lines.append(f"  建议: {r['recommendation']}")
            if r.get("elderly_note"): lines.append(f"  👴老年: {r['elderly_note']}")
            if r["upgraded"]: lines.append(f"  ⚠️ 患者≥75岁，风险升级为严重")
        lines.append("\n⚠️ AI辅助生成，不能替代医生/药师专业判断")
        return "\n".join(lines)

    async def call(self, drug_list, patient_age=None):
        if len(drug_list) < 2:
            return ToolChunk(content=[TextBlock(text="至少需要2种药物")])
        interactions = self._check(drug_list, patient_age)
        return ToolChunk(content=[TextBlock(text=self._format(interactions, drug_list))])


# ---- 主函数：多组测试用例 ----
async def main():
    ddi = DDITool()
    print(f"工具: {ddi.name}\n参数Schema:\n{json.dumps(ddi.input_schema, ensure_ascii=False, indent=2)}\n")

    # 测试1: 华法林+阿司匹林(严重)
    print("="*56, "\n测试1: 华法林+阿司匹林(78岁)", "="*56)
    r = await ddi(drug_list=["华法林","阿司匹林"], patient_age=78)
    print(r.content[0].text)

    # 测试2: 依那普利+螺内酯(中度→老年升级严重)
    print("\n"+"="*56, "\n测试2: 依那普利+螺内酯(82岁)", "="*56)
    r = await ddi(drug_list=["依那普利","螺内酯"], patient_age=82)
    print(r.content[0].text)

    # 测试3: 三联多重用药
    print("\n"+"="*56, "\n测试3: 华法林+阿司匹林+氨氯地平(78岁)", "="*56)
    r = await ddi(drug_list=["华法林","阿司匹林","氨氯地平"], patient_age=78)
    print(r.content[0].text)

    # 测试4: 禁忌级
    print("\n"+"="*56, "\n测试4: 硝酸甘油+西地那非(绝对禁忌)", "="*56)
    r = await ddi(drug_list=["硝酸甘油","西地那非"])
    print(r.content[0].text)

    print("\n✅ 所有测试完成")

if __name__ == "__main__":
    asyncio.run(main())
