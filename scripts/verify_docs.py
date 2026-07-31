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

USER_FACING_DOCUMENTS = ("README.md", "ARCHITECTURE.md")

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
        lines = [line for line in content.splitlines() if line.strip()]
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
        "scripts",
    ]
    missing = []
    for d in required_dirs:
        if not (workspace / d).is_dir():
            missing.append(d)
    return missing


def check_module_documents(workspace: Path) -> list[str]:
    """Require operational docs beside every first-party Python module package."""

    modules_root = workspace / "apps/api/src/gerclaw_api/modules"
    if not modules_root.is_dir():
        return ["apps/api/src/gerclaw_api/modules is missing"]
    issues: list[str] = []
    for module in sorted(path for path in modules_root.iterdir() if path.is_dir()):
        has_python_source = any(
            path.suffix == ".py" and path.name != "__init__.py" for path in module.iterdir()
        )
        if not has_python_source:
            continue
        for filename in ("AGENTS.md", "README.md"):
            document = module / filename
            if not document.is_file() or count_lines(document) == 0:
                issues.append(f"{module.relative_to(workspace)} missing {filename}")
    return issues


def check_markdown_links(workspace: Path) -> list[str]:
    """Reject broken relative paths and heading anchors in governed Markdown."""

    def heading_anchors(document: Path) -> set[str]:
        anchors: set[str] = set()
        duplicates: dict[str, int] = {}
        in_fence = False
        for raw_line in document.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = re.match(r"^#{1,6}\s+(.+?)\s*#*$", line)
            if not match:
                continue
            heading = re.sub(r"<[^>]+>", "", match.group(1))
            heading = re.sub(r"[`*_~]", "", heading).strip().lower()
            slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
            slug = re.sub(r"\s+", "-", slug)
            duplicate_number = duplicates.get(slug, 0)
            duplicates[slug] = duplicate_number + 1
            anchors.add(slug if duplicate_number == 0 else f"{slug}-{duplicate_number}")
        return anchors

    issues: list[str] = []
    for rel_path in (*REQUIRED_FILES, *USER_FACING_DOCUMENTS):
        document = workspace / rel_path
        if not document.exists() or document.suffix != ".md":
            continue
        content = document.read_text(encoding="utf-8")
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
            normalized = unquote(target.strip().strip("<>"))
            if normalized.startswith(("/", "http://", "https://", "mailto:", "file:")):
                continue
            path_part, separator, fragment = normalized.partition("#")
            target_document = (document.parent / path_part).resolve() if path_part else document
            if path_part and not target_document.exists():
                issues.append(f"{rel_path} -> {target}")
                continue
            if separator and fragment and target_document.suffix.lower() == ".md":
                if fragment.lower() not in heading_anchors(target_document):
                    issues.append(f"{rel_path} -> {target} (不存在的章节锚点)")
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

    link_issues = check_markdown_links(workspace)
    for issue in link_issues:
        errors.append(f"BROKEN LINK:  {issue}")

    plan_issues = check_exec_plans_exist(workspace)
    for issue in plan_issues:
        warnings.append(f"EXEC PLAN:    {issue}")

    module_issues = check_module_documents(workspace)
    for issue in module_issues:
        errors.append(f"MODULE DOCS:  {issue}")

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
