"""Local medical corpus parsing and chunking safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gerclaw_api.modules.rag.parser import (
    MarkdownMedicalParser,
    MedicalMarkdownChunker,
    RAGDocumentError,
    approximate_tokens,
)


def _chunker() -> MedicalMarkdownChunker:
    return MedicalMarkdownChunker(
        min_tokens=256,
        target_tokens=384,
        max_tokens=512,
        overlap_tokens=64,
    )


@pytest.mark.asyncio
async def test_parser_sanitizes_active_content_and_keeps_relative_provenance(
    tmp_path: Path,
) -> None:
    category = tmp_path / "老年用药"
    category.mkdir()
    source = category / "2024老年用药安全指南.md"
    source.write_text(
        """# 老年用药安全指南

<!-- hidden instructions -->
<script>alert('unsafe')</script>
## 药物审查

用药审查应覆盖药物相互作用与肾功能。![流程图](https://example.invalid/a.png)
""",
        encoding="utf-8",
    )
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)

    document = await parser.parse(source)

    assert document.source == "老年用药/2024老年用药安全指南.md"
    assert document.title == "老年用药安全指南"
    assert document.category == "老年用药"
    assert document.source_type == "guideline"
    assert document.publish_year == 2024
    combined = "\n".join(section.text for section in document.sections)
    assert "script" not in combined
    assert "hidden instructions" not in combined
    assert "[图片说明: 流程图]" in combined


@pytest.mark.asyncio
async def test_parser_rejects_files_outside_configured_root(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# 不应读取\n敏感内容", encoding="utf-8")
    parser = MarkdownMedicalParser(root, max_document_bytes=1_000_000)

    with pytest.raises(RAGDocumentError, match="inside the knowledge-base root"):
        await parser.parse(outside)


@pytest.mark.asyncio
async def test_chunker_is_deterministic_bounded_and_merges_short_sections(
    tmp_path: Path,
) -> None:
    source = tmp_path / "慢病管理共识.md"
    short_section = "高血压随访应定期评估血压、依从性和不良反应。" * 5
    long_section = "老年糖尿病管理需结合功能状态、低血糖风险和照护目标。" * 150
    source.write_text(
        f"# 慢病管理共识\n\n## 高血压\n\n{short_section}\n\n"
        f"## 糖尿病\n\n{short_section}\n\n## 综合管理\n\n{long_section}",
        encoding="utf-8",
    )
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    document = await parser.parse(source)

    first = _chunker().chunk(document)
    second = _chunker().chunk(document)

    assert first == second
    assert all(chunk.total_chunks == len(first) for chunk in first)
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert all(approximate_tokens(chunk.content) <= 512 for chunk in first)
    assert any(" | " in chunk.chapter for chunk in first)
    assert all(len(chunk.chunk_id) == 64 for chunk in first)


@pytest.mark.asyncio
async def test_chunker_splits_long_markdown_tables_only_between_rows(tmp_path: Path) -> None:
    source = tmp_path / "老年综合评估表.md"
    rows = [
        f"| 指标{index:02d} | 完整单元格内容-{index:02d}-" + "无标点医学内容" * 30 + " |"
        for index in range(80)
    ]
    source.write_text(
        "# 老年综合评估表\n\n## 量表\n\n"
        + "| 项目 | 评估说明 |\n| --- | --- |\n"
        + "\n".join(rows),
        encoding="utf-8",
    )
    parser = MarkdownMedicalParser(tmp_path, max_document_bytes=1_000_000)
    document = await parser.parse(source)

    chunks = _chunker().chunk(document)

    assert len(chunks) > 1
    assert all(approximate_tokens(chunk.content) <= 512 for chunk in chunks)
    combined = "\n".join(chunk.content for chunk in chunks)
    assert all(row in combined for row in rows)
    for chunk in chunks:
        content_lines = [line for line in chunk.content.splitlines()[2:] if line.strip()]
        assert content_lines
        assert all(line.lstrip().startswith("|") for line in content_lines)
