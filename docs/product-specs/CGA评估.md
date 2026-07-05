# CGA评估 — 产品规格

> 模块：CGA评估 | 优先级：P0 | 基于PRD.md第4节生成

---

## 1. 模块概述

CGA（老年综合评估）模块通过自然语言对话引导老年患者完成标准化医学量表评估，支持PHQ-9抑郁、SAS焦虑、PSQI睡眠质量、Mini-Cog认知筛查、MMSE智能状态5个核心量表，实现自动计分、严重程度分级、结果解读和评估报告生成，同时为医生提供CGA工作区查看患者评估进度、结果汇总和历史对比。

> **音频方案说明**（依据 `gerclaw设计要求.md` §7.4）：CGA 量表的**问题题干与选项语音采用预录制音频文件**方案，存储于 `/assets/audio/cga/{量表id}/{题号}.mp3`（选项音频 `{题号}_opt{n}.mp3`），播放时直接加载音频文件，**不调用 TTS 模型**，避免重复调用 TTS 造成的延迟与成本。TTS 仅用于**评估报告朗读**（报告内容为动态生成，无法预录制）。

## 2. 用户故事

| 编号 | 作为... | 我想要... | 以便于... |
|------|---------|----------|----------|
| US-001 | 老年患者 | 通过语音对话一步步完成评估问题，不用填表 | 轻松完成老年综合评估，不会因为复杂表单而困惑 |
| US-002 | 老年患者 | 评估问题能语音朗读、用大按钮选择答案 | 视力不好也能顺利完成评估 |
| US-003 | 老年患者 | 评估中断后能从上次的地方继续 | 不用重新开始已经答过的题目 |
| US-004 | 老年患者 | 评估完成后能得到通俗易懂的结果解读 | 了解自己的健康状况 |
| US-005 | 老年科医生 | 在工作区查看患者评估进度和结果汇总 | 快速掌握多位患者的评估情况 |
| US-006 | 老年科医生 | 查看患者历史评估结果对比 | 跟踪患者健康状况变化趋势 |
| US-007 | 老年科医生 | 导出患者的CGA评估报告 | 用于临床记录和转诊 |
| US-008 | 老年科医生 | 在对话中引导患者完成评估 | 实时查看患者答题情况，必要时补充说明 |

## 3. 功能清单

