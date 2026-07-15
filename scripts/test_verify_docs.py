"""Regression tests for the documentation half of the Development Harness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from verify_docs import check_markdown_links, check_placeholders, check_requirement_matrix


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


if __name__ == "__main__":
    unittest.main()
