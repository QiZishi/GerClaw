---
name: followup-questionnaire
description: 根据已知疾病与治疗目标生成简明、可追踪的随访问卷草稿。
whenToUse: 用户需要复诊前准备、随访问卷或阶段性健康回顾时使用。
user-invocable: true
disable-model-invocation: false
metadata:
  displayName: 随访问卷生成
  version: 1.0.0
  category: followup
---

# 随访问卷生成

1. 核对随访对象、时间范围、既往记录和本次目标；把用户自述与专业结论分开标注。
2. 使用 `library_search` 查询 GerClaw 本地医学知识库，禁止编造量表条目、阈值或文献。
3. 问卷优先采用单选、多选和短答案，聚焦症状变化、功能、用药依从、不良反应、居家监测与复诊计划。
4. 将红旗症状单列，并给出立即联系急救或尽快就医的清晰动作。
5. 输出可继续编辑的草稿，附来源标识和统一 AI 辅助免责声明。