| 编号 | 功能 | 描述 | 优先级 | 验收标准 |
|------|------|------|--------|---------|
| F-001 | 量表选择 | 提供5个标准化量表供选择：PHQ-9(抑郁)、SAS(焦虑)、PSQI(睡眠)、Mini-Cog(认知筛查)、MMSE(智能状态) | P0 | 可看到5个量表的名称、描述、题目数量、预计时长 |
| F-002 | 对话化评估引导 | 通过自然语言对话一道一道引导患者完成量表，不像传统填表 | P0 | 一次只问一个问题，语言口语化，允许答非所问时温和澄清 |
| F-003 | 右侧面板答题界面 | 评估时右侧面板展示题目、大按钮选项、进度条、语音朗读按钮 | P0 | 面板宽度400-500px，老年模式下字体≥18px，按钮≥48px |
| F-004 | 语音交互支持 | 所有问题自动播放预录制音频朗读（§7.4，非TTS实时合成），支持语音输入回答 | P0 | 点击🔊播放预录制音频，老年模式默认自动播放；音频文件存于 `/assets/audio/cga/` |
| F-005 | 题目导航 | 支持上一题/下一题导航、快速跳转到任意题目 | P0 | 已答题显示✓，未答题显示空心，当前题高亮 |
| F-006 | 自动计分 | 完成量表后自动计算得分，严格遵循各量表评分标准 | P0 | PHQ-9(0-27分)、SAS(标准分)、PSQI(0-21分)、Mini-Cog(0-5分)、MMSE(0-30分)计分准确 |
| F-007 | 严重程度分级 | 根据得分自动判定严重程度等级，给出临床建议 | P0 | 每个量表分级符合医学标准，PHQ-9第9题（自伤意念）单独风险提示 |
| F-008 | 结果解读 | 生成通俗易懂的结果解读，避免医学术语恐吓 | P0 | 不使用"痴呆""智力"等词汇，用"记性可能需要多练练"等温和表述 |
| F-009 | 评估报告生成 | 完成评估后生成结构化CGA评估报告 | P0 | 包含各量表得分、分级、建议、免责声明 |
| F-010 | 右侧面板报告预览 | 评估报告在右侧面板展示，支持目录导航 | P0 | Markdown渲染，可滚动查看长内容 |
| F-011 | 报告导出 | 支持导出评估报告为PDF、Markdown、DOCX格式 | P0 | 导出文件格式正确，内容完整 |
| F-012 | 断点续答 | 评估中断后再次进入可从断点继续 | P0 | 已答题目和答案保留，进度正确 |
| F-013 | 医生端CGA工作区 | 医生端可查看患者评估进度、结果汇总 | P0 | 显示患者列表、评估状态、完成时间、关键得分 |
| F-014 | 历史评估对比 | 医生端可查看同一患者多次评估结果对比 | P0 | 不同时间评估得分并列展示，变化趋势可见 |
| F-015 | 适老化适配 | 患者端老年模式下字体放大、按钮加大、对比度增强 | P0 | 正文≥18px，按钮≥48px，对比度≥7:1(AAA) |
| F-016 | 敏感问题处理 | PHQ-9第9题（自伤意念）后置提问并加铺垫语 | P0 | 问题前有"接下来这个问题有点直接，但对您健康很重要"铺垫 |
| F-017 | 疲劳检测与休息提示 | 检测到患者疲劳（"累了""不想说了"）时主动提议休息保存进度 | P0 | 识别疲劳信号，提示保存断点，礼貌道别 |
| F-018 | 医疗安全与免责 | 所有评估结果附带"筛查工具，不能替代临床诊断"免责声明 | P0 | 报告底部和高风险结果处显示免责声明 |
| F-019 | 高风险预警 | PHQ-9第9题得分≥1分、重度抑郁/焦虑/认知障碍时提示就医 | P0 | 高风险结果醒目显示，建议立即就医/转诊 |
| F-020 | 对话区联动 | 主聊天区显示评估引导和实时反馈 | P0 | 显示"您已完成3/9题，继续加油！"等进度提示 |

## 4. 交互流程

### 4.1 主流程（Happy Path）

```
患者端：
1. 用户点击输入框左侧📋评估按钮 / 欢迎页"老年综合评估"卡片 / 对话中说"我要做评估"
2. 右侧面板自动展开，显示量表选择界面（5个量表卡片）
3. 用户选择一个或多个量表开始评估
4. 系统通过对话问候，说明评估时长和注意事项
5. 右侧面板显示第一道题：
   - 题目文字（大字体）
   - 🔊语音朗读按钮（老年模式自动播放）
   - 选项以大卡片形式展示（每个选项含文字+分值）
   - 顶部进度条（如"PHQ-9：1/9"）
   - 底部上一题/下一题按钮、题目导航点
6. 用户点击选项卡片 / 语音回答
7. 系统在对话中给予简短反馈（如"好的，我记下了"），然后展示下一题
8. 重复5-7直到所有题目完成
9. 主聊天区显示思考过程→自动计分→生成报告
10. 右侧面板展示完整评估报告，支持目录导航、语音朗读、导出
11. 主聊天区给出关键结论摘要，显示"查看完整报告"和"导出"按钮

医生端：
1. 医生切换到医生端，进入CGA工作区
2. 查看患者列表：每位患者显示评估状态（未开始/进行中/已完成）、最近评估时间
3. 点击患者查看详情：
   - 评估进度（进行中患者显示完成百分比）
   - 已完成量表的得分和分级
   - 历史评估记录列表
4. 点击"查看报告"在右侧面板打开完整评估报告
5. 点击"历史对比"查看多次评估结果趋势
6. 可导出报告为PDF/Markdown/DOCX
7. 可在对话中引导患者继续未完成的评估
```

### 4.2 异常流程

