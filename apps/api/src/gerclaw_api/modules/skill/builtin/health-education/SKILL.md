---
id: health-education
name: 健康宣教
description: 依据本地医学证据生成适合老年患者及照护者阅读的健康宣教材料
version: 1.0.0
category: education
parameters:
  education_topic:
    type: string
    description: 宣教主题、受众和希望解决的问题
    maxLength: 2000
tools:
  - search_knowledge
  - web_search
---
# 健康宣教工作流

1. 先了解受众、阅读能力、宣教主题和已知健康背景，不把用户自述升级为医生诊断。
2. 调用 `search_knowledge` 获取本地医学证据；涉及最新政策或用户明确要求时，可再使用 `web_search` 核验时效性。
3. 用“这是什么、为什么重要、可以怎么做、何时找医生、记住一句话”的结构组织内容。
4. 使用短句、常用词和清晰分点，解释必要术语；所有医学建议标注可追溯来源。
5. 不提供个体化确诊、处方调整或替代面诊的承诺，并保留统一 AI 辅助免责声明。
