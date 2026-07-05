/**
 * Mock 五大处方数据
 * 对齐 gerclaw设计要求.md §6 五大处方模块
 * 循证来源使用真实存在的指南名称，禁止编造文献
 */
import type {
  HealthDiagnosis,
  PatientSummary,
  PrescriptionReport,
  PrescriptionStage,
} from "@/types";

/** 默认展示阶段：预览态 */
export const mockPrescriptionStage: PrescriptionStage = "done";

/** 患者信息摘要 */
export const mockPatientSummary: PatientSummary = {
  name: "张桂芳",
  age: 78,
  gender: "female",
  chiefComplaint: "血压偏高 1 月余，伴头晕乏力",
  history: ["高血压病史 10 年", "2 型糖尿病 5 年", "轻度认知障碍"],
  allergies: ["青霉素过敏"],
  currentMedications: ["氨氯地平 5mg qd", "二甲双胍 0.5g bid", "阿托伐他汀 20mg qn"],
  vitals: {
    血压: "150/95 mmHg",
    血糖: "7.2 mmol/L",
    心率: "78 次/分",
    BMI: "24.5",
  },
};

/** 健康诊断（疑似，禁止确定性诊断） */
export const mockHealthDiagnosis: HealthDiagnosis = {
  summary:
    "患者为老年女性，多病共存（高血压+糖尿病+轻度认知障碍），目前血压、血糖控制均未达标，需综合干预。",
  problems: [
    "血压控制未达标（150/95 mmHg，目标 <140/90）",
    "血糖控制欠佳（空腹 7.2 mmol/L，目标 7.0-7.5）",
    "多重用药风险（3 种药物）",
    "轻度认知障碍需进一步评估",
    "跌倒风险增加（头晕乏力症状）",
  ],
  suspectedDiagnoses: [
    "疑似 1 级高血压（未达标）",
    "疑似 2 型糖尿病（控制不佳）",
    "疑似轻度认知障碍",
  ],
  riskFactors: ["高龄", "多病共存", "多重用药", "活动量不足"],
};