| 异常场景 | 系统行为 | 用户提示 |
|---------|---------|---------|
| 用户答非所问/扯家常 | LLM先共情回应，再温和拉回当前问题；连续3次无效则右侧面板突出显示选项按钮 | "您说的我理解了，咱们先回到这个问题好吗？您觉得最近两周做事时提不起劲的时候多吗？" |
| 用户说"没听清""再说一遍" | 重复朗读当前问题，右侧面板题目高亮显示 | 🔊重新播放语音，对话中重复问题文字 |
| 用户说"刚才说错了""回上一题" | 调用回退逻辑，返回上一题，已选答案可修改 | "好的，咱们回到上一题，您重新选择一下" |
| 用户说"累了""不想说了" | 主动保存断点，提示可以下次继续 | "没关系，您先休息，我已经保存了您的进度，下次来可以接着做" |
| 评估中途关闭页面/刷新 | 自动保存当前进度到localStorage | 下次进入时提示"您上次的评估还没完成，是否继续？" |
| PHQ-9第9题（自伤意念）得分≥1分 | 立即进行风险提示，建议寻求专业帮助 | "您提到有伤害自己的想法，这很重要，请您立即告诉家人或医生，必要时拨打心理援助热线或前往医院" |
| 得分达到重度（如PHQ-9≥20分、SAS≥70分） | 结果醒目显示（红色警告），强烈建议就医 | "评估结果显示您可能需要专业帮助，建议您尽快到医院就诊" |
| Mini-Cog/MMSE显示认知障碍可能 | 避免使用"痴呆"等恐吓词汇，建议进一步检查 | "这个筛查提示记性方面可能需要多留意，建议您到医院做个更详细的检查" |
| 语音识别失败/麦克风权限被拒 | 提示用户检查权限，自动切换到文本/点击选项模式 | "无法访问麦克风，请检查权限设置，您也可以直接点击选项回答" |
| LLM回复异常/跳题 | 前端状态机强制校验题号连续，异常时重置到当前正确题目 | "让我再确认一下这个问题..."，重新显示当前题目 |

## 5. 界面/API规格

### 5.1 界面

**患者端 - 量表选择界面（右侧面板）**
- 入口：点击📋评估按钮后自动展开
- 关键元素：
  - 标题："选择评估量表"
  - 5个量表卡片：每个卡片含量表图标、名称、一句话描述、题目数量、预计时长
  - 多选支持：可勾选多个量表连续评估
  - 开始评估按钮（大按钮）
- 状态：
  - 主流程：5个卡片可选，按钮可点击
  - 加载中：骨架屏占位
  - 为空：无（MVP固定5个量表）
  - 错误：提示"加载失败，请重试"

**患者端 - 答题界面（右侧面板）**
- 入口：选择量表开始评估后
- 面板布局（400-500px宽）：
  - 顶部进度区：
    - 量表名称 + 题目进度（如"PHQ-9 抑郁评估：3/9"）
    - 进度条可视化（已完成绿色，当前蓝色，未完成灰色）
    - 放弃/关闭按钮×
  - 问题展示区（中部滚动）：
    - 问题序号 + 问题文字（大字体，高对比度）
    - 🔊语音朗读按钮（播放时显示波形动画）
    - 评估时间范围提示（如"过去两周内"）
  - 选项展示区：
    - 选项以大卡片形式排列（垂直排列，间距≥16px）
    - 每个选项：选项文字（通俗表述，非原始分值选项）+ 分值小标签
    - 点击卡片即选中，选中后高亮边框+背景
    - 支持语音输入按钮🎤
  - 导航区（底部）：
    - 上一题按钮（第一题禁用）
    - 题目导航点（小圆点，已答✓，未答空心，当前蓝色边框，可点击跳转）
    - 下一题按钮（选中选项后激活）
- 状态：
  - 主流程：题目和选项正常显示，可交互
  - 加载中：语音加载时显示波形占位
  - 为空：无（量表必有题目）
  - 错误：语音失败显示重试按钮

