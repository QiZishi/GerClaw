/**
 * Mock 医生端患者列表数据
 * 对齐 gerclaw设计要求.md §3.2.2 医生端 / 角色切换.md §4.1 mockPatients
 */

export interface MockPatient {
  id: string;
  name: string;
  age: number;
  gender: "男" | "女";
  chiefComplaint: string;
  conditions: string[];
  currentMedications: string[];
  recentCgaScore?: number;
  status: "待评估" | "评估中" | "已完成";
  lastVisit: string;
}

export const mockPatients: MockPatient[] = [
  {
    id: "p001",
    name: "张桂芳",
    age: 78,
    gender: "女",
    chiefComplaint: "血压偏高伴头晕乏力 1 月余",
    conditions: ["高血压", "2 型糖尿病", "轻度认知障碍"],
    currentMedications: ["氨氯地平 5mg qd", "二甲双胍 0.5g bid", "阿托伐他汀 20mg qn"],
    recentCgaScore: 65,
    status: "评估中",
    lastVisit: "2026-07-01",
  },
  {
    id: "p002",
    name: "李建国",
    age: 72,
    gender: "男",
    chiefComplaint: "胸闷气短，活动后加重 2 周",
    conditions: ["冠心病", "高脂血症"],
    currentMedications: ["阿司匹林 100mg qd", "瑞舒伐他汀 10mg qn", "美托洛尔 25mg bid"],
    recentCgaScore: 78,
    status: "已完成",
    lastVisit: "2026-06-28",
  },
  {
    id: "p003",
    name: "王秀兰",
    age: 81,
    gender: "女",
    chiefComplaint: "近 3 月多次跌倒，伴记忆力下降",
    conditions: ["骨质疏松", "阿尔茨海默病早期", "高血压"],
    currentMedications: ["阿仑膦酸钠 70mg qw", "碳酸钙 D3 1片 qd", "缬沙坦 80mg qd"],
    recentCgaScore: 52,
    status: "评估中",
    lastVisit: "2026-06-25",
  },
  {
    id: "p004",
    name: "赵德顺",
    age: 68,
    gender: "男",
    chiefComplaint: "糖尿病随访，血糖控制良好",
    conditions: ["2 型糖尿病（控制良好）"],
    currentMedications: ["二甲双胍 0.5g bid", "格列美脲 2mg qd"],
    recentCgaScore: 88,
    status: "已完成",
    lastVisit: "2026-07-02",
  },
  {
    id: "p005",
    name: "陈美珍",
    age: 75,
    gender: "女",
    chiefComplaint: "睡眠障碍伴焦虑 2 月",
    conditions: ["骨关节炎", "睡眠障碍", "焦虑状态"],
    currentMedications: ["艾司西酞普兰 5mg qd", "唑吡坦 5mg qn", "塞来昔布 200mg qd"],
    recentCgaScore: 70,
    status: "待评估",
    lastVisit: "2026-06-30",
  },
  {
    id: "p006",
    name: "孙志强",
    age: 70,
    gender: "男",
    chiefComplaint: "慢性咳嗽伴活动后气促",
    conditions: ["慢阻肺", "前列腺增生"],
    currentMedications: ["沙美特罗替卡松 1吸 bid", "坦索罗辛 0.2mg qn"],
    recentCgaScore: 75,
    status: "待评估",
    lastVisit: "2026-06-20",
  },
  {
    id: "p007",
    name: "刘桂英",
    age: 83,
    gender: "女",
    chiefComplaint: "脑梗后吞咽困难，体重下降",
    conditions: ["脑梗死后遗症", "吞咽困难", "营养不良风险"],
    currentMedications: ["阿司匹林 100mg qd", "阿托伐他汀 40mg qn", "多潘立酮 10mg tid"],
    recentCgaScore: 45,
    status: "评估中",
    lastVisit: "2026-07-03",
  },
  {
    id: "p008",
    name: "周文斌",
    age: 65,
    gender: "男",
    chiefComplaint: "健康体检，无不适",
    conditions: ["高血压前期"],
    currentMedications: [],
    recentCgaScore: 92,
    status: "已完成",
    lastVisit: "2026-06-15",
  },
];
