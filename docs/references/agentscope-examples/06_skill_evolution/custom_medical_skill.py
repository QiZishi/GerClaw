# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗AI平台 — 自定义医疗Skill示例：老年跌倒风险评估

本示例演示 AgentScope Skill 系统的完整使用流程：
  1. 使用 tempfile 在临时目录创建符合 GerClaw 医疗规范的 SKILL.md
     （含 YAML Frontmatter：name/description/version/medical 扩展字段）
  2. 创建配套资源文件（Morse跌倒量表速查表 morse_scale.md）
  3. 通过 LocalSkillLoader 加载技能目录
  4. 注册到 Toolkit，获取技能指令片段（可附加到 system prompt）
  5. 使用内置 SkillViewer（工具名 "Skill"）查看技能全文
  6. 定义一个辅助工具（fall_risk_calculator）执行评分计算
  7. 当 DASHSCOPE_API_KEY 存在时，演示 Agent 真实推理流程：
     用户问题 → 模型查看Skill → 调用评估工具 → 生成风险评估报告

运行方式：
    export DASHSCOPE_API_KEY="your-key"   # 可选
    python custom_medical_skill.py
"""
import asyncio
import json
import os
import tempfile
from typing import Any

from pydantic import Field

from agentscope.credential import DashScopeCredential
from agentscope.message import (
    Msg, TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState,
)
from agentscope.model import DashScopeChatModel
from agentscope.skill import LocalSkillLoader
from agentscope.state import AgentState
from agentscope.tool import (
    FunctionTool, ParamsBase, ToolChunk, Toolkit, ToolResponse,
)


# ============================================================
# 步骤1：在临时目录创建医疗Skill（SKILL.md + 资源文件）
# ============================================================

SKILL_MD_CONTENT = """---
name: fall-risk-assessment
description: Use when assessing fall risk for elderly patients aged 60+. Triggers on admission screening, mobility complaints, history of falls, or post-fall evaluation.
display_name: 老年跌倒风险评估
version: "1.0.0"
category: 健康评估
author: GerClaw Medical Team
medical:
  applicable_population:
    age_range: ">=60"
    conditions: ["fall_risk_screening", "mobility_assessment", "post_fall_eval"]
    contraindications: ["pediatric", "acute_trauma_requiring_imaging"]
  risk_level: "medium"
  requires_approval: false
  approval_role: "nurse"
  compliance:
    disclaimer: "本工具为辅助决策工具，不替代医生临床判断。"
    evidence_level: "B"
    guideline_references:
      - "Morse Fall Scale (MFS)"
      - "中国老年人跌倒风险评估专家共识2023"
---

# 老年跌倒风险评估（Morse跌倒量表）

## Overview
对60岁以上老年患者进行标准化跌倒风险筛查，基于Morse跌倒量表(MFS)评分，
给出风险等级和个性化干预建议。

## When to Use
- 60岁以上老年患者入院/入住养老院/社区初诊时
- 患者主诉步态不稳、头晕、乏力
- 过去1年内有跌倒史
- 术后首次下床活动前
- 用药变更后（镇静剂/降压药/利尿剂新增或调整）

**Do NOT use when:**
- 患者为急性创伤（疑似骨折/头部外伤），应先进行急救处理
- 患者年龄<60岁（使用通用跌倒评估工具）
- 患者已发生急性跌倒且疑似重伤，应立即启动急救流程

## Medical Safety Guardrails
- ⚠️ 高风险患者必须立即启动防跌倒预案（床栏、陪护、防滑鞋）
- ⚠️ 评估中发现患者有急性意识障碍/胸痛/呼吸困难，立即建议就医
- ⚠️ 所有评估结果需由护士/医生复核签字

## Core Protocol
1. **前置检查**：确认患者年龄≥60岁，无急性创伤需要急救
2. **MFS评分**：使用 fall_risk_calculator 工具，依次评估6个维度
3. **风险分级**：根据总分判定风险等级（低/中/高）
4. **干预建议**：根据风险等级给出对应预防措施
5. **记录与随访**：将评估结果记录到患者档案，高风险者48h复评

