---
id: medication-reminder
name: 用药提醒
description: 收集医嘱中的药名、剂量与时间，生成适老化提醒草稿并提示复核
version: 1.0.0
category: medication
parameters:
  medication_context:
    type: string
    description: 用户提供或医嘱中已经明确的用药信息
    maxLength: 2000
tools:
  - search_knowledge
---
# 用药提醒工作流

1. 先核对药名、剂量、频次、服用时间、开方机构和是否存在过敏史；缺失信息逐项询问，不猜测。
2. 涉及服法、漏服、不良反应或相互作用时，先调用 `search_knowledge` 获取本地循证资料；没有证据就明确说明需要医生或药师确认。
3. 只依据用户提供的有效医嘱生成提醒草稿，不自行增减剂量、停药、换药或新增药物。
4. 输出使用短句、大标题和早/中/晚分组，并提醒由患者、家属或医护人员复核。
5. 出现严重不适、意识改变、呼吸困难或大出血等红旗情况时，停止普通提醒流程并建议立即急救就医。
