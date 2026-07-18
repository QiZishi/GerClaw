"""Regression tests for the documentation half of the Development Harness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_docs import (
    check_markdown_links,
    check_module_documents,
    check_placeholders,
    check_requirement_matrix,
)


class VerifyDocsTests(unittest.TestCase):
    def test_placeholder_detection_rejects_unfinished_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "document.md"
            document.write_text("## Ready\nTODO: finish this boundary\n", encoding="utf-8")
            self.assertTrue(check_placeholders(document))

    def test_security_boundary_tag_is_not_a_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "document.md"
            document.write_text("Use <untrusted-web-evidence> tags.\n", encoding="utf-8")
            self.assertEqual(check_placeholders(document), [])

    def test_requirement_matrix_rejects_missing_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            docs = workspace / "docs"
            docs.mkdir()
            ids = [f"REQ-{index:02d}" for index in range(1, 61)]
            (docs / "PRD.md").write_text(
                "\n".join(f"- `{item}` requirement" for item in ids),
                encoding="utf-8",
            )
            rows = (
                "| ID | 需求 | 设计→实现合同/模块 | 测试→运行证据 | 状态与缺口 |\n"
                "|---|---|---|---|---|\n"
                + "\n".join(
                f"| {item} | requirement | module | evidence | ✅ |" for item in ids[:-1]
                )
            )
            (docs / "REQUIREMENTS_MATRIX.md").write_text(rows, encoding="utf-8")
            self.assertEqual(
                check_requirement_matrix(workspace),
                ["matrix missing PRD IDs: REQ-60"],
            )

    def test_broken_relative_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "README.md").write_text(
                "Read [missing](docs/missing.md).\n",
                encoding="utf-8",
            )
            self.assertIn("README.md -> docs/missing.md", check_markdown_links(workspace))

    def test_broken_heading_anchor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "README.md").write_text(
                "# GerClaw\n\n[错误目录](#不存在的章节)\n",
                encoding="utf-8",
            )
            self.assertIn(
                "README.md -> #不存在的章节 (不存在的章节锚点)",
                check_markdown_links(workspace),
            )

    def test_existing_chinese_and_english_heading_anchors_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            (workspace / "README.md").write_text(
                "# GerClaw\n\n"
                "[快速开始](#快速开始)\n"
                "[知识库](#医学知识库与-mineru)\n\n"
                "## 快速开始\n\n"
                "## 医学知识库与 MinerU\n",
                encoding="utf-8",
            )
            self.assertEqual(check_markdown_links(workspace), [])

    def test_module_document_check_requires_agents_and_readme_for_python_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            module = workspace / "apps/api/src/gerclaw_api/modules/example"
            module.mkdir(parents=True)
            (module / "implementation.py").write_text("VALUE = 1\n", encoding="utf-8")
            self.assertEqual(
                check_module_documents(workspace),
                [
                    "apps/api/src/gerclaw_api/modules/example missing AGENTS.md",
                    "apps/api/src/gerclaw_api/modules/example missing README.md",
                ],
            )
            (module / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
            (module / "README.md").write_text("# Example\n", encoding="utf-8")
            self.assertEqual(check_module_documents(workspace), [])


if __name__ == "__main__":
    unittest.main()