## Morse跌倒量表评分标准
| 维度 | 分值 |
|------|------|
| 跌倒史（过去3个月有跌倒） | 25分 |
| 超过1个医学诊断 | 15分 |
| 行走辅助（轮椅/平车/拐杖/扶物行走） | 15/30分 |
| 静脉输液/肝素锁 | 20分 |
| 步态（虚弱/受损） | 10/20分 |
| 精神状态（高估自身能力/判断力受限） | 15分 |

风险等级：0-24分低风险，25-50分中风险，≥51分高风险

## Escalation Rules
- 高风险且患者独居：立即通知家属，建议24h陪护
- 评估中发现急性神经系统症状（FAST阳性）：立即拨打120
- 患者/家属拒绝评估：记录并通知主管医生
"""

MORSE_SCALE_REF = """# Morse Fall Scale Quick Reference

## Scoring Items
1. History of falling (immediate or within 3 months): 25 points if yes
2. Secondary diagnosis (more than 1 medical diagnosis): 15 points if yes
3. Ambulatory aids:
   - None / Bed rest / Wheelchair: 0 points
   - Crutches / Cane / Walker: 15 points
   - Furniture for support: 30 points
4. IV / Heparin lock: 20 points if present
5. Gait:
   - Normal / Bedridden / Wheelchair: 0 points
   - Weak (stooped, short steps): 10 points
   - Impaired (difficulty standing, needs assistance): 20 points
6. Mental status (overestimates own ability / forgets limitations): 15 points

