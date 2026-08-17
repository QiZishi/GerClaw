"""Retrieval and compression evaluation framework for memory module."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional



class EvalMetricType(str, Enum):
    """评估指标类型"""
    COMPRESSION_RATIO = "compression_ratio"
    MEDICAL_INFO_RETENTION = "medical_info_retention"
    RETRIEVAL_ACCURACY = "retrieval_accuracy"
    RETRIEVAL_RECALL = "retrieval_recall"
    RETRIEVAL_PRECISION = "retrieval_precision"
    FALLBACK_USAGE = "fallback_usage"
    USER_SATISFACTION = "user_satisfaction"
    PROCESSING_TIME = "processing_time"


class EvalCaseStatus(str, Enum):
    """测试用例状态"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class EvalCase:
    """评估用例"""
    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    status: EvalCaseStatus = EvalCaseStatus.PENDING

    # 输入数据
    input_data: Dict[str, Any] = field(default_factory=dict)

    # 预期输出
    expected_output: Dict[str, Any] = field(default_factory=dict)

    # 实际输出
    actual_output: Dict[str, Any] = field(default_factory=dict)

    # 评估指标
    metrics: Dict[str, float] = field(default_factory=dict)

    # 时间信息
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 错误信息
    error_message: Optional[str] = None


@dataclass
class CompressionEvalCase(EvalCase):
    """压缩评估用例"""
    # 原始文本
    original_text: str = ""

    # 预期压缩结果
    expected_compressed_text: str = ""
    expected_compression_ratio: float = 0.0
    expected_medical_fields_retained: List[str] = field(default_factory=list)

    # 实际压缩结果
    actual_compressed_text: str = ""
    actual_compression_ratio: float = 0.0
    actual_medical_fields_retained: List[str] = field(default_factory=list)


@dataclass
class RetrievalEvalCase(EvalCase):
    """检索评估用例"""
    # 查询
    query: str = ""
    query_embedding: List[float] = field(default_factory=list)

    # 预期检索结果
    expected_result_ids: List[str] = field(default_factory=list)
    expected_relevant_count: int = 0

    # 实际检索结果
    actual_result_ids: List[str] = field(default_factory=list)
    actual_relevant_count: int = 0

    # 检索参数
    top_k: int = 10
    similarity_threshold: float = 0.7


@dataclass
class EvalResult:
    """评估结果"""
    eval_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # 评估类型
    eval_type: str = ""

    # 用例结果
    cases: List[EvalCase] = field(default_factory=list)

    # 汇总指标
    summary_metrics: Dict[str, float] = field(default_factory=dict)

    # 统计信息
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    skipped_cases: int = 0

    # 配置信息
    config_snapshot: Dict[str, Any] = field(default_factory=dict)


