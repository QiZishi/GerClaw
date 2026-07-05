# PLANS.md

> 计划总览 | 当前开发路线图

---

## 两阶段 Mock 策略声明

> ⚠️ **关键约束**（依据 `gerclaw设计要求.md` §15.2、`ARCHITECTURE.md` ADR-006）：
> - **阶段一（0001）**：UI 壳子构建，**允许使用 mock 数据**（集中于 `src/data/mock/`），不调用真实 API
> - **阶段二（0002 起）**：功能实现，**严禁使用 mock 数据**，所有外部 API 调用必须真实调用模型服务和工具服务，用真实数据验证。**违者视为未完成。**

---

## 当前里程碑

**当前阶段**：规范构建完成，文档对齐完成，即将进入阶段一 UI 壳子搭建

所有 PRD、product-specs（16 个功能模块）、design-docs（16 个技术设计）、横切规范（SECURITY/RELIABILITY/FRONTEND/DESIGN/PRODUCT_SENSE/core-beliefs）、架构文档（ARCHITECTURE/QUALITY_SCORE）均已完成并与 `gerclaw设计要求.md` 对齐。

## 执行计划索引

### 活跃计划 (active/)

| 编号 | 任务名 | 创建时间 | 状态 | 优先级 | 阶段 |
|------|--------|---------|------|--------|------|
| 0001 | 完整前端UI壳子搭建 | 2026-07-05 | 待开始 | P0 | 一（允许 mock） |

### 已完成计划 (completed/)

| 编号 | 任务名 | 完成时间 | 关键产出 |
|------|--------|---------|---------|
| - | - | - | - |

---

## 阶段一：UI 壳子搭建（允许 mock 数据）

**0001. 完整前端UI壳子搭建**
构建 GerClaw 完整前端 UI 壳子：9 个核心页面/视图、三栏布局、全部按钮与交互、§4.2.3 七项可视化组件、适老化老年模式、响应式适配。Mock 数据集中于 `src/data/mock/`，不调用真实 API。
- 计划文件：[exec-plans/active/0001-完整前端UI壳子搭建.md](exec-plans/active/0001-完整前端UI壳子搭建.md)

---

## 阶段二：功能实现（禁止 mock，逐模块接入真实 API）

> 阶段二首任务（0002）必须先删除 `src/data/mock/` 全部 mock 数据，建立真实 API Client 基础设施，后续任务逐模块接入真实模型/工具服务。

**0002. 删除全部 mock 数据 + API Client 基础设施**
删除 `src/data/mock/`；建立统一 API 基类（超时/重试/降级/熔断/trace_id）、主备模型切换、Zod schema 校验、SSE 流式处理基类。

**0003. 通用对话核心功能**
真实 LLM 流式对话（Vercel AI SDK useChat）、消息气泡、Markdown 渲染、思维链折叠、工具调用可视化、localStorage 会话管理。

**0004. 模型配置与环境变量系统**
openai/dashscope/anthropic 三协议支持、环境变量 Zod 校验、`.env.example`、运行时模型切换 UI。

**0005. 语音交互模块**
MediaRecorder 录音、Mimo ASR 真实集成、Web Audio API PCM16 流式播放、TTS 朗读（冰糖音色）、实时波形、点击式语音对话。

**0006. 医疗安全后处理层**
免责声明自动附加、确定性诊断拦截、高风险症状提示就医、输出格式校验、prompt injection 隔离。

**0007. 联网搜索模块**
AnySearch 真实集成、Tavily 兜底、搜索结果卡片、角标引用标注、搜索结果隔离标记。

**0008. 文档解析模块**
文件上传 UI、MinerU API 真实集成、多模态图片理解、解析结果参与对话上下文。

**0009. 适老化老年模式完整实现**
大字体≥18px、大按钮≥48px、高对比度 WCAG AAA、语音优先入口、操作提示、确认对话框、医生/患者端 UI 差异。

**0010. CGA 评估模块**
5 个量表真实题库 data/scales/、对话化评估状态机、自动计分与分级、§7.4 预录制音频（`/assets/audio/cga/`）、评估报告生成与预览、医生端工作区视图。

**0011. 五大处方模块**
处方生成 prompt 工程、五类处方（药物/运动/营养/心理/康复）结构化输出（Function Calling/JSON Mode）、四重校验、右侧面板预览、PDF/Markdown/DOCX 多格式导出。

**0012. 用药审查模块**
DDI 规则引擎 data/、Beers 标准审查 data/、剂量与重复用药检查、规则引擎 100% 确定性判断、风险等级展示、LLM 解读生成。

**0013. 技能管理模块**
预置技能加载、自定义 skill.md 上传（含 .zip 压缩包自动解压，§3.2.1）、自然语言描述生成技能（§3.2.1）、localStorage 保存、技能加载影响对话行为。

**0014. 结果导出完善**
对话记录导出、处方导出、CGA 报告导出、jsPDF/docx 真实导出。

**0015. MVP 联调与全量测试**
所有模块集成测试、适老化验证、医疗安全验证、主备切换测试、降级测试、`npm run build/lint` 验证、IGA Pages 部署测试。

---

## 技术债追踪

详见 [exec-plans/tech-debt-tracker.md](exec-plans/tech-debt-tracker.md)

## 下一步计划

1. 执行 0001：完整前端 UI 壳子搭建（阶段一）
2. 0001 完成后进入阶段二，执行 0002：删除 mock + API Client 基础设施
3. 按阶段二路线图顺序逐模块实现真实功能，每个模块走开发-审阅-用户测试对抗循环
4. 所有模块完成后进行 MVP 全量验收，部署到 IGA Pages
