---
name: risk-assessment
description: 选择循证筛查工具并以对话方式完成跌倒、营养、认知或情绪风险初筛。
whenToUse: 用户希望进行老年综合风险初筛，且不属于已有确定性 CGA 量表时使用。
user-invocable: true
disable-model-invocation: false
metadata:
  displayName: 老年风险评估
  version: 1.0.0
  category: assessment
---

# 老年风险评估

1. 明确评估目的和适用人群，先用 `library_search` 核对量表版本、条目、计分和来源。
2. 如果属于 PHQ-9、SAS、PSQI、Mini-Cog 或 MMSE，转用 GerClaw 确定性 CGA 界面，不自行计算。
3. 一次提出一至两个易懂问题，并允许“不清楚”或“暂不回答”。
4. 资料不足时标记“待专业评估”，不得把筛查结果当作诊断。
5. 检出急性意识改变、自伤风险、卒中征象、胸痛或呼吸困难时，立即终止筛查并提示急救就医。