class MemoryEvalFramework:
    """内存评估框架"""

    def __init__(self, output_dir: Optional[Path] = None):
        self._output_dir = output_dir
        self._eval_results: List[EvalResult] = []
        self._eval_cases: Dict[str, List[EvalCase]] = {
            "compression": [],
            "retrieval": [],
        }

    def add_compression_eval_case(self, case: CompressionEvalCase):
        """添加压缩评估用例"""
        self._eval_cases["compression"].append(case)

    def add_retrieval_eval_case(self, case: RetrievalEvalCase):
        """添加检索评估用例"""
        self._eval_cases["retrieval"].append(case)

    def run_compression_eval(self,
                            compress_func: Callable[..., str],
                            config: Dict[str, Any]) -> EvalResult:
        """运行压缩评估"""
        result = EvalResult(eval_type="compression")
        result.config_snapshot = config

        for case in self._eval_cases["compression"]:
            case.status = EvalCaseStatus.RUNNING
            case.started_at = datetime.now(UTC)

            try:
                # 执行压缩
                compressed_text = compress_func(case.original_text, **config)

                # 计算压缩率
                original_len = len(case.original_text)
                compressed_len = len(compressed_text)
                compression_ratio = 1 - (compressed_len / original_len) if original_len > 0 else 0

                # 检查医学字段保留
                retained_fields = self._check_medical_fields_retained(
                    case.original_text, compressed_text
                )

                # 更新用例结果
                case.actual_compressed_text = compressed_text
                case.actual_compression_ratio = compression_ratio
                case.actual_medical_fields_retained = retained_fields

                # 计算指标
                case.metrics = {
                    "compression_ratio": compression_ratio,
                    "medical_fields_retained_count": len(retained_fields),
                    "expected_medical_fields_count": len(case.expected_medical_fields_retained),
                }

                # 检查是否通过
                if self._check_compression_case_passed(case):
                    case.status = EvalCaseStatus.PASSED
                    result.passed_cases += 1
                else:
                    case.status = EvalCaseStatus.FAILED
                    result.failed_cases += 1

            except Exception as e:
                case.status = EvalCaseStatus.FAILED
                case.error_message = str(e)
                result.failed_cases += 1

            case.completed_at = datetime.now(UTC)
            result.cases.append(case)
            result.total_cases += 1

        # 计算汇总指标
        result.summary_metrics = self._calculate_summary_metrics(result.cases)

        self._eval_results.append(result)
        return result

    def run_retrieval_eval(self,
                          retrieve_func: Callable[..., List[str]],
                          config: Dict[str, Any]) -> EvalResult:
        """运行检索评估"""
        result = EvalResult(eval_type="retrieval")
        result.config_snapshot = config

        for case in self._eval_cases["retrieval"]:
            case.status = EvalCaseStatus.RUNNING
            case.started_at = datetime.now(UTC)

            try:
                # 执行检索
                result_ids = retrieve_func(
                    case.query_embedding,
                    top_k=case.top_k,
                    similarity_threshold=case.similarity_threshold,
                    **config
                )

                # 计算检索指标
                relevant_retrieved = set(result_ids) & set(case.expected_result_ids)
                precision = len(relevant_retrieved) / len(result_ids) if result_ids else 0
                recall = len(relevant_retrieved) / len(case.expected_result_ids) if case.expected_result_ids else 0
                f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

                # 更新用例结果
                case.actual_result_ids = result_ids
                case.actual_relevant_count = len(relevant_retrieved)

                # 计算指标
                case.metrics = {
                    "precision": precision,
                    "recall": recall,
                    "f1_score": f1,
                    "retrieved_count": len(result_ids),
                    "relevant_count": len(case.expected_result_ids),
                }

                # 检查是否通过
                if self._check_retrieval_case_passed(case):
                    case.status = EvalCaseStatus.PASSED
                    result.passed_cases += 1
                else:
                    case.status = EvalCaseStatus.FAILED
                    result.failed_cases += 1

            except Exception as e:
                case.status = EvalCaseStatus.FAILED
                case.error_message = str(e)
                result.failed_cases += 1

            case.completed_at = datetime.now(UTC)
            result.cases.append(case)
            result.total_cases += 1

        # 计算汇总指标
        result.summary_metrics = self._calculate_summary_metrics(result.cases)

        self._eval_results.append(result)
        return result

    def _check_medical_fields_retained(self, original: str, compressed: str) -> List[str]:
        """检查医学字段保留情况"""
        medical_patterns = {
            "allergy": r"过敏|不耐受|不良反应",
            "medication": r"药|服药|用药|剂量",
            "vital_sign": r"血压|血糖|心率|体温",
            "red_flag": r"胸痛|呼吸困难|意识模糊|出血",
            "diagnosis": r"诊断|确诊|疾病",
            "procedure": r"手术|操作",
            "hospitalization": r"住院|入院|出院",
            "chronic_disease": r"高血压|糖尿病|冠心病",
        }

        retained = []
        import re
        for field_name, pattern in medical_patterns.items():
            if re.search(pattern, original) and re.search(pattern, compressed):
                retained.append(field_name)

        return retained

    def _check_compression_case_passed(self, case: CompressionEvalCase) -> bool:
        """检查压缩用例是否通过"""
        # 检查压缩率是否在合理范围内
        if case.actual_compression_ratio < 0.1:  # 压缩率太低
            return False

        # 检查关键医学字段是否保留
        expected_critical = {"allergy", "medication", "vital_sign", "red_flag"}
        actual_retained = set(case.actual_medical_fields_retained)
        original_fields = set(case.expected_medical_fields_retained)

        # 关键字段必须保留
        critical_in_original = original_fields & expected_critical
        critical_retained = critical_in_original & actual_retained

        if critical_in_original and len(critical_retained) < len(critical_in_original) * 0.8:
            return False

        return True

    def _check_retrieval_case_passed(self, case: RetrievalEvalCase) -> bool:
        """检查检索用例是否通过"""
        # 检查召回率
        if case.expected_result_ids:
            recall = case.actual_relevant_count / len(case.expected_result_ids)
            if recall < 0.5:  # 召回率低于50%
                return False

        return True

    def _calculate_summary_metrics(self, cases: List[EvalCase]) -> Dict[str, float]:
        """计算汇总指标"""
        if not cases:
            return {}

        # 收集所有指标
        all_metrics: Dict[str, List[float]] = {}
        for case in cases:
            for metric_name, metric_value in case.metrics.items():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(metric_value)

        # 计算平均值
        summary = {}
        for metric_name, values in all_metrics.items():
            if values:
                summary[f"avg_{metric_name}"] = sum(values) / len(values)
                summary[f"min_{metric_name}"] = min(values)
                summary[f"max_{metric_name}"] = max(values)

        # 添加通过率
        passed_count = sum(1 for c in cases if c.status == EvalCaseStatus.PASSED)
        summary["pass_rate"] = passed_count / len(cases) if cases else 0

        return summary

    def get_eval_results(self, eval_type: Optional[str] = None) -> List[EvalResult]:
        """获取评估结果"""
        if eval_type:
            return [r for r in self._eval_results if r.eval_type == eval_type]
        return self._eval_results

    def export_results(self, output_path: Optional[Path] = None):
        """导出评估结果"""
        export_path = output_path or self._output_dir
        if not export_path:
            return

        export_path.mkdir(parents=True, exist_ok=True)

        for result in self._eval_results:
            filename = f"eval_{result.eval_type}_{result.eval_id}.json"
            filepath = export_path / filename

            data = {
                "eval_id": result.eval_id,
                "eval_type": result.eval_type,
                "timestamp": result.timestamp.isoformat(),
                "summary_metrics": result.summary_metrics,
                "total_cases": result.total_cases,
                "passed_cases": result.passed_cases,
                "failed_cases": result.failed_cases,
                "config_snapshot": result.config_snapshot,
                "cases": [
                    {
                        "case_id": case.case_id,
                        "name": case.name,
                        "status": case.status.value,
                        "metrics": case.metrics,
                        "error_message": case.error_message,
                    }
                    for case in result.cases
                ],
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def generate_report(self) -> str:
        """生成评估报告"""
        if not self._eval_results:
            return "No evaluation results available."

        report_lines = ["# Memory Module Evaluation Report", ""]

        for result in self._eval_results:
            report_lines.append(f"## {result.eval_type.capitalize()} Evaluation")
            report_lines.append(f"- **Eval ID**: {result.eval_id}")
            report_lines.append(f"- **Timestamp**: {result.timestamp.isoformat()}")
            report_lines.append(f"- **Total Cases**: {result.total_cases}")
            report_lines.append(f"- **Passed**: {result.passed_cases}")
            report_lines.append(f"- **Failed**: {result.failed_cases}")
            report_lines.append(f"- **Pass Rate**: {result.summary_metrics.get('pass_rate', 0):.2%}")
            report_lines.append("")

            report_lines.append("### Summary Metrics")
            for metric_name, metric_value in result.summary_metrics.items():
                if metric_name != "pass_rate":
                    report_lines.append(f"- **{metric_name}**: {metric_value:.4f}")
            report_lines.append("")

            if result.failed_cases > 0:
                report_lines.append("### Failed Cases")
                for case in result.cases:
                    if case.status == EvalCaseStatus.FAILED:
                        report_lines.append(f"- **{case.name}**: {case.error_message or 'Unknown error'}")
                report_lines.append("")

        return "\n".join(report_lines)


# 预定义的压缩评估用例
COMPRESSION_EVAL_CASES = [
    CompressionEvalCase(
        case_id="compression.medical_fields_retention",
        name="医学字段保留测试",
        description="验证压缩后关键医学字段是否保留",
        original_text="患者对青霉素过敏，目前服用二甲双胍500mg每日两次，血压140/90mmHg，有高血压病史5年。",
        expected_compression_ratio=0.3,
        expected_medical_fields_retained=["allergy", "medication", "vital_sign", "chronic_disease"],
    ),
    CompressionEvalCase(
        case_id="compression.critical_fields_priority",
        name="关键字段优先级测试",
        description="验证过敏史和红旗事件是否优先保留",
        original_text="患者昨天因胸痛急诊，有青霉素过敏史，最近睡眠不好，喜欢运动。",
        expected_compression_ratio=0.4,
        expected_medical_fields_retained=["red_flag", "allergy"],
    ),
    CompressionEvalCase(
        case_id="compression.time_decay",
        name="时间衰减测试",
        description="验证时间衰减是否正常工作",
        original_text="一周前血压120/80，三天前血压130/85，今天血压140/90。",
        expected_compression_ratio=0.2,
        expected_medical_fields_retained=["vital_sign"],
    ),
]

# 预定义的检索评估用例
RETRIEVAL_EVAL_CASES = [
    RetrievalEvalCase(
        case_id="retrieval.medical_query",
        name="医学查询检索测试",
        description="验证医学相关查询的检索准确性",
        query="患者过敏史",
        expected_result_ids=["fact_1", "fact_2"],
        expected_relevant_count=2,
        top_k=10,
        similarity_threshold=0.7,
    ),
    RetrievalEvalCase(
        case_id="retrieval.time_sensitive",
        name="时间敏感查询测试",
        description="验证时间敏感查询的检索效果",
        query="最近血压记录",
        expected_result_ids=["fact_3", "fact_4", "fact_5"],
        expected_relevant_count=3,
        top_k=10,
        similarity_threshold=0.6,
    ),
    RetrievalEvalCase(
        case_id="retrieval.fallback_strategy",
        name="降级策略测试",
        description="验证降级策略是否正常工作",
        query="未知疾病症状",
        expected_result_ids=[],
        expected_relevant_count=0,
        top_k=5,
        similarity_threshold=0.8,
    ),
]
