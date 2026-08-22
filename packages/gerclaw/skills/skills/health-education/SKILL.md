---
name: health-education
description: 依据本地医学证据生成适合患者及照护者阅读的健康宣教材料。
whenToUse: 用户希望理解疾病、检查、康复或日常照护知识时使用。
user-invocable: true
disable-model-invocation: false
metadata:
  displayName: 健康宣教
  version: 1.0.0
  category: education
---

# 健康宣教

1. 先了解受众、阅读习惯、宣教主题和已知背景，不把用户自述升级为诊断。
2. 先用 `library_search` 获取 GerClaw 本地医学证据；只有涉及最新政策或用户明确要求时再用 Web 检索核验。
3. 用“这是什么、为什么重要、可以怎么做、何时找医生、记住一句话”组织内容。
4. 使用短句、常用词并解释必要术语；医学建议必须标注可追溯来源。
5. 不作个体化确诊或处方调整，保留统一 AI 辅助免责声明。
