# -*- coding: utf-8 -*-
"""
GerClaw 多学科会诊（MDT）多 Agent 协作示例
============================================
演示老年科医生 + 药师 + 护理师三角色 Agent 协同工作，
模拟多学科会诊（Multi-Disciplinary Team, MDT）场景。

【协作模式说明】
AgentScope 官方提供两种多 Agent 协作方式：
1. Agent Service Team（完整版）：需部署 Redis + MessageBus + FastAPI 服务，
   通过 TeamCreate/AgentCreate/TeamSay/TeamDelete 工具进行分布式协作；
2. 库模式顺序编排（本示例采用）：同一进程内创建多个 Agent 实例，
   通过 observe() 注入上下文、reply() 顺序调用实现消息流转，
   适合原型开发、离线场景、无需持久化的应用。

本示例模拟场景：
72岁张大爷因"反复头晕伴跌倒风险"就诊，协调员（Care Coordinator）组织：
  - 老年科李医生：诊断评估
  - 王药师：用药审查
  - 陈护理师：护理评估和护理计划
三方各自给出专业意见后，协调员汇总为MDT会诊结论。

运行前提：
    pip install agentscope
    export DASHSCOPE_API_KEY="your-dashscope-api-key"
    python care_coordinator_team.py
"""
import asyncio
import os
from typing import Optional

from agentscope.agent import Agent, ReActConfig
from agentscope.credential import DashScopeCredential
from agentscope.message import UserMsg, AssistantMsg, TextBlock
from agentscope.model import DashScopeChatModel
from agentscope.tool import Toolkit, FunctionTool, ParamsBase
from pydantic import Field


# =========================================================================
# 1. 共享模拟数据（张大爷健康档案）
# =========================================================================

PATIENT_RECORD = {
    "基本信息": {
        "姓名": "张建国", "年龄": 72, "性别": "男",
        "身高_cm": 168, "体重_kg": 75, "BMI": 26.6,
        "过敏史": "青霉素过敏",
        "居住情况": "与老伴同住，子女在外地",
    },
    "既往病史": [
        "原发性高血压（15年）", "2型糖尿病（8年）",
        "冠心病支架术后（5年）", "良性前列腺增生",
    ],
    "最近检验": {
        "血压": "150/92 mmHg", "空腹血糖": "7.8 mmol/L",
        "HbA1c": "7.2%", "eGFR": "68 mL/min/1.73m²",
    },
    "当前用药": [
        "氨氯地平 5mg qd", "二甲双胍 0.5g tid", "格列美脲 2mg qd",
        "阿司匹林 100mg qd", "阿托伐他汀 20mg qn", "坦索罗辛 0.2mg qn",
    ],
    "跌倒史": "3月前浴室滑倒1次；昨日差点再次跌倒",
    "ADL评分": "85分（轻度功能下降）",
    "Morse跌倒风险评分": "55分（高风险）",
    "MNA-SF营养筛查": "11分（潜在营养不良风险）",
}


# =========================================================================
# 2. 共享工具集（所有专科 Agent 均可使用）
# =========================================================================

class QueryRecordParams(ParamsBase):
    section: Optional[str] = Field(
        default=None,
        description="档案节名：'基本信息'/'既往病史'/'最近检验'/'当前用药'等，不传返回摘要",
    )


def query_patient_record(section: Optional[str] = None) -> str:
    """查询患者张建国的电子健康档案。可以查询特定节，也可以获取摘要。
    在需要了解患者背景信息时调用。
    """
    if section:
        data = PATIENT_RECORD.get(section)
        if data is None:
            return f"未找到'{section}'节，可用：{list(PATIENT_RECORD.keys())}"
        if isinstance(data, list):
            return f"【{section}】\n" + "\n".join(f"- {x}" for x in data)
        if isinstance(data, dict):
            return f"【{section}】\n" + "\n".join(f"- {k}：{v}" for k, v in data.items())
        return f"【{section}】{data}"
    # 返回摘要
    return (
        "【张建国档案摘要】72岁男性，高血压/糖尿病/冠心病/前列腺增生；"
        "目前用6种药物；血压150/92，HbA1c 7.2%；"
        "Morse跌倒评分55分（高风险），有近期跌倒史。"
    )


