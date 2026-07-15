---
id: ui-upload-review
name: UI 上传审阅
description: 验证上传只进入预览且未经用户确认不会注册的安全工作流
version: 1.0.0
category: general
parameters: {}
tools:
  - search_knowledge
---
# 上传审阅工作流

先核对用户目标，再检索本地证据并标注来源，输出供医生复核的草稿。
禁止确定性诊断；发现高风险症状时提示立即就医。
