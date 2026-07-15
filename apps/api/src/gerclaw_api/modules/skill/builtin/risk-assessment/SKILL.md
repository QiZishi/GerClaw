---
id: risk-assessment
name: 老年风险评估
description: 选择循证筛查工具并以对话方式完成跌倒、营养、认知或情绪风险初筛
version: 1.0.0
category: assessment
parameters:
  assessment_target:
    type: string
    description: 希望筛查的风险主题和已知背景
    maxLength: 2000
tools:
  - search_knowledge
---
# 老年风险评估工作流

1. 明确评估目的和适用人群，再调用 `search_knowledge` 核对量表版本、条目、计分和来源。
2. 一次只提出一至两个问题，使用用户易理解的语言，并允许“不清楚”或“暂不回答”。
3. 只按检索到的有效规则计算风险等级；资料不足时保留为“待专业评估”，不得把筛查结果当成诊断。
4. 输出评估范围、回答摘要、计分依据、风险提示、建议的下一步和可追溯来源。
5. 检出急性意识改变、自伤风险、卒中征象、胸痛或呼吸困难时，立即终止量表并提示急救就医。