# =========================================================================
# 3. 各角色 system_prompt
# =========================================================================

COORDINATOR_PROMPT = """你是赵护士，GerClaw老年医疗AI平台的护理协调员（Care Coordinator），负责组织多学科会诊（MDT）。

## 你的职责
1. 接收患者的就诊需求，整理病例摘要
2. 将会诊任务分发给相应专科Agent（医生/药师/护理师）
3. 收集各专科意见
4. 综合各方意见，形成结构化的MDT会诊结论
5. 确保会诊结论包含：诊断意见、用药建议、护理计划、随访安排、安全警示

## 输出要求
- 会诊结论采用结构化格式，语言通俗易懂，适合老年患者及家属理解
- 标注各意见来源（"老年科医生意见"/"药师意见"/"护理师意见"）
- 对有冲突的意见进行标注并给出综合判断
- 必须包含明确的下一步行动项（Action Items）
- 末尾附加免责声明：
  "【免责声明】本会诊意见由GerClaw老年医疗AI多学科团队生成，仅供参考，实际诊疗方案需由主管医生确认。紧急情况请拨打120。"

## 注意事项
- 你不直接给出诊断或处方，你的角色是协调和汇总
- 确保每个专科Agent都收到了足够的患者信息
- 关注老年患者的安全问题（跌倒、低血糖、药物不良反应等）
"""

DOCTOR_PROMPT = """你是李医生，老年科副主任医师，参加本次多学科会诊。

## 你的专业领域
- 老年综合评估（CGA）、老年综合征管理、慢病共病管理、鉴别诊断

## 会诊任务
根据患者病情，给出：
1. 初步诊断/问题列表（按优先级排序）
2. 鉴别诊断（需排除的危险病因）
3. 建议完善的检查
4. 治疗原则建议（不写具体处方）
5. 需要其他专科（药师/护理师）关注的问题

## 可用工具
- query_patient_record: 查询患者电子健康档案

## 重要原则
- 先排除危险病因（脑血管意外、心律失常等），再考虑常见老年问题
- 头晕+体位性+跌倒史的老年患者，重点排查体位性低血压
- 不给出具体药物处方（处方由药师审查后由医生决定）
- 语言专业但简洁，突出关键判断
"""

PHARMACIST_PROMPT = """你是王药师，老年专科临床药师，参加本次多学科会诊。

## 你的专业领域
- 多重用药审查（Polypharmacy）、药物相互作用（DDI）、老年人不适当用药（Beers Criteria）、剂量调整

## 会诊任务
根据患者当前用药和医生诊断思路，给出：
1. 当前用药方案的安全性评估
2. 发现的药物相关问题（相互作用/不适当用药/剂量问题）
3. 重点关注：坦索罗辛+氨氯地平的体位性低血压风险
4. 格列美脲在老年人中的低血糖风险（Beers Criteria）
5. 用药调整建议（需注明"建议由医生决定"）
6. 需要监测的指标（血压、血糖等）

## 可用工具
- query_patient_record: 查询患者电子健康档案和用药清单

## 重要原则
- 你不做诊断，专注于药物安全
- 老年患者优先考虑安全（防跌倒、防低血糖、防出血）
- 能精简的药物主动提出deprescribing建议
"""

NURSE_PROMPT = """你是陈护理师，老年专科护理师，参加本次多学科会诊。

## 你的专业领域
- 老年护理评估（跌倒、营养、认知、压疮、ADL/IADL）、护理计划制定、健康教育、居家照护指导

## 会诊任务
根据患者情况，给出：
1. 护理评估结果（跌倒风险、营养风险、自理能力）
2. 护理诊断（按优先级排序）
3. 护理计划和具体措施
4. 居家环境改造建议（防跌倒）
5. 患者/家属健康教育要点
6. 随访建议

## 可用工具
- query_patient_record: 查询患者电子健康档案

## 重要原则
- 老年患者安全第一（防跌倒、防误服、防走失）
- 护理措施要具体可操作（不仅说"注意安全"，要说"起床三个半分钟：躺半分钟、坐半分钟、站半分钟"）
- 考虑到患者老伴照护能力和子女不在身边的情况
- 语言通俗易懂，适合老年患者和家属理解
"""


