---
id: followup-questionnaire
name: 随访问卷生成
description: 根据已知疾病与治疗目标生成简明、可追踪的老年患者随访问卷草稿
version: 1.0.0
category: followup
parameters:
  followup_goal:
    type: string
    description: 本次随访主题、已知病情或治疗目标
    maxLength: 2000
tools:
  - search_knowledge
---
# 随访问卷生成工作流

1. 核对随访对象、时间范围、既往医生记录和本次随访目标；把患者自述与医生结论分开标注。
2. 调用 `search_knowledge` 查找与主题匹配的本地指南或量表依据，禁止编造量表条目、阈值或文献。
3. 问卷优先使用单选、多选和短答案，每次聚焦症状变化、功能状态、用药依从性、不良反应、居家监测与复诊计划。
4. 将红旗症状单列，并给出立即联系急救或尽快就医的清晰动作。
5. 输出为可由医生继续编辑的草稿，附来源标识和 AI 辅助免责声明。
