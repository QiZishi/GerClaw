/**
 * Mock 搜索结果数据
 * 用于 SearchResultCard 展示
 */
import type { SearchResultItem } from "@/types";

export const mockSearchResults: SearchResultItem[] = [
  {
    id: "sr_1",
    title: "中国老年高血压管理指南 2024",
    url: "https://example.com/guideline/elderly-hypertension-2024",
    source: "中华医学会老年医学分会",
    snippet:
      "老年高血压患者血压控制目标建议为 140/90 mmHg 以下，合并糖尿病或慢性肾病者可降至 130/80 mmHg。优先选择长效钙通道阻滞剂（CCB）或 ARB 类药物。",
    publishedDate: "2024-03",
  },
  {
    id: "sr_2",
    title: "老年综合评估（CGA）临床应用专家共识",
    url: "https://example.com/consensus/cga-clinical",
    source: "中华老年医学杂志",
    snippet:
      "CGA 是对老年人医学、心理、功能等多维度的综合评估，可识别老年综合征，改善老年患者功能预后和生活质量。",
    publishedDate: "2023-11",
  },
  {
    id: "sr_3",
    title: "老年患者多重用药管理策略",
    url: "https://example.com/article/polypharmacy-elderly",
    source: "中国药房",
    snippet:
      "老年人多重用药（≥5 种）增加药物不良反应风险。建议定期进行用药审查，使用 Beers 标准识别潜在不适当用药。",
    publishedDate: "2024-01",
  },
  {
    id: "sr_4",
    title: "老年跌倒风险评估与干预",
    url: "https://example.com/guide/fall-prevention",
    source: "国家卫生健康委",
    snippet:
      "65 岁以上老年人每年至少进行一次跌倒风险评估。干预措施包括平衡训练、居家环境改造、维生素 D 补充等。",
    publishedDate: "2023-08",
  },
  {
    id: "sr_5",
    title: "老年糖尿病血糖控制目标",
    url: "https://example.com/guideline/elderly-diabetes",
    source: "中国 2 型糖尿病防治指南",
    snippet:
      "老年糖尿病患者 HbA1c 控制目标应个体化：健康老年人 7.0-7.5%，合并多种慢性病者 7.5-8.0%，虚弱老年人 8.0-8.5%。",
    publishedDate: "2024-05",
  },
];
