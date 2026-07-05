# AGENTS.md

## Product

面向老年患者和老年科医生的Web端AI双向诊疗平台，以老年专科医生智能体为核心，通过语音优先的适老化交互和专业CGA评估/五大处方能力，为老年人提供便捷、专业、安全的智能医疗健康服务。

## Start Here

**读取顺序**（必读→按需）：
1. **⚠️ 最高权威** `docs/references/gerclaw设计要求.md` — 产品设计的根本依据，所有设计和实现必须符合此文件要求，与其他文档冲突时以此为准
2. `docs/长期规划.md` — 当前进度、已完成、风险点
3. `docs/exec-plans/active/` — 当前活跃执行计划（找编号最小的未完成任务）
4. `ARCHITECTURE.md` — 系统架构和分层约束
5. `docs/PRODUCT_SENSE.md` — 产品直觉和好坏判断
6. `docs/design-docs/core-beliefs.md` — 核心理念、代码品味、技术决策原则
7. 按需读取：`docs/SECURITY.md`、`docs/RELIABILITY.md`、`docs/QUALITY_SCORE.md`、`docs/FRONTEND.md`、`docs/DESIGN.md`、`docs/product-specs/`、`docs/design-docs/`

## Agent Operating Rules

1. 读规范后改代码，未读规范不改
2. 小步提交：每个PR/变更集只做一件事
3. 歧义写入当前exec-plan，和用户确认再继续
4. 行为变更必须同步更新对应文档
5. 数据校验：每个信任边界都要校验（上传/检索/工具/模型/API响应），使用Zod做schema验证
6. 安全和可观测性是产品代码，不是额外工作
7. 收到重复反馈时，转为文档/lint/test/checklist
8. 偏好共享工具包，不重复造轮子；二阶段智能体能力优先使用AgentScope
9. 所有命令实际执行，不空谈"应该可以"
10. 禁止读取gerclaw-main-origin和gerclaw-design-origin目录
11. 医疗安全底线：禁止确定性诊断，所有医疗输出带免责声明，高风险症状提示立即就医
12. 适老化无障碍：患者端老年模式≥18px正文、≥48px按钮、高对比度、图标必有文字标签
13. 配置不可硬编码：所有API Key/模型名/URL通过环境变量配置，.env.example提供模板
14. API Client层抽象：所有外部API调用走services/层，为二阶段迁移后端预留适配

## Expected Agent Loop

```
1. 读取Start Here指定的文档
2. 读取当前exec-plan，理解任务目标和验收标准
3. 按计划编写代码+测试
4. 实际运行测试（npm run build + npm run lint），附完整输出
5. git commit（使用conventional commits）
6. 提交变更汇报给审阅者
7. 审阅者独立审查+测试+判定
8. 若项目涉及前端且审阅通过：
   8a. 启动前端服务（npm run dev），向用户展示当前效果
   8b. 记录后台运行日志（console、网络请求、错误等）
   8c. 用户手动测试并提供反馈
   8d. 根据用户反馈+后台日志修复代码
   8e. 回到步骤3，重新进入开发-审阅对抗循环
   8f. 仅当审阅者通过 AND 用户测试通过，才进入步骤9
9. 若通过（含前端用户测试通过）：审阅者回写长期规划，任务移入completed
10. 若不通过：修复后回到步骤3
```

## Definition of Done

- 产品行为匹配对应product-spec和design-doc
- 访客模式下所有功能可用，无需登录
- 外部API（LLM/ASR/TTS/搜索）可真实调用或有清晰的降级方案
- 前端可成功构建（next build无错误），lint检查通过
- 医疗安全：所有医疗输出带免责声明，循证引用可追溯
- 适老化规范（字体/按钮/对比度）在患者端落实
- 文档反映已实现的行为
- 无铁律违反
- 全量回归测试通过

## 铁律摘要

### 通用铁律（3条，不可删减）

1. **真实执行**：禁止"应该可以"，必须实际运行npm run build/npm run dev并附完整输出
2. **禁止破坏**：改完必须跑全量构建和关键路径测试，不破坏现有逻辑
3. **禁止虚伪成功**：如实报告，失败就是失败，必须附错误信息和复现步骤

### 项目特定铁律

4. **前端必验**：涉及前端的任务，必须启动服务让用户手动测试，记录后台日志，用户反馈+日志修复后重新进入对抗循环，审阅者通过且用户测试通过才能进入下一阶段
5. **医疗安全底线**：禁止给出确定性诊断结论，所有医疗输出必须附带免责声明，高风险症状必须提示立即就医
6. **循证可溯源**：所有医学建议必须标注来源依据，禁止编造医学知识或引用不存在的文献
7. **适老化无障碍**：患者端老年模式下禁止使用<16px字体、<44px按钮、低对比度配色；禁止纯图标无文字标签按钮
8. **配置不可硬编码**：所有API Key、模型名、URL、协议必须通过环境变量配置，禁止在代码中硬编码
9. **技术栈优先级**：设计要求>AgentScope参考>技术选型推荐；二阶段智能体能力优先使用AgentScope
10. **禁止读取origin目录**：严禁阅读gerclaw-main-origin和gerclaw-design-origin目录下的任何文件

详细铁律和检查方式见各文档规范（SECURITY.md/RELIABILITY.md/core-beliefs.md）。
