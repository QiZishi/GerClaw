#!/usr/bin/env python3
"""
Harness Documentation Verification Script
验证harness规范文档的完整性：文件存在、非空、必填章节完整、无占位符残留。

Usage:
    python3 verify-docs.py <workspace_path>
"""

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REQUIRED_FILES = {
    "README.md": {
        "min_lines": 40,
        "required_sections": [
            "## 当前状态",
            "## 系统架构",
            "## 环境变量",
            "## 本地启动",
            "## 验证",
            "## Docker",
            "## 测试与性能状态",
            "## 风险与改进",
            "## 医疗安全",
        ],
    },
    "AGENTS.md": {
        "min_lines": 50,
        "max_lines": 200,
        "required_sections": [
            "## Product",
            "## Start Here",
            "## Agent Operating Rules",
            "## Expected Agent Loop",
            "## Definition of Done",
            "## 铁律摘要",
        ],
    },
    "CLAUDE.md": {
        "min_lines": 1,
        "max_lines": 5,
        "required_sections": [],
    },
    "ARCHITECTURE.md": {
        "min_lines": 50,
        "required_sections": [
            "## 1. 系统目标",
            "## 3. 推荐技术栈",
            "## 5. 分层依赖",
            "## 6. 数据边界",
            "## 7. Agent-Legible Invariants",
        ],
    },
    "docs/PRD.md": {
        "min_lines": 50,
        "required_sections": [
            "## 1. 产品目标",
            "## 2. 用户与模式",
            "## 3. 核心用户旅程",
            "## 4. 功能需求",
            "## 5. 非功能指标",
            "## 6. 数据与信任边界",
            "## 7. 发布验收",
            "## 8. 当前事实基线",
        ],
    },
    "docs/REQUIREMENTS_MATRIX.md": {
        "min_lines": 30,
        "required_sections": [
            "# GerClaw 需求→模块→验收矩阵",
            "## 发布规则",
        ],
    },
    "docs/DEVELOPMENT_HARNESS.md": {
        "min_lines": 20,
        "required_sections": [
            "## 模式",
            "## 环境前置条件",
            "## 失败语义",
            "## 证据合同",
        ],
    },
    "docs/SECURITY.md": {
        "min_lines": 30,
        "required_sections": [
            "## 1. 认证与授权",
            "## 2. 数据安全",
            "## 3. Prompt Injection 防护",
            "## 5. 审计日志",
        ],
    },
    "docs/RELIABILITY.md": {
        "min_lines": 30,
        "required_sections": [
            "## 1. 超时策略",
            "## 2. 重试策略",
            "## 3. 降级策略",
            "## 5. 健康检查",
        ],
    },
    "docs/QUALITY_SCORE.md": {
        "min_lines": 20,
        "required_sections": [
            "## 评分规则",
            "## 模块质量评分",
        ],
    },
    "docs/DESIGN.md": {
        "min_lines": 30,
        "required_sections": [
            "## 1. 设计理念",
            "## 2. 视觉规范",
            "## 3. 交互规范",
        ],
    },
    "docs/PRODUCT_SENSE.md": {
        "min_lines": 20,
        "required_sections": [
            "## 1. 产品核心理念",
            "## 2. 好的行为",
            "## 3. 坏的行为",
            "## 4. 成功的定性标准",
        ],
    },
    "docs/PLANS.md": {
        "min_lines": 10,
        "required_sections": [
            "## 当前阶段",
            "## 活跃计划",
            "## 后续顺序",
            "## 交付规则",
            "## 已完成生产里程碑",
        ],
    },
    "docs/长期规划.md": {
        "min_lines": 20,
        "required_sections": [
            "## 一、项目长期目标",
            "## 二、产品原则",
            "## 三、模块交付追踪日志",
            "## 四、进度总览表",
        ],
    },
    "docs/design-docs/index.md": {
        "min_lines": 5,
        "required_sections": ["## 模块设计文档"],
    },
    "docs/design-docs/core-beliefs.md": {
        "min_lines": 15,
        "required_sections": [
            "## 1. 我们相信",
            "## 3. 技术决策原则",
        ],
    },
    "docs/product-specs/index.md": {
        "min_lines": 5,
        "required_sections": ["## 模块产品规格"],
    },
    "docs/exec-plans/tech-debt-tracker.md": {
        "min_lines": 5,
        "required_sections": ["## 活跃技术债"],
    },
}

