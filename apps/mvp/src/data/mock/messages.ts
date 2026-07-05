/**
 * Mock 消息数据
 * 覆盖 7 种可视化块：thinking / tool_call / sub_agent / decision / search_results / file / text
 * 包含：流式消息、引用角标、免责声明
 */
import type { Citation, Message } from "@/types";
import { mockSearchResults } from "./search-results";

const now = Date.now();

const mockCitations: Citation[] = [
  {
    id: 1,
    title: "中国老年高血压管理指南 2024",
    snippet:
      "老年高血压患者血压控制目标建议为 140/90 mmHg 以下，优先选择长效 CCB 或 ARB 类药物。",
    url: "https://example.com/guideline/elderly-hypertension-2024",
    source: "中华医学会老年医学分会",
    publishedDate: "2024-03",
  },
  {
    id: 2,
    title: "老年综合评估（CGA）临床应用专家共识",
    snippet:
      "CGA 是对老年人医学、心理、功能等多维度的综合评估，可识别老年综合征。",
    url: "https://example.com/consensus/cga-clinical",
    source: "中华老年医学杂志",
    publishedDate: "2023-11",
  },
];

export const mockMessagesBySession: Record<string, Message[]> = {
  // === 会话1：血压偏高咨询（患者端，含全部 7 种块）===
  sess_today_1: [
    {
      id: "msg_1",
      sessionId: "sess_today_1",
      role: "user",
      blocks: [
        {
          kind: "text",
          id: "block_1",
          content: "我最近血压偏高，平时在 150/95 左右，该怎么办？",
        },
      ],
      status: "done",
      createdAt: now - 30 * 60 * 1000,
    },
    {
      id: "msg_2",
      sessionId: "sess_today_1",
      role: "assistant",
      blocks: [
        // 1. 思考块
        {
          kind: "thinking",
          id: "block_thinking_1",
          data: {
            id: "thinking_1",
            content:
              "用户为老年患者，主诉血压 150/95 mmHg，高于 140/90 的诊断阈值。需结合年龄、合并症等评估。考虑：1) 询问是否规律监测血压；2) 询问伴随症状；3) 提供生活方式建议；4) 强调就医的重要性，避免给出确定性诊断。",
            status: "done",
            startedAt: now - 25 * 60 * 1000,
            endedAt: now - 24 * 60 * 1000,
          },
        },
        // 2. 工具调用块
        {
          kind: "tool_call",
          id: "block_tool_1",
          data: {
            id: "tool_1",
            toolName: "医疗知识检索",
            params: { query: "老年高血压管理指南 血压控制目标" },
            result: {
              guideline: "中国老年高血压管理指南 2024",
              target: "<140/90 mmHg",
            },
            status: "done",
            startedAt: now - 24 * 60 * 1000,
            endedAt: now - 23 * 60 * 1000,
            durationMs: 1200,
          },
        },
        // 3. 子智能体树
        {
          kind: "sub_agent",
          id: "block_sub_1",
          data: {
            id: "agent_root",
            name: "老年专科医生智能体",
            status: "done",
            startedAt: now - 23 * 60 * 1000,
            endedAt: now - 18 * 60 * 1000,
            children: [
              {
                id: "agent_1",
                name: "用药审查子智能体",
                status: "done",
                detail: "未发现当前用药与降压药存在相互作用",
                startedAt: now - 22 * 60 * 1000,
                endedAt: now - 20 * 60 * 1000,
              },
              {
                id: "agent_2",
                name: "CGA 评估子智能体",
                status: "done",
                detail: "建议进行老年综合评估",
                startedAt: now - 21 * 60 * 1000,
                endedAt: now - 19 * 60 * 1000,
              },
            ],
          },
        },
        // 4. 决策时间线
        {
          kind: "decision",
          id: "block_dec_1",
          data: [
            {
              id: "step_1",
              stepIndex: 0,
              type: "thought",
              title: "评估血压水平",
              content: "150/95 mmHg 高于 140/90 阈值，属于 1 级高血压",
              status: "done",
              durationMs: 350,
              timestamp: now - 23 * 60 * 1000,
            },
            {
              id: "step_2",
              stepIndex: 1,
              type: "action",
              title: "检索老年高血压指南",
              content: "调用医疗知识检索工具",
              status: "done",
              durationMs: 1200,
              timestamp: now - 22 * 60 * 1000,
            },
            {
              id: "step_3",
              stepIndex: 2,
              type: "observation",
              title: "指南推荐",
              content: "血压控制目标 <140/90，优先长效 CCB 或 ARB",
              status: "done",
              durationMs: 280,
              timestamp: now - 21 * 60 * 1000,
            },
          ],
        },
        // 5. 搜索结果块
        {
          kind: "search_results",
          id: "block_search_1",
          data: mockSearchResults.slice(0, 3),
        },
        // 6. 文件块
        {
          kind: "file",
          id: "block_file_1",
          data: {
            id: "file_1",
            fileName: "血压记录表.pdf",
            fileType: "application/pdf",
            fileSize: 245760,
            status: "done",
            progress: 100,
            thumbnailUrl: "/file.svg",
            parsedMarkdown:
              "## 7天血压记录\n| 日期 | 收缩压 | 舒张压 |\n|---|---|---|\n| 7-01 | 148 | 92 |\n| 7-02 | 152 | 96 |\n| 7-03 | 150 | 95 |",
          },
        },
        // 7. 文本块（带引用角标）
        {
          kind: "text",
          id: "block_text_1",
          content:
            "## 血压评估\n您近期血压在 **150/95 mmHg** 左右，略高于目标值 [1]。\n\n### 建议\n1. **规律监测**：每天早晚各测量一次血压并记录\n2. **生活方式调整**：低盐饮食（每日食盐<5g）、适量运动、控制体重\n3. **及时就医**：建议前往社区医院或老年科就诊，由医生评估是否需要药物治疗 [2]\n\n> 注意：以上建议仅供参考，具体诊疗请遵医嘱。",
        },
      ],
      citations: mockCitations,
      status: "done",
      createdAt: now - 20 * 60 * 1000,
      hasDisclaimer: true,
    },
    {
      id: "msg_3",
      sessionId: "sess_today_1",
      role: "user",
      blocks: [
        {
          kind: "text",
          id: "block_3",
          content: "好的，谢谢医生。我需要吃药吗？",
        },
      ],
      status: "done",
      createdAt: now - 10 * 60 * 1000,
    },
    // 流式中的 AI 消息
    {
      id: "msg_4",
      sessionId: "sess_today_1",
      role: "assistant",
      blocks: [
        {
          kind: "thinking",
          id: "block_thinking_2",
          data: {
            id: "thinking_2",
            content: "用户询问是否需要服药。150/95 属于 1 级高血压，需结合心血管风险分层决定。不能给出确定性诊断或直接开药建议，应强调就医评估。",
            status: "thinking",
            startedAt: now - 5 * 60 * 1000,
          },
        },
        {
          kind: "text",
          id: "block_text_streaming",
          content: "是否需要服药需要医生根据您的整体情况评估",
          streaming: true,
        },
      ],
      status: "streaming",
      createdAt: now - 5 * 60 * 1000,
    },
  ],

  // === 会话2：医生端 - 老年用药方案评估 ===
  sess_today_2: [
    {
      id: "msg_d_1",
      sessionId: "sess_today_2",
      role: "user",
      blocks: [
        {
          kind: "text",
          id: "block_d_1",
          content:
            "患者男，78岁，高血压、糖尿病、慢性肾病III期。目前用药：氨氯地平、二甲双胍、阿托伐他汀、雷贝拉唑。请评估用药方案。",
        },
      ],
      status: "done",
      createdAt: now - 2 * 60 * 60 * 1000,
    },
    {
      id: "msg_d_2",
      sessionId: "sess_today_2",
      role: "assistant",
      blocks: [
        {
          kind: "thinking",
          id: "block_d_thinking",
          data: {
            id: "thinking_d",
            content:
              "78岁男性多病共存患者，使用4种药物。需评估：1) 适应症是否适当；2) 剂量是否需要根据肾功能调整；3) 药物相互作用；4) Beers标准潜在不适当用药。",
            status: "done",
            startedAt: now - 110 * 60 * 1000,
            endedAt: now - 109 * 60 * 1000,
          },
        },
        {
          kind: "tool_call",
          id: "block_d_tool_1",
          data: {
            id: "tool_d_1",
            toolName: "用药相互作用检查",
            params: { drugs: ["氨氯地平", "二甲双胍", "阿托伐他汀", "雷贝拉唑"] },
            result: {
              interactions: [
                {
                  drugs: ["氨氯地平", "阿托伐他汀"],
                  severity: "中等",
                  note: "增加肌病风险，建议监测肌酸激酶",
                },
              ],
            },
            status: "done",
            startedAt: now - 109 * 60 * 1000,
            endedAt: now - 108 * 60 * 1000,
            durationMs: 850,
          },
        },
        {
          kind: "tool_call",
          id: "block_d_tool_2",
          data: {
            id: "tool_d_2",
            toolName: "肾功能调整建议",
            params: { drug: "二甲双胍", egfr: 45 },
            status: "failed",
            errorMessage: "未提供患者 eGFR 数值，无法精确计算",
            startedAt: now - 108 * 60 * 1000,
            endedAt: now - 107 * 60 * 1000,
            durationMs: 320,
          },
        },
        {
          kind: "text",
          id: "block_d_text_1",
          content:
            "## 用药方案评估\n\n### 1. 药物相互作用\n检测到 **氨氯地平 + 阿托伐他汀** 存在中等程度相互作用 [1]，增加肌病风险，建议监测肌酸激酶（CK）。\n\n### 2. 用药建议\n- **氨氯地平**：继续使用，监测血压\n- **二甲双胍**：需根据 eGFR 调整剂量\n- **阿托伐他汀**：建议改为亲水性他汀（如瑞舒伐他汀）\n\n> 建议补充：肾功能 eGFR、肝功能、CK 等检查结果",
        },
      ],
      citations: [mockCitations[2]],
      status: "done",
      createdAt: now - 105 * 60 * 1000,
      hasDisclaimer: true,
    },
  ],

  // === 会话3：简单的纯文本对话 ===
  sess_today_3: [
    {
      id: "msg_s_1",
      sessionId: "sess_today_3",
      role: "user",
      blocks: [
        {
          kind: "text",
          id: "block_s_1",
          content: "我最近总是头晕乏力，是不是贫血了？",
        },
      ],
      status: "done",
      createdAt: now - 4 * 60 * 60 * 1000,
    },
    {
      id: "msg_s_2",
      sessionId: "sess_today_3",
      role: "assistant",
      blocks: [
        {
          kind: "text",
          id: "block_s_2",
          content:
            "您好，头晕乏力可能由多种原因引起，包括贫血、低血压、颈椎病等。建议您前往医院进行血常规、血压、血糖等基础检查，以明确原因。请注意休息，避免突然站起。",
        },
      ],
      status: "done",
      createdAt: now - 3.5 * 60 * 60 * 1000,
      hasDisclaimer: true,
    },
  ],
};
