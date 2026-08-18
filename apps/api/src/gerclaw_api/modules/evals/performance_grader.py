"""Performance grader for evaluation framework."""

from __future__ import annotations

from typing import Any, Dict

from base_grader import BaseGrader, EvalCaseInput, EvalCaseOutput, GraderConfig, GraderResult, GraderType


class PerformanceGrader(BaseGrader):
    """性能评分器"""
    
    def __init__(self, config: GraderConfig):
        super().__init__(config)
        self.config.grader_type = GraderType.PERFORMANCE
        
        # 性能阈值
        self.max_latency_ms = config.config_params.get("max_latency_ms", 5000)
        self.max_token_count = config.config_params.get("max_token_count", 1000)
        self.max_token_cost = config.config_params.get("max_token_cost", 0.1)
        self.max_sse_timeout = config.config_params.get("max_sse_timeout", 3)
    
    async def grade(self, input_data: EvalCaseInput, output_data: EvalCaseOutput) -> GraderResult:
        """性能评分"""
        errors = []
        warnings = []
        score = 1.0
        passed = True
        
        # 1. 延迟检查
        if output_data.latency_ms > self.max_latency_ms:
            errors.append(f"延迟过高: {output_data.latency_ms}ms > {self.max_latency_ms}ms")
            score -= 0.3
            passed = False
        elif output_data.latency_ms > self.max_latency_ms * 0.8:
            warnings.append(f"延迟较高: {output_data.latency_ms}ms")
            score -= 0.1
        
        # 2. Token成本检查
        if output_data.token_count > self.max_token_count:
            errors.append(f"Token数量过多: {output_data.token_count} > {self.max_token_count}")
            score -= 0.2
            passed = False
        
        if output_data.token_cost > self.max_token_cost:
            errors.append(f"Token成本过高: {output_data.token_cost} > {self.max_token_cost}")
            score -= 0.2
            passed = False
        
        # 3. SSE心跳与超时检查
        if output_data.sse_timeout_count > self.max_sse_timeout:
            errors.append(f"SSE超时次数过多: {output_data.sse_timeout_count} > {self.max_sse_timeout}")
            score -= 0.2
            passed = False
        
        score = max(0.0, score)
        
        return self._create_result(
            passed=passed,
            score=score,
            details={
                "errors": errors,
                "warnings": warnings,
                "latency_ms": output_data.latency_ms,
                "token_count": output_data.token_count,
                "token_cost": output_data.token_cost,
                "sse_timeout_count": output_data.sse_timeout_count,
            }
        )
