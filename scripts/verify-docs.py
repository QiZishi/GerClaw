#!/usr/bin/env python3
"""
Harness Documentation Verification Script
验证harness规范文档的完整性：文件存在、非空、必填章节完整、无占位符残留。

Usage:
    python3 verify-docs.py <workspace_path>
"""

import sys
import os
import re
from pathlib import Path

REQUIRED_FILES = {
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
            "## 1. 产品定位",
            "## 2. 核心价值",
            "## 3. 目标用户",
            "## 4. 功能清单",
            "## 5. 技术栈",
            "## 6. 非功能需求",
            "## 7. 协作模式确认",
            "## 8. 铁律确认",
            "## 9. 验收标准",
            "## 10. 约束与风险",
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
            "## 当前里程碑",
            "## 执行计划索引",
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


def check_p0_modules_have_specs_and_designs(workspace: Path) -> list:
    issues = []
    proposal = workspace / "docs/PRD.md"
    if not proposal.exists():
        return ["PRD.md not found, cannot check P0 modules"]

    try:
        content = proposal.read_text(encoding="utf-8")
        p0_modules = set()
        in_feature_table = False
        for line in content.splitlines():
            if "## 4. 功能清单" in line:
                in_feature_table = True
                continue
            if in_feature_table and line.startswith("## "):
                break
            if in_feature_table and line.strip().startswith("|") and "P0" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 4:
                    module_name = parts[1]
                    if module_name and module_name not in ("模块", "---", ""):
                        p0_modules.add(module_name)

        for module in p0_modules:
            spec_file = workspace / f"docs/product-specs/{module}.md"
            design_file = workspace / f"docs/design-docs/{module}.md"
            if not spec_file.exists():
                issues.append(f"Missing product-spec for P0 module: {module}")
            if not design_file.exists():
                issues.append(f"Missing design-doc for P0 module: {module}")
    except Exception as e:
        issues.append(f"Error checking P0 modules: {e}")
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

    p0_issues = check_p0_modules_have_specs_and_designs(workspace)
    for issue in p0_issues:
        errors.append(f"P0 MODULE:    {issue}")

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