## Risk Levels
- 0-24: Low risk → standard precautions
- 25-50: Medium risk → fall prevention protocol
- 51+: High risk → high-risk protocol + immediate interventions
"""


def create_medical_skill_dir(base_dir: str) -> str:
    """在指定目录下创建跌倒风险评估Skill目录结构。

    Args:
        base_dir: 基础目录路径

    Returns:
        Skill目录的绝对路径
    """
    skill_dir = os.path.join(base_dir, "fall-risk-assessment")
    os.makedirs(skill_dir, exist_ok=True)

    # 写入 SKILL.md
    with open(
        os.path.join(skill_dir, "SKILL.md"),
        "w", encoding="utf-8",
    ) as f:
        f.write(SKILL_MD_CONTENT)

    # 写入配套资源文件
    with open(
        os.path.join(skill_dir, "morse_scale.md"),
        "w", encoding="utf-8",
    ) as f:
        f.write(MORSE_SCALE_REF)

    return skill_dir


# ============================================================
# 步骤2：定义跌倒风险计算工具
# ============================================================

class FallRiskCalculator(ParamsBase):
    """跌倒风险评估工具参数"""
    age: int = Field(..., ge=60, description="患者年龄，必须≥60")
    fall_history: bool = Field(..., description="过去3个月内是否有跌倒史")
    secondary_diagnosis: bool = Field(..., description="是否有超过1个医学诊断")
    ambulatory_aid: str = Field(
        "none",
        description="行走辅助方式: none(无)/crutches(拐杖)/furniture(扶物)",
    )
    iv_present: bool = Field(False, description="是否有静脉输液/肝素锁")
    gait: str = Field(
        "normal",
        description="步态: normal(正常)/weak(虚弱)/impaired(受损)",
    )
    mental_status_impaired: bool = Field(
        False,
        description="是否高估自身能力/判断力受限",
    )


async def calculate_fall_risk(
    age: int,
    fall_history: bool,
    secondary_diagnosis: bool,
    ambulatory_aid: str = "none",
    iv_present: bool = False,
    gait: str = "normal",
    mental_status_impaired: bool = False,
) -> str:
    """计算Morse跌倒量表评分，给出风险等级和干预建议。

    基于Morse Fall Scale (MFS) 对60岁以上老年患者进行跌倒风险评估。

    Args:
        age: 患者年龄（≥60）
        fall_history: 过去3个月内是否有跌倒史
        secondary_diagnosis: 是否有超过1个医学诊断
        ambulatory_aid: 行走辅助方式
        iv_present: 是否有静脉输液
        gait: 步态状况
        mental_status_impaired: 精神状态是否受损
    """
    score = 0

    # 逐项评分
    if fall_history:
        score += 25
    if secondary_diagnosis:
        score += 15
    if ambulatory_aid == "crutches":
        score += 15
    elif ambulatory_aid == "furniture":
        score += 30
    if iv_present:
        score += 20
    if gait == "weak":
        score += 10
    elif gait == "impaired":
        score += 20
    if mental_status_impaired:
        score += 15

    # 风险分级
    if score <= 24:
        level = "低风险"
        interventions = [
            "1. 保持病区/居家环境整洁、地面干燥",
            "2. 床栏按需使用，呼叫器放置患者可及处",
            "3. 穿着防滑鞋，裤腿不宜过长",
            "4. 入院时及病情变化时评估",
        ]
    elif score <= 50:
        level = "中风险"
        interventions = [
            "1. 启动跌倒预防标准预案：床栏拉起、陪护",
            "2. 床头悬挂'防跌倒'警示标识",
            "3. 协助日常活动（上下床/如厕/行走）",
            "4. 用药后1小时内密切观察",
            "5. 每班评估一次",
        ]
    else:
        level = "高风险"
        interventions = [
            "1. ⚠️ 立即启动高风险防跌倒预案",
            "2. 24小时专人陪护或家属陪护",
            "3. 床栏全程拉起，离床活动需护士协助",
            "4. 使用坐便椅/床上便器，减少走动",
            "5. 通知主管医生，考虑调整高跌倒风险药物",
            "6. 每8小时复评一次，48小时后全面再评估",
            "7. 对患者及家属进行防跌倒宣教",
        ]

    result = (
        f"=== Morse跌倒量表评估结果 ===\n"
        f"患者年龄: {age}岁\n"
        f"MFS总分: {score}分\n"
        f"风险等级: {level}\n\n"
        f"--- 评分明细 ---\n"
        f"跌倒史: {'是(+25)' if fall_history else '否(+0)'}\n"
        f"多诊断: {'是(+15)' if secondary_diagnosis else '否(+0)'}\n"
        f"行走辅助: {ambulatory_aid}\n"
        f"静脉输液: {'是(+20)' if iv_present else '否(+0)'}\n"
        f"步态: {gait}\n"
        f"精神状态: {'受损(+15)' if mental_status_impaired else '正常(+0)'}\n\n"
        f"--- 推荐干预措施 ---\n"
        + "\n".join(interventions)
        + "\n\n---\n"
        + "免责声明：以上为AI辅助评估结果，须由执业护士/医生复核确认。"
    )
    return result


# ============================================================
# 步骤3：主流程演示
# ============================================================

SYSTEM_PROMPT = (
    "你是GerClaw老年医疗AI平台的护士助手，擅长老年跌倒风险评估。"
    "你有一个名为 fall-risk-assessment 的临床技能SOP可用。"
    "当用户需要进行跌倒风险评估时：\n"
    "1. 先使用 Skill 工具查看 fall-risk-assessment 技能的完整SOP\n"
    "2. 按照SOP中的Core Protocol步骤执行评估\n"
    "3. 使用 fall_risk_calculator 工具计算MFS评分\n"
    "4. 根据评分结果给出风险等级和干预建议\n"
    "5. 回答末尾必须附加：'以上为AI辅助评估结果，须由医护人员复核确认。'"
)


async def demo_skill_creation_and_loading() -> Toolkit:
    """演示Skill创建、LocalSkillLoader加载和Toolkit注册。"""
    print("=" * 60)
    print("步骤1：创建医疗Skill目录（tempfile临时目录）")
    print("=" * 60)

    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="gerclaw_skill_")
    skill_dir = create_medical_skill_dir(temp_dir)
    print(f"  Skill目录: {skill_dir}")
    print(f"  SKILL.md 已创建")
    print(f"  morse_scale.md 资源文件已创建")

    # 列出目录内容
    print(f"\n  目录文件列表:")
    for fname in os.listdir(skill_dir):
        fpath = os.path.join(skill_dir, fname)
        size = os.path.getsize(fpath)
        print(f"    - {fname} ({size} bytes)")

    # 使用 LocalSkillLoader 加载
    print("\n" + "=" * 60)
    print("步骤2：通过 LocalSkillLoader 加载Skill")
    print("=" * 60)

    loader = LocalSkillLoader(
        directory=temp_dir,
        scan_subdir=True,
    )
    skills = await loader.list_skills()
    print(f"  成功加载 {len(skills)} 个Skill:")
    for s in skills:
        print(f"    - 名称: {s.name}")
        print(f"      描述: {s.description[:80]}...")
        print(f"      目录: {s.dir}")
        print(f"      更新时间: {s.updated_at}")
        print(f"      正文长度: {len(s.markdown)} 字符")

    # 创建工具并注册到Toolkit
    print("\n" + "=" * 60)
    print("步骤3：注册Skill和工具到Toolkit")
    print("=" * 60)

    calc_tool = FunctionTool(
        func=calculate_fall_risk,
        name="fall_risk_calculator",
        is_read_only=True,
        is_concurrency_safe=True,
    )

    toolkit = Toolkit(
        tools=[calc_tool],
        skills_or_loaders=[loader],
    )

    # 查看工具schema（应包含 fall_risk_calculator 和自动注册的 Skill 查看器）
    schemas = await toolkit.get_tool_schemas()
    print(f"  已注册 {len(schemas)} 个工具:")
    for s in schemas:
        fn = s["function"]
        print(f"    - {fn['name']}: {fn['description'][:60]}...")

    # 获取技能指令（附加到system prompt的片段）
    print("\n" + "=" * 60)
    print("步骤4：获取技能指令片段（skill instructions）")
    print("=" * 60)
    skill_instructions = await toolkit.get_skill_instructions()
    if skill_instructions:
        print(skill_instructions[:500])
        print("  ... (截断)")

    return toolkit, temp_dir


async def demo_skill_viewer(toolkit: Toolkit) -> None:
    """演示通过SkillViewer读取Skill全文。"""
    print("\n" + "=" * 60)
    print("步骤5：通过SkillViewer（Skill工具）读取技能全文")
    print("=" * 60)

    state = AgentState()
    tool_call = ToolCallBlock(
        id="view_skill_001",
        name="Skill",
        input=json.dumps({"skill": "fall-risk-assessment"}),
    )

    print(f"  调用工具: {tool_call.name}")
    print(f"  参数: {tool_call.input}\n")

    skill_content = ""
    async for result in toolkit.call_tool(tool_call, state):
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    skill_content += block.text

    # 显示SKILL.md正文的前800字符
    print("  --- SKILL.md 正文（前800字符）---")
    print(skill_content[:800])
    print("  ... (截断)")


async def demo_direct_fall_assessment(toolkit: Toolkit) -> None:
    """演示直接调用跌倒评估工具（不经过模型推理）。"""
    print("\n" + "=" * 60)
    print("步骤6：直接调用跌倒风险计算工具")
    print("=" * 60)

    state = AgentState()

    # 模拟一位78岁有跌倒史的患者
    tool_call = ToolCallBlock(
        id="calc_001",
        name="fall_risk_calculator",
        input=json.dumps({
            "age": 78,
            "fall_history": True,
            "secondary_diagnosis": True,
            "ambulatory_aid": "crutches",
            "iv_present": False,
            "gait": "weak",
            "mental_status_impaired": False,
        }),
    )

    print(f"  患者信息: 78岁，有跌倒史，多诊断，使用拐杖，步态虚弱")
    print(f"  调用: {tool_call.name}\n")

    async for result in toolkit.call_tool(tool_call, state):
        if isinstance(result, (ToolChunk, ToolResponse)):
            for block in result.content:
                if hasattr(block, "text"):
                    print(block.text)


async def demo_agent_with_model(toolkit: Toolkit) -> None:
    """当DASHSCOPE_API_KEY存在时，演示Agent真实ReAct推理。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("\n" + "=" * 60)
        print("步骤7：Agent推理演示（跳过）")
        print("=" * 60)
        print("  未检测到 DASHSCOPE_API_KEY，跳过模型推理演示。")
        print("  如需完整演示，请设置: export DASHSCOPE_API_KEY='your-key'")
        return

    print("\n" + "=" * 60)
    print("步骤7：Agent真实推理演示（DashScope模型）")
    print("=" * 60)

    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen3.5-plus",
        stream=False,
        context_size=131072,
    )

    # 获取技能指令并拼接到system prompt
    skill_instructions = await toolkit.get_skill_instructions() or ""
    full_system_prompt = SYSTEM_PROMPT + "\n\n" + skill_instructions

    tools = await toolkit.get_tool_schemas()
    msgs = [
        Msg(name="system", role="system",
            content=[TextBlock(text=full_system_prompt)]),
        Msg(name="user", role="user",
            content=[TextBlock(
                text="我奶奶今年82岁，上周在家摔倒过一次，有高血压和糖尿病，"
                     "现在走路需要扶着家具，没有输液，走路有点摇晃，"
                     "有时候会忘记自己行动不便。请帮我评估一下她的跌倒风险。"
            )]),
    ]

    # 多轮ReAct循环（最多3轮）
    for round_num in range(1, 4):
        print(f"\n  [Round {round_num}] 发送消息给模型...")
        response = await model(msgs, tools=tools)
        assistant_content = response.content if response else []

        tool_calls = [b for b in assistant_content if isinstance(b, ToolCallBlock)]
        text_blocks = [b for b in assistant_content if isinstance(b, TextBlock)]

        for tb in text_blocks:
            text = tb.text.strip()
            if text:
                print(f"  模型输出: {text[:300]}")

        if not tool_calls:
            print("\n  === 最终回答 ===")
            for tb in text_blocks:
                print(tb.text)
            break

        # 执行工具调用
        state = AgentState()
        tool_result_blocks = []
        for tc in tool_calls:
            args_preview = tc.input[:200] if tc.input else ""
            print(f"\n  模型调用工具: {tc.name}")
            print(f"  参数: {args_preview}")

            result_text = ""
            async for result in toolkit.call_tool(tc, state):
                if hasattr(result, "content"):
                    for block in result.content:
                        if hasattr(block, "text"):
                            result_text += block.text

            print(f"  工具返回: {result_text[:200]}...")
            tool_result_blocks.append(
                ToolResultBlock(
                    id=tc.id, name=tc.name, output=result_text,
                    state=ToolResultState.SUCCESS,
                )
            )

        # 组装下一轮消息
        msgs.append(Msg(name="nurse_agent", role="assistant",
                        content=assistant_content))
        msgs.append(Msg(name="tool", role="assistant",
                        content=tool_result_blocks))


async def main() -> None:
    """主入口。"""
    print("GerClaw 老年医疗AI平台 — 自定义医疗Skill示例")
    print("AgentScope Skill + LocalSkillLoader + SkillViewer 演示\n")

    toolkit, temp_dir = await demo_skill_creation_and_loading()
    await demo_skill_viewer(toolkit)
    await demo_direct_fall_assessment(toolkit)
    await demo_agent_with_model(toolkit)

    # 清理临时目录
    import shutil
    try:
        shutil.rmtree(temp_dir)
        print(f"\n  临时目录已清理: {temp_dir}")
    except Exception:
        pass

    print("\n示例运行完成。")


if __name__ == "__main__":
    asyncio.run(main())
