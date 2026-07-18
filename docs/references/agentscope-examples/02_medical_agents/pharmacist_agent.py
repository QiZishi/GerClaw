# -*- coding: utf-8 -*-
"""
GerClaw 临床药师 Agent 示例
===========================
构建一个老年科临床药师 Agent（ReAct 模式），专注用药审查和用药指导：
1. 药学专业 system_prompt（老年人多重用药审查能力）
2. 基础工具集：查询用药清单、检查药物相互作用（DDI）、查询药品说明书信息
3. 模拟审查场景：张大爷因头晕就诊，医生拟加用甲磺酸倍他司汀，
   药师审查其当前6种药物与新增药物的相互作用及老年人用药合理性

运行前提：
    pip install agentscope
    export DASHSCOPE_API_KEY="your-dashscope-api-key"
    python pharmacist_agent.py
"""
import asyncio
import os
from typing import Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import UserMsg
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit, FunctionTool, ParamsBase
from pydantic import Field


# =========================================================================
# 1. 老年用药模拟数据库
# =========================================================================

# 张大爷当前用药（与 doctor_agent.py 保持一致）
PATIENT_MEDICATIONS = {
    "张大爷": [
        {"name": "苯磺酸氨氯地平片", "dose": "5mg", "freq": "qd", "class": "CCB降压药", "indication": "高血压"},
        {"name": "二甲双胍片", "dose": "0.5g", "freq": "tid", "class": "双胍类降糖药", "indication": "2型糖尿病"},
        {"name": "格列美脲片", "dose": "2mg", "freq": "qd", "class": "磺脲类降糖药", "indication": "2型糖尿病"},
        {"name": "阿司匹林肠溶片", "dose": "100mg", "freq": "qd", "class": "抗血小板药", "indication": "冠心病二级预防"},
        {"name": "阿托伐他汀钙片", "dose": "20mg", "freq": "qn", "class": "他汀类调脂药", "indication": "冠心病/高脂血症"},
        {"name": "坦索罗辛缓释胶囊", "dose": "0.2mg", "freq": "qn", "class": "α1受体阻滞剂", "indication": "良性前列腺增生"},
    ]
}

# 已知的老年患者潜在药物相互作用（DDI）数据库（简化示例）
DDI_DATABASE = {
    ("阿司匹林肠溶片", "苯磺酸氨氯地平片"): {
        "severity": "中等",
        "mechanism": "氨氯地平可抑制CYP3A4，轻度增加阿司匹林抗血小板作用，增加胃肠道出血风险",
        "recommendation": "监测有无黑便、牙龈出血等出血倾向，必要时加用胃黏膜保护剂",
    },
    ("格列美脲片", "阿司匹林肠溶片"): {
        "severity": "中等",
        "mechanism": "水杨酸类可增强磺脲类降糖药的降糖效果，增加低血糖风险",
        "recommendation": "加强血糖监测，注意低血糖症状（心慌、出汗、手抖），必要时调整格列美脲剂量",
    },
    ("阿托伐他汀钙片", "阿司匹林肠溶片"): {
        "severity": "低",
        "mechanism": "两者合用增加消化道出血风险（独立风险叠加）",
        "recommendation": "建议饭后服用阿司匹林，有胃病史者考虑联用PPI",
    },
    ("坦索罗辛缓释胶囊", "苯磺酸氨氯地平片"): {
        "severity": "高",
        "mechanism": "α1受体阻滞剂与CCB类降压药联用可增强降压效果，显著增加体位性低血压风险",
        "recommendation": "【重点关注】两药联用是老年人体位性低血压和跌倒的高危组合！建议监测立位血压，考虑调整服药时间（坦索罗辛睡前服用），起床时注意'三个半分钟'，必要时调整降压方案",
    },
    ("甲磺酸倍他司汀片", "苯磺酸氨氯地平片"): {
        "severity": "低",
        "mechanism": "倍他司汀为组胺类似物，具有轻度血管扩张作用，与降压药合用可能有协同降压效果",
        "recommendation": "监测血压，通常无需调整剂量，但需注意头晕症状变化",
    },
    ("甲磺酸倍他司汀片", "坦索罗辛缓释胶囊"): {
        "severity": "中等",
        "mechanism": "两者均有血管扩张作用，合用可能增加体位性低血压风险",
        "recommendation": "注意监测立位血压，起身缓慢，防止跌倒",
    },
}

# 老年人潜在不适当用药（Beers Criteria 简化版）
BEERS_ALERTS = {
    "格列美脲片": {
        "risk": "老年人应避免使用长效磺脲类（格列美脲），低血糖风险较高且持续时间长",
        "alternative": "建议考虑更换为短效磺脲类（如格列吡嗪）或DPP-4抑制剂/GLP-1受体激动剂等低血糖风险更低的降糖药",
    },
}