OPTIONAL_FILES = {
    "docs/FRONTEND.md": {
        "min_lines": 30,
        "required_sections": [
            "## 1. 技术栈",
            "## 3. 组件规范",
        ],
    },
}

PLACEHOLDER_PATTERNS = [
    r"\{\{[^}]+\}\}",
    r"TODO",
    r"待补充",
    r"待填写",
    r"待完善",
    r"如：",
    r"例如：",
    r"XXX",
    r"xxx",
    # Security boundary tags such as <untrusted-web-evidence> are executable
    # protocol literals, not unfinished documentation. Angle-bracket placeholders
    # in this repository contain human-language text or whitespace.
    r"<[^>]*[\s\u4e00-\u9fff][^>]*>",
]

EXCLUDED_PATTERNS = [
    r"^```",
    r"^>",
    r"<!--",
    r"-->",
    r"\{\{YYYY-MM-DD\}\}",
    r"\{\{项目名\}\}",
    r"\{\{模块名\}\}",
]


def should_skip_line(line: str) -> bool:
    for pattern in EXCLUDED_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def count_lines(filepath: Path) -> int:
    try:
        content = filepath.read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.strip()]
        return len(lines)
    except Exception:
        return 0


def check_sections(filepath: Path, required_sections: list) -> list:
    missing = []
    try:
        content = filepath.read_text(encoding="utf-8")
        for section in required_sections:
            if section not in content:
                missing.append(section)
    except Exception:
        missing = required_sections
    return missing


def check_placeholders(filepath: Path) -> list:
    issues = []
    try:
        content = filepath.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), 1):
            if should_skip_line(line):
                continue
            for pattern in PLACEHOLDER_PATTERNS:
                if re.search(pattern, line):
                    stripped = line.strip()
                    if len(stripped) > 80:
                        stripped = stripped[:77] + "..."
                    issues.append((i, pattern, stripped))
                    break
    except Exception as e:
        issues.append((0, "read_error", str(e)))
    return issues


def check_required_dirs(workspace: Path) -> list:
    required_dirs = [
        "docs/design-docs",
        "docs/product-specs",
        "docs/exec-plans/active",
        "docs/exec-plans/completed",
        "docs/references",
        "docs/generated",
        "scripts",
    ]
    missing = []
    for d in required_dirs:
        if not (workspace / d).is_dir():
            missing.append(d)
    return missing


MIN_REQUIREMENT_COUNT = 59


def _duplicates(values: list[str]) -> list[str]:
    return sorted(item for item in set(values) if values.count(item) != 1)


def check_requirement_matrix(workspace: Path) -> list[str]:
    """Ensure PRD and matrix expose the same non-trivial requirement inventory."""

    prd = workspace / "docs/PRD.md"
    matrix = workspace / "docs/REQUIREMENTS_MATRIX.md"
    if not prd.exists() or not matrix.exists():
        return ["PRD or requirements matrix is missing"]
    prd_ids = re.findall(r"`([A-Z]+-\d{2})`", prd.read_text(encoding="utf-8"))
    matrix_content = matrix.read_text(encoding="utf-8")
    matrix_ids = re.findall(
        r"^\| ([A-Z]+-\d{2}) \|",
        matrix_content,
        flags=re.MULTILINE,
    )
    issues: list[str] = []
    required_header = (
        "| ID | 需求 | 设计→实现合同/模块 | 测试→运行证据 | 状态与缺口 |"
    )
    if required_header not in matrix_content:
        issues.append("matrix lacks the requirement→design→implementation→test→runtime header")
    if len(set(prd_ids)) < MIN_REQUIREMENT_COUNT:
        issues.append(
            f"PRD tracks only {len(set(prd_ids))} requirements; need >= {MIN_REQUIREMENT_COUNT}"
        )
    missing = sorted(set(prd_ids) - set(matrix_ids))
    extra = sorted(set(matrix_ids) - set(prd_ids))
    prd_duplicates = _duplicates(prd_ids)
    matrix_duplicates = _duplicates(matrix_ids)
    if missing:
        issues.append(f"matrix missing PRD IDs: {', '.join(missing)}")
    if extra:
        issues.append(f"matrix has unknown IDs: {', '.join(extra)}")
    if prd_duplicates:
        issues.append(f"duplicate PRD IDs: {', '.join(prd_duplicates)}")
    if matrix_duplicates:
        issues.append(f"duplicate matrix IDs: {', '.join(matrix_duplicates)}")
    status_ids = re.findall(
        r"^\| ([A-Z]+-\d{2}) \|.*\| ([✅🚧❌])[^|]*\|$",
        matrix_content,
        flags=re.MULTILINE,
    )
    if len(status_ids) != len(matrix_ids):
        issues.append("every matrix row must end in an explicit ✅/🚧/❌ status")
    return issues