**患者端 - 评估报告界面（右侧面板）**
- 入口：完成所有题目后自动展示
- 关键元素：
  - 报告标题："老年综合评估报告"
  - 评估基本信息：评估时间、患者信息（可选）
  - 目录导航（点击跳转到对应章节）
  - 各量表结果卡片：
    - 量表名称
    - 得分（大字显示）+ 总分
    - 严重程度分级（彩色标签：绿色正常/黄色轻度/橙色中度/红色重度）
    - 结果解读（通俗易懂的文字）
    - 临床建议
  - 综合总结与建议
  - 免责声明（底部醒目位置）
  - 操作按钮：🔊语音朗读、📥导出（PDF/Markdown/DOCX）
- 状态：
  - 主流程：报告完整渲染
  - 加载中：生成中显示进度动画
  - 为空：无（完成必有报告）
  - 错误：生成失败显示重试按钮

**医生端 - CGA工作区**
- 入口：医生端左侧导航"CGA工作区"
- 关键元素：
  - 患者列表（左侧或主区域）：
    - 患者姓名/标识
    - 评估状态标签（未开始/进行中/已完成）
    - 最近评估时间
    - 关键得分摘要（如"PHQ-9: 5分 轻度"）
  - 患者详情区：
    - 评估进度条（进行中患者）
    - 本次评估各量表得分详情
    - 历史评估记录时间线
    - "查看报告""导出""历史对比"按钮
  - 历史对比视图：
    - 同一量表多次评估得分折线/柱状对比
    - 分级变化标注
- 状态：
  - 主流程：列表和详情正常显示
  - 加载中：骨架屏
  - 为空：显示"暂无评估记录"
  - 错误：加载失败提示

### 5.2 API端点（MVP纯前端，无后端API；二阶段FastAPI接口）

| 方法 | 路径 | 描述 | 认证 | 请求参数 | 响应格式 |
|------|------|------|------|---------|---------|
| GET | /api/cga/scales | 获取可用量表列表 | 是（二阶段） | 无 | `{ scales: ScaleInfo[] }` |
| POST | /api/cga/assessments/start | 开始新评估 | 是 | `{ scaleIds: string[], patientId?: string }` | `{ assessmentId: string, firstQuestion: Question }` |
| POST | /api/cga/assessments/:id/answer | 提交答案 | 是 | `{ questionIndex: number, answer: string\|int, score: int }` | `{ nextQuestion?: Question, isCompleted: boolean, progress: number }` |
| GET | /api/cga/assessments/:id | 获取评估状态 | 是 | 无 | `{ assessment: AssessmentState }` |
| POST | /api/cga/assessments/:id/complete | 完成评估生成报告 | 是 | 无 | `{ report: AssessmentReport }` |
| GET | /api/cga/assessments/:id/report | 获取评估报告 | 是 | 无 | `{ report: AssessmentReport }` |
| GET | /api/cga/patients/:id/assessments | 获取患者历史评估列表 | 是 | 无 | `{ assessments: AssessmentSummary[] }` |
| POST | /api/cga/reports/:id/export | 导出报告 | 是 | `{ format: 'pdf'\|'markdown'\|'docx' }` | 文件流（bytes） |

> MVP阶段：所有数据存储在前端localStorage，不调用后端API；量表定义存放在`data/scales/`目录下的JSON文件。

## 6. 数据模型