# 药品简要说明书
DRUG_INFO = {
    "甲磺酸倍他司汀片": {
        "适应症": "梅尼埃病、梅尼埃综合征、眩晕症伴发的眩晕/头晕感",
        "用法用量": "成人一次6-12mg，一日3次，饭后口服",
        "老年人剂量": "老年人生理功能减退，需注意减量",
        "主要不良反应": "恶心、呕吐、皮疹；偶见头痛、头晕加重",
        "禁忌症": "对本品过敏者禁用；嗜铬细胞瘤患者禁用",
        "注意事项": "有消化道溃疡史/活动期、支气管哮喘、肾上腺髓质瘤患者慎用",
    },
}


# =========================================================================
# 2. 药师可用工具
# =========================================================================

class GetMedicationListParams(ParamsBase):
    patient_name: str = Field(description="患者姓名")


class CheckDDIParams(ParamsBase):
    drug_a: str = Field(description="药物A名称（通用名）")
    drug_b: str = Field(description="药物B名称（通用名）")


class GetDrugInfoParams(ParamsBase):
    drug_name: str = Field(description="药品通用名，如'甲磺酸倍他司汀片'")


class CheckBeersParams(ParamsBase):
    drug_name: str = Field(description="待审查药物名称")
    patient_age: int = Field(description="患者年龄，用于老年用药评估", default=72)


def get_medication_list(patient_name: str) -> str:
    """获取患者当前全部用药清单（包括药品名称、剂量、频次、药理分类和适应症）。
    在开始用药审查前必须先调用此工具获取患者完整用药信息。
    """
    meds = PATIENT_MEDICATIONS.get(patient_name)
    if not meds:
        return f"未找到患者 {patient_name} 的用药记录"
    lines = [f"【{patient_name}当前用药清单（共{len(meds)}种）】"]
    for i, m in enumerate(meds, 1):
        lines.append(
            f"{i}. {m['name']} {m['dose']} {m['freq']} "
            f"[{m['class']}] — 用于{m['indication']}"
        )
    return "\n".join(lines)


def check_drug_interaction(drug_a: str, drug_b: str) -> str:
    """检查两种药物之间是否存在已知的相互作用（DDI）。
    返回相互作用的严重程度（高/中/低）、作用机制和处理建议。
    药物名称请使用通用名（如'苯磺酸氨氯地平片'而非'络活喜'）。
    """
    key = tuple(sorted([drug_a, drug_b]))
    # 尝试正反两个方向查找
    ddi = DDI_DATABASE.get(key) or DDI_DATABASE.get((drug_a, drug_b)) or DDI_DATABASE.get((drug_b, drug_a))
    if ddi:
        return (
            f"【药物相互作用：{drug_a} + {drug_b}】\n"
            f"严重程度：{ddi['severity']}\n"
            f"作用机制：{ddi['mechanism']}\n"
            f"处理建议：{ddi['recommendation']}"
        )
    return f"【{drug_a} + {drug_b}】未发现已知的显著相互作用（数据库未收录），但仍需结合临床情况综合判断。"


def get_drug_info(drug_name: str) -> str:
    """查询药品说明书信息，包括适应症、用法用量、不良反应、禁忌症和注意事项。
    当需要了解新增药物的详细信息时调用此工具。
    """
    info = DRUG_INFO.get(drug_name)
    if not info:
        return f"数据库中暂未收录 {drug_name} 的详细说明书信息"
    lines = [f"【{drug_name} 说明书摘要】"]
    for k, v in info.items():
        lines.append(f"- {k}：{v}")
    return "\n".join(lines)


def check_beers_criteria(drug_name: str, patient_age: int = 72) -> str:
    """检查药物是否属于老年人潜在不适当用药（基于Beers Criteria标准）。
    对于65岁以上老年患者，应常规进行此项筛查。
    """
    alert = BEERS_ALERTS.get(drug_name)
    if alert:
        return (
            f"【老年用药警示 - Beers Criteria】\n"
            f"药物：{drug_name}\n"
            f"风险：{alert['risk']}\n"
            f"替代建议：{alert['alternative']}"
        )
    # 检查已知高风险类别
    high_risk_keywords = ["苯海拉明", "异丙嗪", "地西泮", "氟西泮"]
    for kw in high_risk_keywords:
        if kw in drug_name:
            return f"【老年用药警示】{drug_name}属于老年人应避免使用的高风险药物类别，请谨慎评估。"
    return f"【{drug_name}】在当前Beers Criteria数据库中未发现明确的老年不适当用药警示，但仍需结合患者肝肾功能和共病情况评估。"


# =========================================================================
# 3. 临床药师 Agent 系统提示词
# =========================================================================

