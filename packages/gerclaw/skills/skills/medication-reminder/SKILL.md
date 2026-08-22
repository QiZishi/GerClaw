---
name: medication-reminder
description: 根据已经确认的药名、剂量和时间生成清楚的用药提醒草稿。
whenToUse: 用户希望整理既有医嘱、服药时间表或提醒清单时使用。
user-invocable: true
disable-model-invocation: false
metadata:
  displayName: 用药提醒
  version: 1.0.0
  category: medication
---

# 用药提醒

1. 核对药名、剂量、频次、时间、开方来源和过敏史；缺失信息逐项询问，不猜测。
2. 涉及服法、漏服、不良反应或相互作用时，先用 `library_search` 查询本地循证资料；没有证据就说明需医生或药师确认。
3. 只依据有效医嘱生成提醒，不自行增减剂量、停药、换药或新增药物。
4. 使用短句和早/中/晚分组，并提醒用户或医护人员复核。
5. 出现严重不适、意识改变、呼吸困难或明显出血时，停止普通提醒并建议立即就医。
