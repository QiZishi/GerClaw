"""Evidence grader for evaluation framework."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from base_grader import BaseGrader, EvalCaseInput, EvalCaseOutput, GraderConfig, GraderResult, GraderType


class EvidenceGrader(BaseGrader):
    """证据评分器"""
    
    def __init__(self, config: GraderConfig):
        super().__init__(config)
        self.config.grader_type = GraderType.EVIDENCE
        
        # 证据配置
        self.evidence_sources = config.config_params.get("evidence_sources", [])
        self.claim_threshold = config.config_params.get("claim_threshold", 0.7)
    
    async def grade(self, input_data: EvalCaseInput, output_data: EvalCaseOutput) -> GraderResult:
        """证据评分"""
        errors = []
        warnings = []
        score = 1.0
        passed = True
        
        # 1. 引用存在性检查
        citation_result = self._check_citations(output_data.response)
        if not citation_result["has_citations"]:
            warnings.append("回答中未包含引用")
            score -= 0.1
        
        # 2. Claim-证据匹配检查
        claim_result = self._check_claim_evidence_match(
            output_data.response, 
            input_data.context.get("evidence", [])
        )
        if claim_result["unsupported_claims"]:
            errors.append(f"无证据支持的声明: {claim_result['unsupported_claims']}")
            score -= 0.3 * len(claim_result["unsupported_claims"])
            passed = False
        
        # 3. 无依据结论检测
        conclusion_result = self._check_unsupported_conclusions(output_data.response)
        if conclusion_result["has_unsupported"]:
            errors.append(f"无依据结论: {conclusion_result['conclusions']}")
            score -= 0.2
            passed = False
        
        score = max(0.0, score)
        
        return self._create_result(
            passed=passed,
            score=score,
            details={
                "errors": errors,
                "warnings": warnings,
                "citation_check": citation_result,
                "claim_check": claim_result,
                "conclusion_check": conclusion_result,
            }
        )
    
    def _extract_chinese_keywords(self, text: str) -> Set[str]:
        """提取中文关键词（2-4字的词组）"""
        keywords = set()
        # 提取2-4字的中文词组
        for length in range(2, 5):
            for i in range(len(text) - length + 1):
                word = text[i:i+length]
                # 过滤掉纯标点或无意义的词
                if re.match(r'^[\u4e00-\u9fa5]+$', word):
                    keywords.add(word)
        return keywords
    
    def _check_citations(self, response: str) -> Dict[str, Any]:
        """检查引用存在性"""
        citation_patterns = [
            r"\[\d+\]",  # [1], [2] 等
            r"根据.*研究",
            r"参考.*文献",
            r"来源[：:]",
            r"研究表明",
            r"文献报道",
            r"指南推荐",
        ]
        
        citations = []
        for pattern in citation_patterns:
            matches = re.findall(pattern, response)
            citations.extend(matches)
        
        return {
            "has_citations": len(citations) > 0,
            "citations": citations,
            "citation_count": len(citations),
        }
    
    def _check_claim_evidence_match(self, response: str, evidence: List[str]) -> Dict[str, Any]:
        """检查声明-证据匹配"""
        unsupported_claims = []
        
        # 按句号分割声明
        claims = [s.strip() for s in response.split("。") if s.strip()]
        
        for claim in claims:
            # 检查声明是否有证据支持
            has_evidence = any(
                self._claim_matches_evidence(claim, ev)
                for ev in evidence
            )
            
            # 如果是医学声明但没有证据，标记为无支持
            if self._is_medical_claim(claim) and not has_evidence:
                unsupported_claims.append(claim[:50])
        
        return {
            "unsupported_claims": unsupported_claims,
            "total_claims": len(claims),
            "supported_claims": len(claims) - len(unsupported_claims),
        }
    
    def _claim_matches_evidence(self, claim: str, evidence: str) -> bool:
        """检查声明是否与证据匹配（改进的中文分词匹配）"""
        # 方法1：直接子串匹配
        if evidence in claim or claim in evidence:
            return True
        
        # 方法2：提取关键词并检查重叠
        claim_keywords = self._extract_chinese_keywords(claim)
        evidence_keywords = self._extract_chinese_keywords(evidence)
        
        # 计算关键词重叠
        overlap = claim_keywords & evidence_keywords
        
        # 如果有2个以上的关键词重叠，认为匹配
        if len(overlap) >= 2:
            return True
        
        # 方法3：检查核心医学术语是否匹配
        medical_terms = ["治疗", "服药", "药物", "症状", "诊断", "疾病", "患者", "血压", "血糖"]
        claim_medical = [term for term in medical_terms if term in claim]
        evidence_medical = [term for term in medical_terms if term in evidence]
        
        # 如果都有医学术语且有重叠，认为匹配
        if claim_medical and evidence_medical:
            medical_overlap = set(claim_medical) & set(evidence_medical)
            if medical_overlap:
                return True
        
        return False
    
    def _is_medical_claim(self, claim: str) -> bool:
        """检查是否为医学声明"""
        medical_keywords = [
            "治疗", "药物", "症状", "诊断", "疾病", "患者",
            "服药", "用药", "血压", "血糖", "心率", "体温",
            "过敏", "手术", "住院", "检查", "化验"
        ]
        return any(keyword in claim for keyword in medical_keywords)
    
    def _check_unsupported_conclusions(self, response: str) -> Dict[str, Any]:
        """检查无依据结论"""
        overconfident_patterns = [
            "一定是",
            "肯定是",
            "绝对是",
            "毫无疑问",
            "100%",
            "完全治愈",
            "根治",
            "特效药",
        ]
        
        conclusions = []
        for pattern in overconfident_patterns:
            if pattern in response:
                conclusions.append(pattern)
        
        return {
            "has_unsupported": len(conclusions) > 0,
            "conclusions": conclusions,
        }