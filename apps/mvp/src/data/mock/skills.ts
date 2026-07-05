/**
 * Mock 技能列表数据
 * 对齐 gerclaw设计要求.md §4.9 Skill 模块 / design-docs/技能管理.md
 */

export interface MockSkill {
  id: string;
  name: string;
  description: string;
  category: "通用" | "专科" | "自定义";
  enabled: boolean;
  source: "builtin" | "custom";
  tags: string[];
}

export const mockSkills: MockSkill[] = [
  {
    id: "skill_elderly_htn",
    name: "老年高血压管理",
    description: "基于《中国老年高血压管理指南 2023》提供老年高血压评估与用药建议 SOP",
    category: "专科",
    enabled: true,
    source: "builtin",
    tags: ["高血压", "心血管", "老年"],
  },
  {
    id: "skill_diabetes_med",
    name: "糖尿病用药",
    description: "依据《中国 2 型糖尿病防治指南 2020》指导降糖药选择与剂量调整",
    category: "专科",
    enabled: true,
    source: "builtin",
    tags: ["糖尿病", "用药"],
  },
  {
    id: "skill_fall_risk",
    name: "跌倒风险评估",
    description: "使用 Morse 跌倒风险评估量表，制定环境改造与运动干预方案",
    category: "专科",
    enabled: false,
    source: "builtin",
    tags: ["跌倒", "康复"],
  },
  {
    id: "skill_elderly_depression",
    name: "老年抑郁筛查",
    description: "使用 PHQ-9 量表筛查老年抑郁，提供分层干预建议",
    category: "专科",
    enabled: true,
    source: "builtin",
    tags: ["心理", "抑郁"],
  },
  {
    id: "skill_polypharmacy_review",
    name: "多药相互作用审查",
    description: "识别老年人多重用药（≥5 种）相互作用与 Beers 标准潜在不适当用药",
    category: "专科",
    enabled: true,
    source: "builtin",
    tags: ["用药", "审查", "Beers"],
  },
  {
    id: "skill_cga_assessment",
    name: "CGA 综合评估",
    description: "执行多维度老年综合评估，识别老年综合征与功能下降",
    category: "专科",
    enabled: false,
    source: "builtin",
    tags: ["CGA", "评估"],
  },
  {
    id: "skill_medication_reminder",
    name: "用药提醒",
    description: "通用用药提醒技能，根据当前用药列表生成提醒计划",
    category: "通用",
    enabled: true,
    source: "builtin",
    tags: ["用药", "提醒"],
  },
  {
    id: "skill_health_education",
    name: "健康宣教",
    description: "为老年患者生成易懂的健康宣教内容，覆盖常见慢性病管理",
    category: "通用",
    enabled: true,
    source: "builtin",
    tags: ["宣教", "通用"],
  },
  {
    id: "skill_followup_questionnaire",
    name: "随访问卷生成",
    description: "根据诊疗内容自动生成个性化随访问卷",
    category: "通用",
    enabled: false,
    source: "builtin",
    tags: ["随访", "问卷"],
  },
  {
    id: "skill_risk_assessment",
    name: "风险评估",
    description: "综合评估患者健康风险，识别高风险因素并制定干预优先级",
    category: "通用",
    enabled: true,
    source: "builtin",
    tags: ["风险", "评估"],
  },
  {
    id: "skill_custom_diet_plan",
    name: "糖尿病饮食指导",
    description: "自定义技能：为糖尿病老年患者制定个性化饮食方案，含食物替换表",
    category: "自定义",
    enabled: true,
    source: "custom",
    tags: ["糖尿病", "饮食", "自定义"],
  },
];
