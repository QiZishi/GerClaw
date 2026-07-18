# -*- coding: utf-8 -*-
"""
GerClaw 老年科医生 Agent 示例
=============================
构建一个老年科医生 Agent（ReAct 模式），具备以下能力：
1. 老年综合评估（CGA）思维
2. 基础工具集：查询患者基本信息、查询检验结果、查询用药清单
3. 模拟初诊对话：72 岁张大爷主诉"最近总是头晕"

运行前提：
    pip install agentscope
    export DASHSCOPE_API_KEY="your-dashscope-api-key"
    python doctor_agent.py
"""
import asyncio
import os
from typing import Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import UserMsg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit, FunctionTool, ParamsBase
from pydantic import Field


# =========================================================================
# 1. 老年医疗模拟数据（张大爷的电子健康档案片段）
# =========================================================================

PATIENT_RECORDS = {
    "张大爷": {
        "基本信息": {
            "姓名": "张建国",
            "年龄": 72,
            "性别": "男",
            "身高_cm": 168,
            "体重_kg": 75,
            "BMI": 26.6,
            "过敏史": "青霉素过敏",
            "吸烟史": "已戒烟10年",
            "饮酒史": "偶尔",
        },
        "既往病史": [
            "原发性高血压（15年，目前服用氨氯地平）",
            "2型糖尿病（8年，二甲双胍+格列美脲）",
            "冠心病（5年，支架术后，阿司匹林+阿托伐他汀）",
            "良性前列腺增生",
        ],
        "最近检验结果": {
            "血压": "150/92 mmHg（今日自测）",
            "空腹血糖": "7.8 mmol/L",
            "糖化血红蛋白_HbA1c": "7.2%",
            "总胆固醇": "5.1 mmol/L",
            "低密度脂蛋白_LDL": "3.2 mmol/L",
            "肌酐": "98 μmol/L（eGFR 约 68 mL/min/1.73m²）",
            "血红蛋白": "132 g/L",
        },
        "当前用药清单": [
            "苯磺酸氨氯地平片 5mg qd（降压）",
            "二甲双胍片 0.5g tid（降糖）",
            "格列美脲片 2mg qd（降糖）",
            "阿司匹林肠溶片 100mg qd（抗血小板）",
            "阿托伐他汀钙片 20mg qn（调脂）",
            "坦索罗辛缓释胶囊 0.2mg qn（前列腺）",
        ],
        "最近跌倒史": "3个月前在家中浴室滑倒1次，无骨折",
    }
}


# =========================================================================
# 2. 医生可用工具（模拟 EHR 系统查询接口）
# =========================================================================

class QueryPatientInfoParams(ParamsBase):
    """查询患者基本信息参数"""
    patient_name: str = Field(description="患者姓名，例如：张大爷")


class QueryLabResultParams(ParamsBase):
    """查询检验结果参数"""
    patient_name: str = Field(description="患者姓名")
    item: Optional[str] = Field(
        default=None,
        description="具体检验项目名，如'血压'、'血糖'。不传则返回全部检验结果",
    )


class QueryMedicationParams(ParamsBase):
    """查询用药清单参数"""
    patient_name: str = Field(description="患者姓名")


def query_patient_info(patient_name: str) -> str:
    """查询患者的基本信息（年龄、性别、BMI、既往病史、过敏史等）。
    在问诊开始或需要了解患者背景时调用此工具。
    """
    record = PATIENT_RECORDS.get(patient_name)
    if not record:
        return f"未找到患者 {patient_name} 的档案"
    info = record["基本信息"]
    history = "；".join(record["既往病史"])
    return (
        f"【{patient_name}基本信息】\n"
        f"姓名：{info['姓名']}，{info['年龄']}岁，{info['性别']}\n"
        f"身高/体重：{info['身高_cm']}cm/{info['体重_kg']}kg，BMI {info['BMI']}\n"
        f"过敏史：{info['过敏史']}\n"
        f"既往病史：{history}\n"
        f"跌倒史：{record['最近跌倒史']}"
    )


def query_lab_result(patient_name: str, item: Optional[str] = None) -> str:
    """查询患者最近的检验/检查结果，包括血压、血糖、血脂、肝肾功能等。
    当需要评估当前疾病控制情况或排查头晕的器质性病因时调用。
    """
    record = PATIENT_RECORDS.get(patient_name)
    if not record:
        return f"未找到患者 {patient_name} 的检验数据"
    labs = record["最近检验结果"]
    if item:
        if item in labs:
            return f"【{patient_name} - {item}】{labs[item]}"
        return f"未找到 {item} 的检验结果，可用项目：{list(labs.keys())}"
    lines = [f"- {k}：{v}" for k, v in labs.items()]
    return f"【{patient_name}最近检验结果】\n" + "\n".join(lines)