/** 五大处方报告 */
export const mockPrescriptionReport: PrescriptionReport = {
  id: "rx_demo_001",
  sessionId: "sess_today_1",
  createdAt: Date.now(),
  patient: mockPatientSummary,
  diagnosis: mockHealthDiagnosis,
  sections: [
    // 1. 药物处方
    {
      type: "drug",
      title: "药物处方",
      summary:
        "调整降压方案，维持降糖与他汀治疗，注意多药相互作用监测。",
      items: [
        {
          name: "氨氯地平片",
          detail: "长效二氢吡啶类 CCB，老年高血压一线选择",
          dosage: "5mg",
          frequency: "每日 1 次，晨起服用",
          duration: "长期",
          precautions: ["监测血压", "注意下肢水肿"],
          evidence: [
            {
              title: "中国老年高血压管理指南 2023",
              snippet:
                "老年高血压优先选择长效 CCB 或 ARB，目标血压 <140/90 mmHg。",
            },
          ],
        },
        {
          name: "二甲双胍片",
          detail: "2 型糖尿病一线降糖药，注意肾功能评估",
          dosage: "0.5g",
          frequency: "每日 2 次，餐中服用",
          duration: "长期",
          precautions: ["监测 eGFR", "注意胃肠道反应"],
          evidence: [
            {
              title: "中国 2 型糖尿病防治指南 2020",
              snippet:
                "二甲双胍是 2 型糖尿病一线用药，eGFR<45 需减量，<30 禁用。",
            },
          ],
        },
        {
          name: "阿托伐他汀钙片",
          detail: "他汀类调脂药，注意与 CCB 相互作用",
          dosage: "20mg",
          frequency: "每晚 1 次",
          duration: "长期",
          precautions: ["监测肌酸激酶", "注意肝功能", "警惕肌病风险"],
          evidence: [
            {
              title: "中国成人血脂异常防治指南 2023",
              snippet:
                "老年高危人群 LDL-C 目标 <1.8 mmol/L，他汀治疗需监测 CK 和肝酶。",
            },
          ],
        },
      ],
      evidence: [
        { title: "中国老年高血压管理指南 2023" },
        { title: "中国 2 型糖尿病防治指南 2020" },
        { title: "中国成人血脂异常防治指南 2023" },
      ],
    },
    // 2. 运动处方
    {
      type: "exercise",
      title: "运动处方",
      summary:
        "低中强度有氧运动为主，结合平衡训练降低跌倒风险。",
      items: [
        {
          name: "有氧运动-散步",
          detail: "中等强度有氧运动，改善血压和血糖控制",
          dosage: "心率维持在 (170-年龄) 次/分左右",
          frequency: "每周 5 次",
          duration: "每次 30 分钟",
          precautions: ["避免清晨空腹运动", "运动前后监测血压", "出现头晕立即停止"],
          evidence: [
            {
              title: "中国老年人运动指南 2021",
              snippet:
                "老年人推荐每周 150 分钟中等强度有氧运动，分散在 3-5 天。",
            },
          ],
        },
        {
          name: "平衡训练-太极拳",
          detail: "改善平衡功能，降低跌倒风险",
          frequency: "每周 3 次",
          duration: "每次 20-30 分钟",
          precautions: ["动作缓慢柔和", "避免突然转身"],
          evidence: [
            {
              title: "老年跌倒预防干预专家共识 2022",
              snippet: "太极拳可降低老年人跌倒风险约 30%。",
            },
          ],
        },
        {
          name: "抗阻训练-弹力带",
          detail: "维持肌肉量，预防老年肌少症",
          frequency: "每周 2-3 次",
          duration: "每次 15-20 分钟",
          precautions: ["阻力适中", "避免憋气"],
          evidence: [
            {
              title: "中国老年肌少症诊疗专家共识 2021",
              snippet: "老年人群推荐每周 2-3 次抗阻训练预防肌少症。",
            },
          ],
        },
      ],
      evidence: [
        { title: "中国老年人运动指南 2021" },
        { title: "老年跌倒预防干预专家共识 2022" },
        { title: "中国老年肌少症诊疗专家共识 2021" },
      ],
    },
    // 3. 营养处方
    {
      type: "nutrition",
      title: "营养处方",
      summary:
        "DASH 饮食模式为主，控制钠盐与精制糖摄入。",
      items: [
        {
          name: "限盐饮食",
          detail: "每日食盐摄入 <5g，减少加工食品",
          frequency: "每日执行",
          duration: "长期",
          precautions: ["注意隐形盐", "使用低钠盐替代"],
          evidence: [
            {
              title: "中国居民膳食指南 2022",
              snippet: "成人每日食盐 <5g，高血压患者建议更低。",
            },
          ],
        },
        {
          name: "DASH 饮食模式",
          detail: "富含蔬果、全谷物、低脂乳制品，减少饱和脂肪",
          frequency: "每日执行",
          duration: "长期",
          precautions: ["逐渐过渡", "保证蛋白质摄入"],
          evidence: [
            {
              title: "中国高血压防治指南 2024",
              snippet: "DASH 饮食可降低收缩压 8-14 mmHg。",
            },
          ],
        },
        {
          name: "糖尿病饮食控制",
          detail: "控制碳水化合物总量，选择低 GI 食物",
          frequency: "每日执行",
          duration: "长期",
          precautions: ["定时定量", "避免精制糖"],
          evidence: [
            {
              title: "中国 2 型糖尿病防治指南 2020",
              snippet: "糖尿病饮食应个体化，碳水化合物供能比 50-65%。",
            },
          ],
        },
      ],
      evidence: [
        { title: "中国居民膳食指南 2022" },
        { title: "中国高血压防治指南 2024" },
        { title: "中国 2 型糖尿病防治指南 2020" },
      ],
    },
    // 4. 心理处方
    {
      type: "psychology",
      title: "心理处方",
      summary:
        "针对轻度焦虑与认知障碍风险，提供心理疏导与认知训练建议。",
      items: [
        {
          name: "认知功能训练",
          detail: "记忆力、注意力训练，延缓认知衰退",
          frequency: "每周 3-5 次",
          duration: "每次 20 分钟",
          precautions: ["难度循序渐进", "保持兴趣"],
          evidence: [
            {
              title: "中国老年认知障碍诊疗指南 2023",
              snippet: "认知训练可延缓 MCI 向痴呆转化。",
            },
          ],
        },
        {
          name: "放松训练",
          detail: "深呼吸、冥想等放松技巧，缓解焦虑",
          frequency: "每日 1-2 次",
          duration: "每次 10-15 分钟",
          precautions: ["环境安静", "避免过度疲劳"],
          evidence: [
            {
              title: "老年心理健康干预专家共识 2022",
              snippet: "放松训练对老年焦虑症状有改善作用。",
            },
          ],
        },
        {
          name: "社交活动建议",
          detail: "鼓励参与社区活动，维持社交连接",
          frequency: "每周 2-3 次",
          duration: "持续进行",
          precautions: ["避免独处过久"],
          evidence: [
            {
              title: "老年心理健康干预专家共识 2022",
              snippet: "社交活动可降低老年人抑郁和认知衰退风险。",
            },
          ],
        },
      ],
      evidence: [
        { title: "中国老年认知障碍诊疗指南 2023" },
        { title: "老年心理健康干预专家共识 2022" },
      ],
    },
    // 5. 康复处方
    {
      type: "rehabilitation",
      title: "康复处方",
      summary:
        "针对跌倒风险与活动能力下降，制定康复干预方案。",
      items: [
        {
          name: "居家环境改造",
          detail: "卫生间防滑、扶手安装、夜间照明改善",
          frequency: "一次性",
          duration: "立即执行",
          precautions: ["评估居家环境", "重点改造卫生间"],
          evidence: [
            {
              title: "老年跌倒预防干预专家共识 2022",
              snippet: "居家环境改造可降低跌倒发生率约 35%。",
            },
          ],
        },
        {
          name: "步态训练",
          detail: "纠正异常步态，提高步行稳定性",
          frequency: "每周 2-3 次",
          duration: "每次 20 分钟",
          precautions: ["穿合适鞋袜", "使用辅助器具"],
          evidence: [
            {
              title: "老年康复医学专家共识 2021",
              snippet: "步态训练可改善老年平衡功能，降低跌倒风险。",
            },
          ],
        },
        {
          name: "维生素 D 补充",
          detail: "改善肌肉功能，预防跌倒",
          dosage: "800-1000 IU",
          frequency: "每日 1 次",
          duration: "长期",
          precautions: ["监测血钙", "避免过量"],
          evidence: [
            {
              title: "老年跌倒预防干预专家共识 2022",
              snippet: "维生素 D 补充可降低老年人跌倒风险。",
            },
          ],
        },
      ],
      evidence: [
        { title: "老年跌倒预防干预专家共识 2022" },
        { title: "老年康复医学专家共识 2021" },
      ],
    },
  ],
  citations: [
    { title: "中国老年高血压管理指南 2023", url: "https://example.com/guideline/elderly-htn-2023" },
    { title: "中国 2 型糖尿病防治指南 2020", url: "https://example.com/guideline/t2dm-2020" },
    { title: "中国成人血脂异常防治指南 2023", url: "https://example.com/guideline/lipid-2023" },
    { title: "中国老年人运动指南 2021", url: "https://example.com/guideline/elderly-exercise-2021" },
    { title: "老年跌倒预防干预专家共识 2022", url: "https://example.com/consensus/fall-2022" },
    { title: "中国老年肌少症诊疗专家共识 2021", url: "https://example.com/consensus/sarcopenia-2021" },
    { title: "中国居民膳食指南 2022", url: "https://example.com/guideline/diet-2022" },
    { title: "中国高血压防治指南 2024", url: "https://example.com/guideline/htn-2024" },
    { title: "中国老年认知障碍诊疗指南 2023", url: "https://example.com/guideline/cognitive-2023" },
    { title: "老年心理健康干预专家共识 2022", url: "https://example.com/consensus/mh-2022" },
    { title: "老年康复医学专家共识 2021", url: "https://example.com/consensus/rehab-2021" },
  ],
  disclaimer: "内容由 AI 生成，仅供参考。身体不适请及时就医。",
};