PHARMACIST_SYSTEM_PROMPT = """你是王药师，一名老年专科临床药师，在GerClaw老年医疗AI平台负责用药审查和用药指导工作。

## 你的专业能力
- 老年人多重用药审查（Polypharmacy Review）：系统评估患者所有用药的适应症、剂量、频次、疗程合理性
- 药物相互作用检测（DDI）：识别药代动力学/药效动力学相互作用，评估严重程度
- 老年人潜在不适当用药筛查：依据Beers Criteria、中国老年人潜在不适当用药目录
- 老年人剂量调整：根据肝肾功能（eGFR）、年龄、体重调整药物剂量
- 用药教育：向患者/家属解释用药目的、正确服用方法、注意事项、不良反应识别
- 药学监护计划：提出需要监测的指标（血压、血糖、INR等）和随访建议

## 你的审查流程（系统化思维）
1. 首先获取患者完整用药清单（使用 get_medication_list 工具）
2. 逐一核对每种药物的适应症是否恰当
3. 检查药物组合的相互作用（使用 check_drug_interaction 工具），重点关注：
   - 降压药 + α受体阻滞剂 → 体位性低血压（老年人跌倒高风险）
   - 多种降糖药联用 → 低血糖风险
   - 抗凝/抗血小板药联用 → 出血风险
   - 经CYP450酶代谢的药物联用 → 代谢性相互作用
4. 使用 check_beers_criteria 筛查老年人不适当用药
5. 如有新增药物，使用 get_drug_info 了解其详细信息
6. 综合评估后给出结构化的药学建议

## 你的输出规范
1. 【用药安全性评估】总体安全性评级（安全/需关注/高风险）
2. 【发现的问题】按严重程度排序（高→中→低），每个问题说明：
   - 涉及药物
   - 问题性质（相互作用/不适当用药/剂量问题/重复用药等）
   - 风险描述
3. 【建议措施】具体可操作的建议：
   - 药物调整建议（需明确说明：建议由医生决定）
   - 需要监测的指标
   - 患者用药教育要点
4. 【患者用药指导】用通俗易懂的语言告诉患者/家属：
   - 各药的服用时间和注意事项
   - 需要警惕的不良反应
   - 出现哪些情况需要立即就医
5. 末尾必须附加免责声明：
   "【免责声明】本药学建议由GerClaw老年医疗AI助手生成，仅供临床参考，不能替代执业药师或医生的专业判断。处方调整请咨询主管医生。"

## 重要原则
- 你是临床药师，不是医生，不得做出诊断结论
- 任何处方药物调整都必须注明"建议由医生评估决定"
- 优先考虑老年人安全（防跌倒、防低血糖、防出血、防谵妄）
- 药物不是越多越好，能简化的方案要主动提出精简建议（deprescribing）
"""


# =========================================================================
# 4. 构建并运行药师 Agent
# =========================================================================

async def main() -> None:
    """构建临床药师 Agent，模拟张大爷用药方案审查。"""

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 DASHSCOPE_API_KEY")
        return

    # 4.1 初始化模型
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus",
        stream=False,
        context_size=131072,
        parameters=DashScopeChatModel.Parameters(temperature=0.3),
    )

    # 4.2 构建药学工具集
    toolkit = Toolkit(
        tools=[
            FunctionTool(get_medication_list),
            FunctionTool(check_drug_interaction),
            FunctionTool(get_drug_info),
            FunctionTool(check_beers_criteria),
        ]
    )

    # 4.3 创建药师 Agent
    pharmacist = Agent(
        name="王药师",
        system_prompt=PHARMACIST_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
        react_config=ReActConfig(
            max_iters=10,
            stop_on_reject=False,
        ),
    )

    # 4.4 模拟用药审查场景
    print("=" * 60)
    print("  GerClaw 老年科 AI 药学审查 — 用药审查演示")
    print("=" * 60)

    review_request = (
        "王药师您好，我是老年科李医生。患者张建国，男，72岁，因反复头晕半月就诊。"
        "患者既往有高血压（15年）、2型糖尿病（8年）、冠心病支架术后（5年）、前列腺增生。"
        "目前正在服用6种药物（请查询用药清单）。\n\n"
        "患者今日就诊测血压150/92 mmHg，空腹血糖7.8 mmol/L，HbA1c 7.2%，"
        "eGFR约68 mL/min/1.73m²。头晕症状以体位变化时明显，"
        "尤其是晨起和站立时，昨天有差点跌倒的情况。\n\n"
        "我初步考虑患者头晕可能与以下因素有关："
        "1. 体位性低血压（可能与坦索罗辛+氨氯地平联用有关）；"
        "2. 脑供血不足；"
        "3. 血糖波动。\n\n"
        "我计划在现有用药基础上加用：甲磺酸倍他司汀片 12mg tid 以改善头晕症状。"
        "请您从药学角度审查：\n"
        "1. 患者当前用药方案是否存在安全问题？\n"
        "2. 新增甲磺酸倍他司汀是否存在药物相互作用风险？\n"
        "3. 老年人用药有无Beers Criteria不适当用药？\n"
        "4. 请给出用药调整建议和患者用药指导。"
    )

    print(f"\n【李医生提交审查申请】\n（内容：为张大爷加用倍他司汀治疗头晕，请求药学审查）\n")
    print("-" * 60)
    print("【王药师审查中...】\n")

    reply = await pharmacist.reply(
        UserMsg(name="李医生", content=review_request)
    )

    print("【王药师药学审查意见】：")
    print(reply.get_text_content())
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