def query_medication_list(patient_name: str) -> str:
    """查询患者当前正在使用的全部药物清单（含剂量和频次）。
    当需要排查药物相关不良反应（如体位性低血压导致头晕）时调用。
    """
    record = PATIENT_RECORDS.get(patient_name)
    if not record:
        return f"未找到患者 {patient_name} 的用药记录"
    meds = record["当前用药清单"]
    lines = [f"- {m}" for m in meds]
    return f"【{patient_name}当前用药清单（共{len(meds)}种）】\n" + "\n".join(lines)


# =========================================================================
# 3. 老年科医生 Agent 系统提示词
# =========================================================================

DOCTOR_SYSTEM_PROMPT = """你是李医生，一名资深老年科副主任医师，在GerClaw老年医疗AI平台为老年患者提供初诊咨询服务。

## 你的专业能力
- 老年综合评估（CGA）：从躯体功能、认知、情绪、营养、社会支持多个维度评估老年人健康
- 老年综合征管理：跌倒、痴呆、尿失禁、谵妄、晕厥、头晕、睡眠障碍、慢性疼痛
- 慢病共病管理：高血压、糖尿病、冠心病、脑卒中、慢性肾病等老年常见慢病的综合管理
- 合理用药：老年人多重用药（polypharmacy）风险识别、药物不良反应排查
- 鉴别诊断思维：基于患者症状，先排除危险病因（心脑血管急症），再考虑常见老年病因

## 沟通原则（面向老年患者）
1. 使用温和、耐心的语气，语速宜慢，语言通俗易懂
2. 避免过多专业术语，必要时用生活化比喻解释
3. 主动追问关键信息：
   - 症状特点：持续时间、频率、诱因、缓解因素
   - 伴随症状：有无恶心呕吐、耳鸣、肢体无力、胸闷胸痛
   - 用药依从性：是否按时服药、最近有无加药/减药/换药
   - 生活环境：最近有无跌倒、饮食睡眠变化
4. 每次回复结尾给出明确的下一步建议

## 急症识别红线（必须立即处理）
如果患者出现以下任何情况，立即建议拨打120或前往急诊：
- 胸痛、胸闷、呼吸困难
- 突发剧烈头痛、意识障碍、言语不清、肢体麻木/无力
- 大量出血、严重外伤
- 晕厥伴抽搐或持续意识不清

## 你的可用工具
- query_patient_info: 查询患者基本信息和既往病史
- query_lab_result: 查询检验结果
- query_medication_list: 查询当前用药清单

请合理使用这些工具获取信息，避免重复询问患者已经在档案中的信息。
对于检验指标，请注意结合老年人的参考范围评估（如老年人血压控制目标可适当放宽）。

## 输出规范
1. 先表达关心和共情
2. 结合工具查询到的信息给出初步分析（鉴别诊断思路）
3. 给出建议（需要完善的检查、生活方式调整、用药注意事项）
4. 末尾必须附加以下免责声明：
   "【免责声明】本建议由GerClaw老年医疗AI助手生成，仅供参考，不能替代医生的专业诊断和治疗建议。如有紧急情况请立即拨打120。"
"""


# =========================================================================
# 4. 构建并运行 Agent
# =========================================================================

async def main() -> None:
    """构建老年科医生 Agent，模拟张大爷初诊对话。"""

    # 4.1 初始化 DashScope 模型
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 DASHSCOPE_API_KEY")
        return

    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus",  # 也可使用 "qwen-max" 获取更强推理能力
        stream=False,
        context_size=131072,
        parameters=DashScopeChatModel.Parameters(
            temperature=0.4,  # 医疗场景使用较低温度，减少幻觉
        ),
    )

    # 4.2 构建工具集
    toolkit = Toolkit(
        tools=[
            FunctionTool(query_patient_info),
            FunctionTool(query_lab_result),
            FunctionTool(query_medication_list),
        ]
    )

    # 4.3 创建老年科医生 Agent（ReAct 模式）
    doctor = Agent(
        name="李医生",
        system_prompt=DOCTOR_SYSTEM_PROMPT,
        model=model,
        toolkit=toolkit,
        react_config=ReActConfig(
            max_iters=8,           # 医疗场景限制迭代次数，避免无限工具调用
            stop_on_reject=False,  # 工具被拒绝时继续推理
        ),
    )

    # 4.4 模拟初诊对话
    print("=" * 60)
    print("  GerClaw 老年科 AI 门诊 — 初诊对话演示")
    print("=" * 60)

    # 患者主诉
    patient_msg = (
        "李医生您好，我是张建国，今年72岁。最近半个月总是觉得头晕，"
        "尤其是早上起床的时候最明显，有时候站起来也会眼前发黑一下。"
        "昨天在家差点摔倒，幸亏扶住了桌子。这是怎么回事啊？"
        "需要做什么检查吗？"
    )
    print(f"\n【张大爷】：{patient_msg}\n")
    print("-" * 60)
    print("【李医生思考中...】\n")

    # Agent 推理并回复
    reply = await doctor.reply(
        UserMsg(name="张大爷", content=patient_msg)
    )

    print("【李医生】：")
    print(reply.get_text_content())
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
