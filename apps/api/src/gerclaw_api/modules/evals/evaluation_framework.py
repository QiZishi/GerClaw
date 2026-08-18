"""Production-ready evaluation framework with data isolation and fixtures loading.

This module enforces:
- EVAL_MODE=true environment check (prevents accidental production DB access)
- All test cases loaded from fixtures/*.json (no SQLAlchemy/HTTP dependencies)
- PHI-free synthetic data only
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from base_grader import (
    BaseGrader,
    EvalCaseInput,
    EvalCaseOutput,
    EvalCaseResult,
    EvalCaseStatus,
    GraderConfig,
    GraderResult,
    GraderType,
)


# === 环境隔离常量 ===
EVAL_MODE_ENV = "EVAL_MODE"
EVAL_MODE_EXPECTED = "true"
_USE_PRODUCTION = False  # 硬编码开关：永远不允许连接生产


class EvalEnvironmentError(RuntimeError):
    """Raised when evaluation is attempted without proper environment isolation."""


class ReportFormat(str, Enum):
    """报告格式"""
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class EvalReport:
    """评测报告"""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    eval_name: str = ""
    eval_description: str = ""
    eval_version: str = "1.0.0"

    # 评测结果
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    error_cases: int = 0
    skipped_cases: int = 0
    pass_rate: float = 0.0

    # 各评分器结果
    grader_summary: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 详细结果
    case_results: List[EvalCaseResult] = field(default_factory=list)

    # 失败清单
    failure_list: List[Dict[str, Any]] = field(default_factory=list)

    # 趋势数据
    trend_data: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


def check_eval_environment() -> None:
    """检查评测环境隔离。

    必须设置 EVAL_MODE=true 才能运行评测，防止误连生产数据库。

    Raises:
        EvalEnvironmentError: 如果环境未正确配置
    """
    eval_mode = os.environ.get(EVAL_MODE_ENV, "").lower()
    if eval_mode != EVAL_MODE_EXPECTED:
        raise EvalEnvironmentError(
            f"评测环境未正确配置。请设置环境变量 {EVAL_MODE_ENV}={EVAL_MODE_EXPECTED}。\n"
            f"当前值: '{eval_mode}'\n"
            f"这是为了防止评测代码误连生产数据库。"
        )

    if _USE_PRODUCTION:
        raise EvalEnvironmentError(
            "代码级安全开关 _USE_PRODUCTION 为 True，这是不允许的。"
        )


def load_cases_from_fixtures(
    fixtures_dir: Path,
    pattern: str = "*.json",
) -> Dict[str, List[EvalCaseInput]]:
    """从 fixtures 目录加载测试用例。

    所有用例以 JSON 格式存储，不依赖任何数据库或外部服务。

    Args:
        fixtures_dir: fixtures 目录路径
        pattern: 文件匹配模式

    Returns:
        按文件名分组的测试用例字典

    Raises:
        FileNotFoundError: 如果 fixtures 目录不存在
    """
    if not fixtures_dir.exists():
        raise FileNotFoundError(f"fixtures 目录不存在: {fixtures_dir}")

    cases_by_file: Dict[str, List[EvalCaseInput]] = {}

    for json_file in sorted(fixtures_dir.glob(pattern)):
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        cases: List[EvalCaseInput] = []
        for case_data in data.get("cases", []):
            case = EvalCaseInput(
                case_id=case_data.get("id", str(uuid.uuid4())),
                query=case_data.get("query", ""),
                context=case_data.get("context", {}),
                expected_output=case_data.get("expected_behavior"),
                conversation_history=case_data.get("conversation_history", []),
                metadata=case_data.get("metadata", {}),
            )
            cases.append(case)

        cases_by_file[json_file.stem] = cases

    return cases_by_file


class EvaluationFramework:
    """评测框架主类（生产就绪版）"""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        *,
        strict_env_check: bool = True,
    ):
        self.output_dir = output_dir
        self.graders: Dict[str, BaseGrader] = {}
        self.eval_cases: List[EvalCaseInput] = []
        self.results: List[EvalCaseResult] = []
        self.reports: List[EvalReport] = []

        # 环境隔离检查
        if strict_env_check:
            check_eval_environment()

    def register_grader(self, grader: BaseGrader):
        """注册评分器"""
        self.graders[grader.config.grader_id] = grader

    def add_eval_case(self, case: EvalCaseInput):
        """添加评测用例"""
        self.eval_cases.append(case)

    def load_fixtures(self, fixtures_dir: Path, pattern: str = "*.json"):
        """从 fixtures 目录加载测试用例"""
        cases_by_file = load_cases_from_fixtures(fixtures_dir, pattern)
        for _filename, cases in cases_by_file.items():
            self.eval_cases.extend(cases)
        return len(self.eval_cases)

    async def run_evaluation(self, eval_func: Callable[..., EvalCaseOutput]) -> EvalReport:
        """运行评测"""
        report = EvalReport(
            eval_name="GerClaw Memory Evaluation",
            eval_description="Multi-grader evaluation with data isolation",
            metadata={
                "eval_mode": os.environ.get(EVAL_MODE_ENV, "not_set"),
                "use_production": _USE_PRODUCTION,
                "fixtures_count": len(self.eval_cases),
            },
        )

        for case in self.eval_cases:
            case_result = EvalCaseResult(
                case_id=case.case_id,
                input_data=case,
            )

            try:
                output = await eval_func(case)
                case_result.output_data = output

                for grader in self.graders.values():
                    if grader.config.enabled:
                        grader_result = await grader.grade(case, output)
                        case_result.grader_results.append(grader_result)

                total_score = sum(r.score * r.max_score for r in case_result.grader_results)
                max_possible = sum(r.max_score for r in case_result.grader_results)
                case_result.total_score = total_score / max_possible if max_possible > 0 else 0
                case_result.passed = all(r.passed for r in case_result.grader_results)
                case_result.status = EvalCaseStatus.PASSED if case_result.passed else EvalCaseStatus.FAILED

            except Exception as e:
                case_result.status = EvalCaseStatus.ERROR
                case_result.error_message = str(e)

            case_result.end_time = datetime.now(UTC)
            case_result.duration_ms = (case_result.end_time - case_result.start_time).total_seconds() * 1000

            self.results.append(case_result)
            report.case_results.append(case_result)

        # 生成报告
        report.total_cases = len(self.results)
        report.passed_cases = sum(1 for r in self.results if r.passed)
        report.failed_cases = sum(1 for r in self.results if r.status == EvalCaseStatus.FAILED)
        report.error_cases = sum(1 for r in self.results if r.status == EvalCaseStatus.ERROR)
        report.pass_rate = report.passed_cases / report.total_cases if report.total_cases > 0 else 0

        # 生成各评分器摘要
        for grader_id, grader in self.graders.items():
            grader_results = [
                r for case in self.results
                for r in case.grader_results
                if r.grader_id == grader_id
            ]

            if grader_results:
                passed_count = sum(1 for r in grader_results if r.passed)
                avg_score = sum(r.score for r in grader_results) / len(grader_results)

                report.grader_summary[grader.config.name] = {
                    "grader_id": grader_id,
                    "grader_type": grader.config.grader_type.value,
                    "total_cases": len(grader_results),
                    "passed_cases": passed_count,
                    "pass_rate": passed_count / len(grader_results),
                    "average_score": avg_score,
                }

        # 生成失败清单
        report.failure_list = [
            {
                "case_id": case.case_id,
                "case_name": case.case_name if hasattr(case, 'case_name') else case.case_id,
                "error_message": case.error_message,
                "failed_graders": [
                    r.grader_name for r in case.grader_results if not r.passed
                ],
            }
            for case in self.results
            if not case.passed
        ]

        self.reports.append(report)
        return report

    def export_report(self, report: EvalReport, format: ReportFormat = ReportFormat.JSON) -> str:
        """导出报告"""
        if format == ReportFormat.JSON:
            return self._export_json(report)
        elif format == ReportFormat.MARKDOWN:
            return self._export_markdown(report)
        else:
            return self._export_json(report)

    def _export_json(self, report: EvalReport) -> str:
        """导出JSON格式"""
        report_dict = {
            "report_id": report.report_id,
            "timestamp": report.timestamp.isoformat(),
            "eval_name": report.eval_name,
            "eval_description": report.eval_description,
            "total_cases": report.total_cases,
            "passed_cases": report.passed_cases,
            "failed_cases": report.failed_cases,
            "error_cases": report.error_cases,
            "pass_rate": report.pass_rate,
            "grader_summary": report.grader_summary,
            "failure_list": report.failure_list,
            "metadata": report.metadata,
        }

        return json.dumps(report_dict, indent=2, ensure_ascii=False)

    def _export_markdown(self, report: EvalReport) -> str:
        """导出Markdown格式"""
        lines = [
            f"# {report.eval_name}",
            "",
            f"**评测时间**: {report.timestamp.isoformat()}",
            f"**评测描述**: {report.eval_description}",
            f"**环境模式**: {report.metadata.get('eval_mode', 'unknown')}",
            "",
            "## 评测概览",
            "",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 总用例数 | {report.total_cases} |",
            f"| 通过用例 | {report.passed_cases} |",
            f"| 失败用例 | {report.failed_cases} |",
            f"| 错误用例 | {report.error_cases} |",
            f"| **通过率** | **{report.pass_rate:.2%}** |",
            "",
            "## 评分器摘要",
            "",
            "| 评分器 | 类型 | 通过率 | 平均分 |",
            "|--------|------|--------|--------|",
        ]

        for grader_name, summary in report.grader_summary.items():
            lines.append(
                f"| {grader_name} | {summary['grader_type']} | {summary['pass_rate']:.2%} | {summary['average_score']:.4f} |"
            )

        if report.failure_list:
            lines.extend([
                "",
                "## 失败清单",
                "",
                "| 用例ID | 失败评分器 | 错误信息 |",
                "|--------|-----------|----------|",
            ])

            for failure in report.failure_list:
                failed_graders = ", ".join(failure['failed_graders'])
                error_msg = failure.get('error_message', 'N/A') or 'N/A'
                lines.append(
                    f"| {failure['case_id']} | {failed_graders} | {error_msg} |"
                )

        lines.extend([
            "",
            "---",
            f"*报告生成时间: {datetime.now(UTC).isoformat()}*",
        ])

        return "\n".join(lines)