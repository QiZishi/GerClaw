"""Medical grader for evaluation framework."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from base_grader import BaseGrader, EvalCaseInput, EvalCaseOutput, GraderConfig, GraderResult, GraderType


class MedicalGrader(BaseGrader):
    """医学评分器"""
    
    def __init__(self, config: GraderConfig):
        super().__init__(config)
        self.config.grader_type = GraderType.MEDICAL
        
        # 医学配置
        self.guidelines = config.config_params.get("guidelines", [])
        self.drug_interactions = config.config_params.get("drug_interactions", {})
        self.contraindications = config.config_params.get("contraindications", {})
    
    async def grade(self, input_data: EvalCaseInput, output_data: EvalCaseOutput) -> GraderResult:
        """医学评分"""
        errors = []
        warnings = []
        score = 1.0
        passed = True
        
        # 1. 处方合理性检查
        prescription_result = self._check_prescription合理性(output_data.response)
        if prescription_result["issues"]:
            # 只有严重问题才扣分和标记失败
            serious_issues = [i for i in prescription_result["issues"] if "禁忌" in i or "相互作用" in i]
            minor_issues = [i for i in prescription_result["issues"] if i not in serious_issues]
            
            if serious_issues:
                errors.extend([f"处方问题: {issue}" for issue in serious_issues])
                score -= 0.3 * len(serious_issues)
                passed = False
            
            if minor_issues:
                warnings.extend([f"处方建议: {issue}" for issue in minor_issues])
                score -= 0.05 * len(minor_issues)  # 小问题只扣少量分
        
        # 2. 药物相互作用检查
        interaction_result = self._check_drug_interactions(output_data.response)
        if interaction_result["interactions"]:
            warnings.extend([f"药物相互作用: {interaction}" for interaction in interaction_result["interactions"]])
            score -= 0.1 * len(interaction_result["interactions"])
        
        # 3. 禁忌症检查
        contraindication_result = self._check_contraindications(output_data.response, input_data.context)
        if contraindication_result["violations"]:
            errors.extend([f"禁忌症违规: {v}" for v in contraindication_result["violations"]])
            score -= 0.4 * len(contraindication_result["violations"])
            passed = False
        
        score = max(0.0, score)
        
        return self._create_result(
            passed=passed,
            score=score,
            details={
                "errors": errors,
                "warnings": warnings,
                "prescription_check": prescription_result,
                "interaction_check": interaction_result,
                "contraindication_check": contraindication_result,
            }
        )
    
    def _check_prescription合理性(self, response: str) -> Dict[str, Any]:
        """检查处方合理性（放宽要求）"""
        issues = []
        
        # 检查是否给出具体处方
        prescription_patterns = [
            r"处方[：:]",
            r"开.*药",
            r"服用.*(?:mg|ml|g|片|粒)",
            r"(?:每日|每天).*(?:次|服用)",
            r"口服",
        ]
        
        has_prescription = any(re.search(pattern, response) for pattern in prescription_patterns)
        
        if has_prescription:
            # 检查是否包含关键信息（放宽：只需要有剂量或频次之一即可）
            has_dosage = bool(re.search(r'\d+\s*(?:mg|ml|g|片|粒)', response))
            has_frequency = bool(re.search(r'(?:每日|每天|一日|一次|两次|三次)', response))
            has_duration = bool(re.search(r'(?:疗程|天|周|月|连续)', response))
            
            # 计算信息完整度
            info_count = sum([has_dosage, has_frequency, has_duration])
            
            if info_count == 0:
                issues.append("处方缺少剂量和频次信息")
            elif info_count == 1:
                # 只有1项信息，给出建议但不扣太多分
                missing = []
                if not has_dosage:
                    missing.append("剂量")
                if not has_frequency:
                    missing.append("频次")
                if not has_duration:
                    missing.append("疗程")
                issues.append(f"处方建议补充{', '.join(missing)}信息")
            
            # 检查是否建议咨询医生
            has_doctor_advice = any(
                phrase in response
                for phrase in ["咨询医生", "遵医嘱", "在医生指导下", "请咨询医生", "医生建议"]
            )
            
            if not has_doctor_advice:
                issues.append("建议咨询医生")
        
        return {
            "has_prescription": has_prescription,
            "issues": issues,
        }
    
    def _check_drug_interactions(self, response: str) -> Dict[str, Any]:
        """检查药物相互作用"""
        interactions = []
        
        mentioned_drugs = []
        for drug in self.drug_interactions.keys():
            if drug in response:
                mentioned_drugs.append(drug)
        
        for i, drug1 in enumerate(mentioned_drugs):
            for drug2 in mentioned_drugs[i+1:]:
                if drug2 in self.drug_interactions.get(drug1, []):
                    interactions.append(f"{drug1}与{drug2}存在相互作用")
        
        return {
            "interactions": interactions,
            "mentioned_drugs": mentioned_drugs,
        }
    
    def _check_contraindications(self, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """检查禁忌症"""
        violations = []
        
        patient_conditions = context.get("patient_conditions", [])
        
        for drug, contraindications in self.contraindications.items():
            if drug in response:
                for condition in patient_conditions:
                    if condition in contraindications:
                        violations.append(f"{drug}禁用于{condition}")
        
        return {
            "violations": violations,
        }