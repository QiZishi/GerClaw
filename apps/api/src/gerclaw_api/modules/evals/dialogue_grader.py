"""Dialogue grader for evaluation framework."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from base_grader import BaseGrader, EvalCaseInput, EvalCaseOutput, GraderConfig, GraderResult, GraderType


class DialogueGrader(BaseGrader):
    """对话评分器"""
    
    def __init__(self, config: GraderConfig):
        super().__init__(config)
        self.config.grader_type = GraderType.DIALOGUE
        
        # 对话配置
        self.consistency_threshold = config.config_params.get("consistency_threshold", 0.8)
        self.follow_up_threshold = config.config_params.get("follow_up_threshold", 0.7)
    
    async def grade(self, input_data: EvalCaseInput, output_data: EvalCaseOutput) -> GraderResult:
        """对话评分"""
        errors = []
        warnings = []
        score = 1.0
        passed = True
        
        # 1. 多轮一致性检查
        consistency_result = {"inconsistencies": [], "historical_facts_count": 0}
        if input_data.conversation_history:
            consistency_result = self._check_consistency(
                output_data.response,
                input_data.conversation_history
            )
            if consistency_result["inconsistencies"]:
                errors.extend([f"不一致: {inc}" for inc in consistency_result["inconsistencies"]])
                score -= 0.2 * len(consistency_result["inconsistencies"])
                passed = False
        
        # 2. 追问完整性检查
        follow_up_result = self._check_follow_up完整性(output_data.response, input_data.query)
        if not follow_up_result["is_complete"]:
            warnings.append(f"追问不完整: {follow_up_result['missing_aspects']}")
            score -= 0.1
        
        score = max(0.0, score)
        
        return self._create_result(
            passed=passed,
            score=score,
            details={
                "errors": errors,
                "warnings": warnings,
                "consistency_check": consistency_result if input_data.conversation_history else None,
                "follow_up_check": follow_up_result,
            }
        )
    
    def _extract_keywords(self, text: str) -> Set[str]:
        """提取关键词（改进的中文分词）"""
        keywords = set()
        
        # 提取2-4字的中文词组
        for length in range(2, 5):
            for i in range(len(text) - length + 1):
                word = text[i:i+length]
                if re.match(r'^[\u4e00-\u9fa5]+$', word):
                    keywords.add(word)
        
        return keywords
    
    def _check_consistency(self, response: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """检查多轮一致性"""
        inconsistencies = []
        
        # 提取历史中的关键信息
        historical_facts = []
        for turn in history:
            if turn.get("role") == "assistant":
                facts = [s.strip() for s in turn.get("content", "").split("。") if s.strip()]
                historical_facts.extend(facts)
        
        # 检查当前响应是否与历史一致
        current_facts = [s.strip() for s in response.split("。") if s.strip()]
        
        for fact in current_facts:
            for historical_fact in historical_facts:
                if self._is_contradictory(fact, historical_fact):
                    inconsistencies.append(f"当前: {fact[:30]} 与历史: {historical_fact[:30]} 矛盾")
        
        return {
            "inconsistencies": inconsistencies,
            "historical_facts_count": len(historical_facts),
        }
    
    def _is_contradictory(self, fact1: str, fact2: str) -> bool:
        """检查是否矛盾（改进的中文分词匹配）"""
        # 否定词列表
        negation_words = ["没有", "不", "无", "未", "非", "否认", "从未"]
        
        # 检查否定状态
        has_negation1 = any(word in fact1 for word in negation_words)
        has_negation2 = any(word in fact2 for word in negation_words)
        
        # 如果否定状态相同，不是矛盾
        if has_negation1 == has_negation2:
            return False
        
        # 提取关键词进行匹配
        keywords1 = self._extract_keywords(fact1)
        keywords2 = self._extract_keywords(fact2)
        
        # 计算关键词重叠
        overlap = keywords1 & keywords2
        
        # 过滤掉否定词本身
        overlap = {w for w in overlap if w not in negation_words}
        
        # 如果有足够的关键词重叠（至少2个）且否定状态不同，认为是矛盾
        if len(overlap) >= 2:
            return True
        
        # 检查核心实体是否匹配（如疾病、药物等）
        medical_entities = ["高血压", "糖尿病", "冠心病", "过敏", "手术", "住院"]
        entity1 = {e for e in medical_entities if e in fact1}
        entity2 = {e for e in medical_entities if e in fact2}
        
        # 如果核心实体匹配且否定状态不同，认为是矛盾
        if entity1 & entity2 and has_negation1 != has_negation2:
            return True
        
        return False
    
    def _check_follow_up完整性(self, response: str, query: str) -> Dict[str, Any]:
        """检查追问完整性"""
        aspects = self._extract_aspects(query)
        
        covered_aspects = []
        missing_aspects = []
        
        for aspect in aspects:
            if aspect in response:
                covered_aspects.append(aspect)
            else:
                missing_aspects.append(aspect)
        
        is_complete = len(missing_aspects) == 0
        
        return {
            "is_complete": is_complete,
            "covered_aspects": covered_aspects,
            "missing_aspects": missing_aspects,
            "coverage_ratio": len(covered_aspects) / len(aspects) if aspects else 1.0,
        }
    
    def _extract_aspects(self, query: str) -> List[str]:
        """提取查询的各个方面"""
        aspects = []
        
        question_words = ["什么", "如何", "为什么", "怎么", "哪些", "是否", "能否"]
        for word in question_words:
            if word in query:
                aspects.append(word)
        
        return aspects if aspects else ["general"]