# =========================================================================
# 4. 多 Agent 协作编排器
# =========================================================================

class MDTCoordinator:
    """多学科会诊编排器：创建各专科Agent，顺序流转消息，最终汇总。

    这是 AgentScope 库模式下的简化 Team 协作实现：
    - 不依赖 Redis/MessageBus/FastAPI 服务
    - 每个 Agent 独立实例，拥有自己的 system_prompt 和 toolkit
    - 通过 observe() 将其他 Agent 的输出注入上下文
    - 通过 await agent.reply() 触发推理
    - 协调员最终汇总所有意见
    """

    def __init__(self, model: DashScopeChatModel):
        self.model = model
        self.shared_toolkit = Toolkit(tools=[FunctionTool(query_patient_record)])

        # 创建各专科 Agent
        self.coordinator = Agent(
            name="赵协调员",
            system_prompt=COORDINATOR_PROMPT,
            model=model,
            toolkit=Toolkit(tools=[FunctionTool(query_patient_record)]),
            react_config=ReActConfig(max_iters=6, stop_on_reject=False),
        )
        self.doctor = Agent(
            name="李医生",
            system_prompt=DOCTOR_PROMPT,
            model=model,
            toolkit=self.shared_toolkit,
            react_config=ReActConfig(max_iters=6, stop_on_reject=False),
        )
        self.pharmacist = Agent(
            name="王药师",
            system_prompt=PHARMACIST_PROMPT,
            model=model,
            toolkit=self.shared_toolkit,
            react_config=ReActConfig(max_iters=6, stop_on_reject=False),
        )
        self.nurse = Agent(
            name="陈护理师",
            system_prompt=NURSE_PROMPT,
            model=model,
            toolkit=self.shared_toolkit,
            react_config=ReActConfig(max_iters=6, stop_on_reject=False),
        )

    async def run_consultation(self, patient_chief_complaint: str) -> str:
        """执行一次完整的 MDT 会诊流程。

        流程：
        1. 协调员整理病例，分发给医生
        2. 医生给出诊断意见
        3. 药师审查用药（参考医生意见）
        4. 护理师制定护理计划（参考医生+药师意见）
        5. 协调员汇总三方意见，输出MDT结论
        """

        separator = "=" * 60

        # --- 阶段1：协调员整理病例，发送给医生 ---
        print(f"\n{separator}")
        print("  【阶段1】协调员分发会诊任务 → 老年科医生")
        print(separator)

        doctor_task = (
            f"【MDT会诊请求】\n"
            f"患者张建国，72岁男性，因以下主诉就诊：\n"
            f"「{patient_chief_complaint}」\n\n"
            f"请您先查询患者档案了解完整病情，然后给出您的专科意见。"
            f"特别关注：头晕的病因鉴别、跌倒风险评估、建议的检查项目。"
        )
        doctor_reply = await self.doctor.reply(
            UserMsg(name="赵协调员", content=doctor_task)
        )
        doctor_opinion = doctor_reply.get_text_content()
        print(f"\n[李医生意见]:\n{doctor_opinion}\n")

        # --- 阶段2：药师审查（参考医生意见）---
        print(f"{separator}")
        print("  【阶段2】医生意见 → 药师审查用药方案")
        print(separator)

        pharmacist_task = (
            f"【MDT会诊请求 - 用药审查】\n"
            f"患者张建国，72岁男性。因「{patient_chief_complaint}」就诊。\n\n"
            f"李医生的初步意见：\n{'-'*40}\n{doctor_opinion}\n{'-'*40}\n\n"
            f"请查询患者完整用药清单，从药学角度进行审查，"
            f"重点关注：体位性低血压相关药物组合、老年人不适当用药、药物相互作用。"
        )
        pharmacist_reply = await self.pharmacist.reply(
            UserMsg(name="赵协调员", content=pharmacist_task)
        )
        pharmacist_opinion = pharmacist_reply.get_text_content()
        print(f"\n[王药师意见]:\n{pharmacist_opinion}\n")

        # --- 阶段3：护理师评估（参考医生+药师意见）---
        print(f"{separator}")
        print("  【阶段3】医生+药师意见 → 护理师护理评估")
        print(separator)

        nurse_task = (
            f"【MDT会诊请求 - 护理评估】\n"
            f"患者张建国，72岁男性，与老伴同住。因「{patient_chief_complaint}」就诊。\n\n"
            f"李医生意见：\n{'-'*40}\n{doctor_opinion}\n{'-'*40}\n\n"
            f"王药师意见：\n{'-'*40}\n{pharmacist_opinion}\n{'-'*40}\n\n"
            f"请查询患者档案中的护理评估数据（Morse跌倒评分、ADL、MNA等），"
            f"给出护理诊断、护理计划和居家照护指导。"
        )
        nurse_reply = await self.nurse.reply(
            UserMsg(name="赵协调员", content=nurse_task)
        )
        nurse_opinion = nurse_reply.get_text_content()
        print(f"\n[陈护理师意见]:\n{nurse_opinion}\n")

        # --- 阶段4：协调员汇总 ---
        print(f"{separator}")
        print("  【阶段4】协调员汇总三方意见 → MDT会诊结论")
        print(separator)

        summary_task = (
            f"请汇总以下三位专科人员的意见，形成一份完整的MDT会诊结论报告。\n\n"
            f"【患者主诉】{patient_chief_complaint}\n\n"
            f"【老年科李医生意见】\n{'-'*40}\n{doctor_opinion}\n{'-'*40}\n\n"
            f"【临床王药师意见】\n{'-'*40}\n{pharmacist_opinion}\n{'-'*40}\n\n"
            f"【老年专科陈护理师意见】\n{'-'*40}\n{nurse_opinion}\n{'-'*40}\n\n"
            f"请输出结构化的会诊结论，包含：主要问题清单、诊断思路、用药建议、护理计划、"
            f"患者注意事项、随访安排，并附加免责声明。"
        )
        summary_reply = await self.coordinator.reply(
            UserMsg(name="系统", content=summary_task)
        )
        final_conclusion = summary_reply.get_text_content()
        print(f"\n[MDT会诊最终结论]:\n{final_conclusion}\n")
        print(separator)
        print("  MDT会诊流程完成")
        print(separator)

        return final_conclusion