def check_markdown_links(workspace: Path) -> list[str]:
    """Reject broken relative Markdown links in governed documentation."""

    issues: list[str] = []
    for rel_path in REQUIRED_FILES:
        document = workspace / rel_path
        if not document.exists() or document.suffix != ".md":
            continue
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
            normalized = unquote(target.strip().strip("<>"))
            if normalized.startswith(("#", "/", "http://", "https://", "mailto:", "file:")):
                continue
            path_part = normalized.split("#", maxsplit=1)[0]
            if path_part and not (document.parent / path_part).resolve().exists():
                issues.append(f"{rel_path} -> {target}")
    return issues


def check_exec_plans_exist(workspace: Path) -> list:
    issues = []
    active_dir = workspace / "docs/exec-plans/active"
    if active_dir.is_dir():
        plans = list(active_dir.glob("*.md"))
        if len(plans) == 0:
            issues.append("No exec-plan exists in docs/exec-plans/active/")
    return issues


def verify(workspace_path: str) -> bool:
    workspace = Path(workspace_path).resolve()
    if not workspace.is_dir():
        print(f"ERROR: {workspace} is not a directory")
        return False

    print(f"Verifying harness documentation in: {workspace}")
    print("=" * 60)

    errors = []
    warnings = []

    missing_dirs = check_required_dirs(workspace)
    for d in missing_dirs:
        errors.append(f"MISSING DIR:  {d}/")

    for rel_path, rules in REQUIRED_FILES.items():
        filepath = workspace / rel_path
        if not filepath.exists():
            errors.append(f"MISSING FILE: {rel_path}")
            continue

        lines = count_lines(filepath)
        min_lines = rules.get("min_lines", 10)
        max_lines = rules.get("max_lines")

        if lines < min_lines:
            errors.append(f"TOO SHORT:    {rel_path} ({lines} lines, need >= {min_lines})")
        elif max_lines and lines > max_lines:
            warnings.append(f"TOO LONG:     {rel_path} ({lines} lines, target <= {max_lines})")

        missing_sections = check_sections(filepath, rules.get("required_sections", []))
        for section in missing_sections:
            errors.append(f"MISSING SEC:  {rel_path} -> {section}")

        placeholders = check_placeholders(filepath)
        for line_no, pattern, text in placeholders[:5]:
            errors.append(f"PLACEHOLDER:  {rel_path}:{line_no} matches '{pattern}': {text}")

    for rel_path, rules in OPTIONAL_FILES.items():
        filepath = workspace / rel_path
        if not filepath.exists():
            warnings.append(f"OPTIONAL MISSING: {rel_path}")
            continue
        lines = count_lines(filepath)
        if lines < rules.get("min_lines", 10):
            warnings.append(f"OPTIONAL SHORT: {rel_path} ({lines} lines)")
        missing_sections = check_sections(filepath, rules.get("required_sections", []))
        for section in missing_sections:
            warnings.append(f"OPTIONAL MISSING SEC: {rel_path} -> {section}")
        placeholders = check_placeholders(filepath)
        for line_no, pattern, text in placeholders[:3]:
            warnings.append(f"OPTIONAL PLACEHOLDER: {rel_path}:{line_no}: {text}")

    matrix_issues = check_requirement_matrix(workspace)
    for issue in matrix_issues:
        errors.append(f"REQ MATRIX:   {issue}")

    link_issues = check_markdown_links(workspace)
    for issue in link_issues:
        errors.append(f"BROKEN LINK:  {issue}")

    plan_issues = check_exec_plans_exist(workspace)
    for issue in plan_issues:
        warnings.append(f"EXEC PLAN:    {issue}")

    print()
    if errors:
        print(f"❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
    else:
        print("✅ No errors found.")

    if warnings:
        print()
        print(f"⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")

    print()
    print("=" * 60)
    if errors:
        print(f"RESULT: FAILED ({len(errors)} errors, {len(warnings)} warnings)")
        return False
    else:
        print(f"RESULT: PASSED ({len(warnings)} warnings)")
        return True


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <workspace_path>")
        sys.exit(1)

    workspace = sys.argv[1]
    success = verify(workspace)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
