"""CLI entry point for GerClaw evaluation framework.

Usage:
    python -m gerclaw_api.modules.evals.run_eval [options]

Environment Requirements:
    EVAL_MODE=true must be set to prevent accidental production DB access.

Examples:
    # Run all grader evaluations
    EVAL_MODE=true python -m gerclaw_api.modules.evals.run_eval

    # Run specific grader only
    EVAL_MODE=true python -m gerclaw_api.modules.evals.run_eval --grader rule

    # Output to specific directory
    EVAL_MODE=true python -m gerclaw_api.modules.evals.run_eval --output ./reports
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

# 添加模块路径
sys.path.insert(0, str(Path(__file__).parent))

from base_grader import (
    EvalCaseInput,
    EvalCaseOutput,
    GraderConfig,
    GraderType,
)
from evaluation_framework import (
    EvalEnvironmentError,
    EvalReport,
    EvaluationFramework,
    ReportFormat,
    check_eval_environment,
)
from rule_grader import RuleGrader
from evidence_grader import EvidenceGrader
from medical_grader import MedicalGrader
from performance_grader import PerformanceGrader
from dialogue_grader import DialogueGrader


# === 默认配置 ===
DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "reports"
DEFAULT_GRADERS = ["rule", "evidence", "medical", "performance", "dialogue"]


def create_graders(grader_names: Optional[List[str]] = None):
    """创建评分器实例"""
    grader_map = {
        "rule": lambda: RuleGrader(GraderConfig(
            name="规则评分器",
            grader_type=GraderType.RULE,
            config_params={
                "red_flag_keywords": ["胸痛", "呼吸困难", "出血", "意识模糊", "偏瘫", "跌倒", "自杀"],
            }
        )),
        "evidence": lambda: EvidenceGrader(GraderConfig(
            name="证据评分器",
            grader_type=GraderType.EVIDENCE,
        )),
        "medical": lambda: MedicalGrader(GraderConfig(
            name="医学评分器",
            grader_type=GraderType.MEDICAL,
            config_params={
                "drug_interactions": {
                    "阿司匹林": ["华法林"],
                    "华法林": ["阿司匹林"],
                },
                "contraindications": {
                    "阿司匹林": ["胃溃疡", "出血性疾病"],
                },
            }
        )),
        "performance": lambda: PerformanceGrader(GraderConfig(
            name="性能评分器",
            grader_type=GraderType.PERFORMANCE,
            config_params={
                "max_latency_ms": 15000,
                "max_token_count": 2000,
                "max_token_cost": 0.1,
                "max_sse_timeout": 5,
            }
        )),
        "dialogue": lambda: DialogueGrader(GraderConfig(
            name="对话评分器",
            grader_type=GraderType.DIALOGUE,
        )),
    }

    names = grader_names or DEFAULT_GRADERS
    graders = []
    for name in names:
        if name in grader_map:
            graders.append(grader_map[name]())
        else:
            print(f"[WARN] 未知评分器: {name}，跳过")
    return graders


async def mock_eval_func(input_data: EvalCaseInput) -> EvalCaseOutput:
    """模拟评测函数（用于演示）

    模拟profile.py中隐形指令的效果：
    当涉及用药时，只确认有用药史，不复述具体药名和剂量。
    """
    query = input_data.query
    metadata = input_data.metadata or {}
    context = input_data.context or {}

    # 根据query生成模拟响应
    # 注意：模拟profile.py中隐形指令的效果
    if "胸痛" in query or "呼吸困难" in query:
        response = f"根据您的描述，{query}需要引起重视。建议立即就医或拨打120急救电话。"
    elif "过敏" in query:
        # 检查是否有过敏史上下文
        if "allergy" in str(context) or "过敏" in str(metadata):
            response = "根据您的记录，您有过敏史。请在就医时告知医生，以便调整治疗方案。"
        else:
            response = f"关于过敏问题：{query}。请告知医生您的过敏史，以便调整治疗方案。"
    elif "血压" in query:
        # 检查是否有血压记录
        if "vital_sign" in str(context) or "血压" in str(metadata):
            response = "根据您的记录，您有血压监测数据。建议定期监测，遵医嘱管理。"
        else:
            # 不包含原始query，避免复述具体剂量
            response = "关于血压问题，建议定期监测血压，遵医嘱管理。如有异常请及时就医。"
    elif "药" in query or "服用" in query:
        # 关键修改：模拟隐形指令效果，不复述具体药名和剂量
        if "medication" in str(context) or "药" in str(metadata):
            response = "根据您的记录，您有相关用药史。具体用药方案请咨询主治医生，不要自行调整。"
        else:
            response = "关于用药问题，建议咨询主治医生获取个性化用药方案。"
    elif "阿司匹林" in query:
        # 直接提及药名时，引导咨询医生
        response = "关于您提到的药物，建议咨询主治医生了解具体用药方案。请勿自行调整用药。"
    else:
        response = f"关于您的问题：{query}。建议咨询专业医生获取个性化建议。"

    return EvalCaseOutput(
        case_id=input_data.case_id,
        response=response,
        latency_ms=1000,
        token_count=100,
        token_cost=0.01,
    )


def save_report(report: EvalReport, output_dir: Path, formats: List[str]):
    """保存报告到文件"""
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    framework = EvaluationFramework(strict_env_check=False)

    for fmt in formats:
        if fmt == "json":
            content = framework._export_json(report)
            filepath = output_dir / f"eval_report_{timestamp}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[INFO] JSON 报告已保存: {filepath}")

        elif fmt == "markdown":
            content = framework._export_markdown(report)
            filepath = output_dir / f"eval_report_{timestamp}.md"
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[INFO] Markdown 报告已保存: {filepath}")


def print_summary(report: EvalReport):
    """打印评测摘要"""
    print("\n" + "=" * 60)
    print(f"评测完成: {report.eval_name}")
    print("=" * 60)
    print(f"总用例数: {report.total_cases}")
    print(f"通过用例: {report.passed_cases}")
    print(f"失败用例: {report.failed_cases}")
    print(f"错误用例: {report.error_cases}")
    print(f"通过率: {report.pass_rate:.2%}")
    print("\n评分器摘要:")
    for name, summary in report.grader_summary.items():
        print(f"  {name}: 通过率 {summary['pass_rate']:.2%}, 平均分 {summary['average_score']:.4f}")
    if report.failure_list:
        print(f"\n失败用例: {len(report.failure_list)} 个")
        for failure in report.failure_list[:5]:  # 只显示前5个
            print(f"  - {failure['case_id']}: {', '.join(failure['failed_graders'])}")
        if len(report.failure_list) > 5:
            print(f"  ... 还有 {len(report.failure_list) - 5} 个失败用例")
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="GerClaw 评测框架 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--grader",
        nargs="+",
        choices=["rule", "evidence", "medical", "performance", "dialogue"],
        default=DEFAULT_GRADERS,
        help="要运行的评分器（默认：全部）",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help="fixtures 目录路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="报告输出目录",
    )
    parser.add_argument(
        "--format",
        nargs="+",
        choices=["json", "markdown"],
        default=["json", "markdown"],
        help="报告格式",
    )
    parser.add_argument(
        "--skip-env-check",
        action="store_true",
        help="跳过环境检查（仅用于测试）",
    )

    args = parser.parse_args()

    # 环境检查
    if not args.skip_env_check:
        try:
            check_eval_environment()
        except EvalEnvironmentError as e:
            print(f"[ERROR] 环境检查失败: {e}")
            print("\n请设置环境变量: EVAL_MODE=true")
            sys.exit(1)

    # 设置环境变量（如果跳过检查）
    if args.skip_env_check:
        os.environ["EVAL_MODE"] = "true"

    print(f"[INFO] 评测模式: EVAL_MODE={os.environ.get('EVAL_MODE_ENV', 'not_set')}")
    print(f"[INFO] fixtures 目录: {args.fixtures}")
    print(f"[INFO] 输出目录: {args.output}")
    print(f"[INFO] 评分器: {', '.join(args.grader)}")

    # 创建框架
    framework = EvaluationFramework(
        output_dir=args.output,
        strict_env_check=not args.skip_env_check,
    )

    # 加载测试用例
    case_count = framework.load_fixtures(args.fixtures)
    print(f"[INFO] 加载测试用例: {case_count} 个")

    # 注册评分器
    graders = create_graders(args.grader)
    for grader in graders:
        framework.register_grader(grader)
    print(f"[INFO] 注册评分器: {len(graders)} 个")

    # 运行评测
    print("\n[INFO] 开始运行评测...")
    report = await framework.run_evaluation(mock_eval_func)

    # 打印摘要
    print_summary(report)

    # 保存报告
    save_report(report, args.output, args.format)

    # 返回退出码
    if report.pass_rate < 0.8:
        print("\n[WARN] 通过率低于 80%，请检查失败用例")
        sys.exit(1)
    else:
        print("\n[SUCCESS] 评测通过")
        sys.exit(0)


# 导出供 pyproject.toml 使用
def cli_main():
    """CLI入口点"""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()