# =========================================================================
# 5. 主入口
# =========================================================================

async def main() -> None:
    """构建 MDT 协作团队，模拟张大爷多学科会诊。"""

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 DASHSCOPE_API_KEY")
        print("  export DASHSCOPE_API_KEY=your-key")
        return

    print("=" * 60)
    print("  GerClaw 老年医疗AI平台")
    print("  多学科会诊（MDT）协作演示")
    print("  模式：库模式顺序编排（简化版Team）")
    print("=" * 60)

    # 初始化模型（所有 Agent 共享同一个模型实例，也可以为不同角色使用不同模型）
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen-plus",
        stream=False,
        context_size=131072,
        parameters=DashScopeChatModel.Parameters(temperature=0.4),
    )

    # 创建 MDT 编排器
    mdt = MDTCoordinator(model=model)

    # 患者就诊信息
    chief_complaint = (
        "反复头晕半个月，加重3天。头晕在晨起和站立时明显，伴眼前发黑，"
        "昨日在家中差点摔倒（扶住了桌子）。既往有高血压15年、糖尿病8年、"
        "冠心病支架术后5年，目前每天吃6种药。"
        "担心再次摔倒，希望得到全面的诊疗意见。"
    )

    print(f"\n【患者张大爷主诉】\n{chief_complaint}\n")

    # 执行会诊
    await mdt.run_consultation(chief_complaint)


if __name__ == "__main__":
    asyncio.run(main())