```typescript
// 量表定义（存放在data/scales/*.json）
interface Scale {
  id: string;                    // 'phq9' | 'sas' | 'psqi' | 'minicog' | 'mmse'
  name: string;                  // 量表全称
  shortName: string;             // 简称
  description: string;           // 一句话描述
  category: string;              // '抑郁' | '焦虑' | '睡眠' | '认知'
  estimatedDuration: string;     // 预计时长，如'2-3分钟'
  timeRange: string;             // 评估时间范围说明
  instructions: string;          // 指导语
  questions: Question[];         // 题目列表
  scoringRules: ScoringRules;    // 评分规则
  interpretation: Interpretation; // 结果解读
}

interface Question {
  id: string;                    // 题目ID，如'phq9_q1'
  index: number;                 // 题目序号（0-based）
  text: string;                  // 题目文本（口语化，用于对话）
  originalText: string;          // 原始量表题目文本
  type: 'single_choice' | 'text' | 'time' | 'number' | 'draw_clock' | 'three_words';
  options?: Option[];            // 选项（单选类型）
  reverseScored?: boolean;       // 是否反向计分题（SAS专用）
  isSensitive?: boolean;         // 是否敏感问题（如PHQ-9第9题）
  sensitivePrefix?: string;      // 敏感问题铺垫语
  skipLogic?: SkipLogic;         // 跳转逻辑
}

interface Option {
  text: string;                  // 选项文字（通俗表述）
  originalText: string;          // 原始选项文字
  score: number;                 // 对应分值
}

interface SkipLogic {
  condition: string;             // 条件表达式
  targetQuestionIndex: number;   // 跳转到的题目索引
}

interface ScoringRules {
  rawScoreFormula: string;       // 粗分计算公式描述
  standardScoreFormula?: string; // 标准分换算（SAS用：粗分×1.25取整）
  dimensionScores?: DimensionScore[]; // 分维度计分（PSQI用）
  factorWeights?: Record<string, number>; // 因子权重
  reverseScoredQuestions?: number[]; // 反向计分题号（SAS: 5,9,13,17,19）
}

interface DimensionScore {
  name: string;                  // 维度名称
  questionIds: string[];         // 包含的题目ID
  formula: string;               // 计分公式
  maxScore: number;              // 该维度满分
}

interface Interpretation {
  levels: SeverityLevel[];       // 严重程度分级
  specialRules?: SpecialRule[];  // 特殊规则（如PHQ-9第9题单独处理）
  disclaimer: string;            // 免责声明文本
}

interface SeverityLevel {
  minScore: number;              // 最低分（含）
  maxScore: number;              // 最高分（含）
  level: string;                 // 等级名称：'无' | '轻度' | '中度' | '中重度' | '重度'
  color: string;                 // 对应颜色标签：'green' | 'yellow' | 'orange' | 'red'
  interpretation: string;        // 结果解读（通俗易懂）
  recommendation: string;        // 临床建议
}

interface SpecialRule {
  condition: string;             // 触发条件
  level: string;                 // 风险等级
  message: string;               // 提示消息
  urgent: boolean;               // 是否紧急（需要立即提示）
}

// 评估会话状态（localStorage存储）
interface AssessmentState {
  id: string;                    // 评估会话ID
  scaleIds: string[];            // 本次评估的量表ID列表
  currentScaleIndex: number;     // 当前正在做的量表索引
  currentQuestionIndex: number;  // 当前题目索引
  answers: Record<string, Answer>; // 所有答案：key为questionId
  progress: number;              // 总体进度0-100
  startedAt: string;             // 开始时间ISO
  updatedAt: string;             // 最后更新时间ISO
  completedAt?: string;          // 完成时间ISO
  isCompleted: boolean;          // 是否完成
  checkpoint?: Checkpoint;       // 断点信息
}

interface Answer {
  questionId: string;
  rawAnswer: string;             // 用户原始回答（语音转写/点击的选项原文）
  selectedOptionIndex?: number;  // 选择的选项索引（单选）
  score: number;                 // 对应分值
  timestamp: string;
}

interface Checkpoint {
  scaleId: string;
  questionIndex: number;
  savedAt: string;
}

// 评估结果
interface ScaleResult {
  scaleId: string;
  scaleName: string;
  rawScore: number;
  standardScore?: number;
  dimensionScores?: Record<string, number>; // 分维度得分（PSQI）
  maxScore: number;
  severityLevel: string;
  severityColor: string;
  interpretation: string;
  recommendation: string;
  specialAlerts?: SpecialAlert[]; // 特殊预警（如自伤意念）
}

interface SpecialAlert {
  type: string;                  // 'suicide_risk' | 'severe_depression' | 'cognitive_impairment'
  level: 'warning' | 'urgent';
  message: string;
}

interface AssessmentReport {
  id: string;
  assessmentId: string;
  patientInfo?: PatientInfo;
  completedAt: string;
  scaleResults: ScaleResult[];
  summary: string;               // 综合总结
  overallRecommendations: string; // 总体建议
  disclaimer: string;
  references?: Reference[];      // 参考文献
}

interface PatientInfo {
  name?: string;
  age?: number;
  gender?: string;
  educationLevel?: string;       // 教育程度（MMSE校正用）
}

interface Reference {
  title: string;
  authors: string;
  journal: string;
  year: number;
}

// 医生端患者评估摘要
interface AssessmentSummary {
  id: string;
  completedAt: string;
  scales: string[];              // 完成的量表列表
  keyFindings: string[];         // 关键发现摘要
  riskLevel: 'normal' | 'attention' | 'urgent';
}

// 5个量表的评分标准摘要
// PHQ-9: 9题，0-3分/题，总分0-27分
//   0-4无抑郁，5-9轻度，10-14中度，15-19中重度，20-27重度
//   第9题（自伤意念）单独评估，≥1分立即预警
// SAS: 20题，1-4分/题，5道反向计分（5,9,13,17,19），粗分×1.25=标准分
//   <50无焦虑，50-59轻度，60-69中度，≥70重度
// PSQI: 19个自评条目，7个因子，每个0-3分，总分0-21分
//   0-5很好，6-10较好，11-15一般，16-21差
//   涉及睡眠效率计算：睡眠时间/床上时间×100%
// Mini-Cog: 三词回忆(0-3分) + 时钟绘制(0-2分)，总分0-5分
//   0-2可能认知障碍，3-5正常
// MMSE: 30题，1分/题，总分0-30分
//   27-30正常，21-26轻度，10-20中度，0-9重度
//   教育程度校正：文盲≤17，小学≤20，中学以上≤24为异常
```

## 7. 非功能要求

| 维度 | 要求 |
|------|------|
| 性能 | 量表题目加载<200ms（本地JSON）；答案提交响应<100ms；计分和报告生成<1s；预录制音频加载<300ms（§7.4，非TTS）；报告朗读TTS首包<1s |
| 安全 | 评估数据仅存localStorage，不上传（MVP访客模式）；高风险结果（自伤意念）必须醒目提示；禁止给出确定性诊断结论 |
| 可靠性 | 每题答完自动保存进度；刷新/关闭页面不丢失已答数据；API调用（LLM/TTS）失败自动重试2次；LLM评分异常时使用确定性计分逻辑兜底；预录制音频加载失败时降级为TTS合成 |
| 可观测性 | 关键操作日志（开始评估、完成题目、完成评估、导出报告）；错误捕获和上报；评估完成率、中断位置统计 |
| 适老化 | 患者端老年模式：正文≥18px，按钮≥48px，对比度≥7:1(AAA)，问题自动播放预录制音频朗读（§7.4），选项大卡片间距≥16px，关键操作二次确认 |
| 兼容性 | Chrome/Edge/Safari最新2个版本；桌面端和平板端完整支持；手机端答题界面全屏覆盖；语音功能需HTTPS环境 |
| 合规性 | 报告必须标注"AI生成，仅供参考，不构成医疗建议"；明确说明量表为筛查工具而非诊断工具；PHQ-9自伤条目必须提供危机干预资源提示 |

## 8. 不做什么（Out of Scope）

- ADL/IADL/MNA-SF/跌倒/GDS等其他CGA量表（P1阶段扩充，MVP仅5个核心量表）
- 后端持久化存储（MVP纯前端localStorage，P1阶段PostgreSQL）
- 患者健康画像关联（P1阶段）
- 医生端评估报告编辑修改功能（MVP仅查看导出，P1考虑）
- 多智能体协作评估（MVP单智能体prompt实现，P1 AgentScope编排）
- 评估过程中实时联网搜索医学信息（设计要求7.7节明确CGA不启用联网搜索）
- 自定义量表上传功能（固定5个量表）
- 评估数据的多设备同步（P1账号系统实现后支持）
- 同伴评定部分（PSQI第11-15题需要室友/配偶协助，MVP暂不实现）
- MMSE时钟绘制、书写句子、结构绘图等需要纸笔/绘图的交互（Mini-Cog时钟绘制MVP通过对话引导描述+简化判断，完整绘图功能P1考虑）
- Mini-Cog/MMSE的实物命名（手表/钢笔）MVP通过图片展示替代
