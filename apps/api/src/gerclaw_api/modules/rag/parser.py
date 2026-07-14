"""Safe Markdown parsing and heading-aware medical-document chunking."""

from __future__ import annotations

import asyncio
import hashlib
import re
from pathlib import Path

from gerclaw_api.modules.rag.models import IndexChunk, ParsedDocument, ParsedSection, SourceType

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_IMAGE = re.compile(r"!\[([^\]\n]{0,200})\]\([^\)\n]{0,2048}\)")
_SENTENCE = re.compile(r"(?<=[。！？!?；;])")  # noqa: RUF001 - Chinese sentence boundaries
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_EXTRACTION_SUFFIX = re.compile(r"(?:_MinerU_+|_+MinerU_+).*?$", re.IGNORECASE)
_HTML_COMMENT_START = "<!--"
_HTML_COMMENT_END = "-->"
_DANGEROUS_BLOCK_TAGS = ("script", "style", "iframe", "object", "embed")


class RAGDocumentError(ValueError):
    """Raised when a local knowledge document violates an indexing boundary."""


def approximate_tokens(value: str) -> int:
    """Match AgentScope's dependency-free UTF-8 token approximation."""

    return max(1, (len(value.encode("utf-8")) + 3) // 4)


def _clean_title(filename: str) -> str:
    title = _EXTRACTION_SUFFIX.sub("", Path(filename).stem)
    title = re.sub(r"^MinerU_+", "", title, flags=re.IGNORECASE)
    return re.sub(r"[_\s]+", " ", title).strip()[:512] or "未命名医学文献"


def _infer_source_type(title: str) -> SourceType:
    folded = title.casefold()
    if any(token in folded for token in ("指南", "guideline", "guidelines", "实践指南")):
        return "guideline"
    if any(token in folded for token in ("共识", "consensus", "声明", "statement")):
        return "consensus"
    if any(token in folded for token in ("教材", "临床营养学", "内科学", "外科学", "whitebook")):
        return "textbook"
    return "literature"


def _strip_markdown_image(match: re.Match[str]) -> str:
    alt = match.group(1).strip()
    return f"[图片说明: {alt}]" if alt else ""


def _sanitize_markdown(raw: str) -> str:
    """Remove executable/invisible carriers while preserving medical tables and text."""

    output: list[str] = []
    in_comment = False
    blocked_tag: str | None = None
    for original_line in raw.replace("\x00", "").splitlines():
        line = original_line
        lowered = line.casefold()
        if blocked_tag is not None:
            if f"</{blocked_tag}" in lowered:
                blocked_tag = None
            continue
        for tag in _DANGEROUS_BLOCK_TAGS:
            if f"<{tag}" in lowered:
                if f"</{tag}" not in lowered:
                    blocked_tag = tag
                line = ""
                break
        if not line:
            continue
        while True:
            if in_comment:
                end = line.find(_HTML_COMMENT_END)
                if end < 0:
                    line = ""
                    break
                line = line[end + len(_HTML_COMMENT_END) :]
                in_comment = False
            start = line.find(_HTML_COMMENT_START)
            if start < 0:
                break
            end = line.find(_HTML_COMMENT_END, start + len(_HTML_COMMENT_START))
            if end < 0:
                line = line[:start]
                in_comment = True
                break
            line = line[:start] + line[end + len(_HTML_COMMENT_END) :]
        if not line or "data:image/" in line.casefold():
            continue
        line = _IMAGE.sub(_strip_markdown_image, line).rstrip()
        output.append(line)
    cleaned = "\n".join(output)
    return re.sub(r"\n{4,}", "\n\n\n", cleaned).strip()


class MarkdownMedicalParser:
    """Read only Markdown files contained by the configured knowledge-base root."""

    def __init__(self, root: Path, *, max_document_bytes: int) -> None:
        self._root = root.expanduser().resolve()
        self._max_document_bytes = max_document_bytes

    @property
    def root(self) -> Path:
        """Return the canonical corpus root."""

        return self._root

    async def discover(self) -> tuple[Path, ...]:
        """List corpus Markdown files without following paths outside the root."""

        def _walk() -> tuple[Path, ...]:
            if not self._root.is_dir():
                raise RAGDocumentError("knowledge-base directory does not exist")
            files: list[Path] = []
            for candidate in self._root.rglob("*.md"):
                resolved = candidate.resolve()
                if not resolved.is_file() or not resolved.is_relative_to(self._root):
                    continue
                files.append(resolved)
            return tuple(sorted(files, key=lambda path: path.relative_to(self._root).as_posix()))

        return await asyncio.to_thread(_walk)

    async def parse(self, path: Path) -> ParsedDocument:
        """Validate, decode, sanitize, and section one Markdown document."""

        resolved = await asyncio.to_thread(lambda: path.expanduser().resolve())
        if not resolved.is_relative_to(self._root) or resolved.suffix.casefold() != ".md":
            raise RAGDocumentError(
                "document must be a Markdown file inside the knowledge-base root"
            )
        try:
            stat = await asyncio.to_thread(resolved.stat)
        except OSError as error:
            raise RAGDocumentError("document cannot be read") from error
        if stat.st_size <= 0 or stat.st_size > self._max_document_bytes:
            raise RAGDocumentError("document size is outside the configured boundary")
        try:
            raw_bytes = await asyncio.to_thread(resolved.read_bytes)
        except OSError as error:
            raise RAGDocumentError("document cannot be read") from error
        try:
            raw = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise RAGDocumentError("document is not valid UTF-8 Markdown") from error
        cleaned = _sanitize_markdown(raw)
        if not cleaned:
            raise RAGDocumentError("document contains no indexable text")

        source = resolved.relative_to(self._root).as_posix()
        fallback_title = _clean_title(resolved.name)
        sections, heading_title = self._sections(cleaned, fallback_title)
        title = (heading_title or fallback_title)[:512]
        category = (
            resolved.relative_to(self._root).parts[0]
            if len(resolved.relative_to(self._root).parts) > 1
            else "通用"
        )
        category = re.sub(r"(?i)md$", "", category).strip()[:128] or "通用"
        year_match = _YEAR.search(fallback_title) or _YEAR.search(cleaned[:8_000])
        publish_year = int(year_match.group(1)) if year_match else None
        return ParsedDocument(
            document_id=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            source=source,
            title=title,
            category=category,
            source_type=_infer_source_type(title),
            publish_year=publish_year,
            sha256=hashlib.sha256(raw_bytes).hexdigest(),
            size_bytes=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            sections=sections,
        )

    @staticmethod
    def _sections(
        cleaned: str, fallback_title: str
    ) -> tuple[tuple[ParsedSection, ...], str | None]:
        hierarchy: dict[int, str] = {}
        current_chapter = fallback_title
        current_lines: list[str] = []
        result: list[ParsedSection] = []
        heading_title: str | None = None

        def flush() -> None:
            text = "\n".join(current_lines).strip()
            if text:
                result.append(ParsedSection(chapter=current_chapter[:1_024], text=text))
            current_lines.clear()

        for line in cleaned.splitlines():
            heading = _HEADING.match(line)
            if heading is None:
                current_lines.append(line)
                continue
            flush()
            level = len(heading.group(1))
            value = heading.group(2).strip()[:512]
            if heading_title is None and level == 1:
                heading_title = value
            hierarchy[level] = value
            for deeper in tuple(key for key in hierarchy if key > level):
                del hierarchy[deeper]
            current_chapter = " > ".join(hierarchy[key] for key in sorted(hierarchy))
        flush()
        if not result:
            result.append(ParsedSection(chapter=fallback_title, text=cleaned))
        return tuple(result), heading_title


class MedicalMarkdownChunker:
    """Create bounded chunks while retaining Markdown heading provenance."""

    INDEX_VERSION = "markdown-heading-v1"

    def __init__(
        self,
        *,
        min_tokens: int,
        target_tokens: int,
        max_tokens: int,
        overlap_tokens: int,
    ) -> None:
        self._min_tokens = min_tokens
        self._target_tokens = target_tokens
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens

    def chunk(self, document: ParsedDocument) -> tuple[IndexChunk, ...]:
        """Chunk a parsed document and assign deterministic IDs and positions."""

        raw_chunks: list[tuple[str, str]] = []
        for section in document.sections:
            chapter = section.chapter[:1_024]
            prefix = f"{document.title}\n章节: {chapter}\n"
            budget = max(64, self._max_tokens - approximate_tokens(prefix))
            units = self._units(section.text, budget)
            bodies = self._pack(units, prefix)
            raw_chunks.extend((chapter, prefix + body) for body in bodies if body.strip())

        raw_chunks = self._merge_adjacent_small_chunks(raw_chunks)

        total = len(raw_chunks)
        chunks: list[IndexChunk] = []
        for index, (chapter, content) in enumerate(raw_chunks):
            if approximate_tokens(content) > self._max_tokens:
                raise RAGDocumentError("chunker produced a chunk above the hard token boundary")
            chunk_id = hashlib.sha256(
                f"{document.document_id}:{document.sha256}:{index}:{content}".encode()
            ).hexdigest()
            chunks.append(
                IndexChunk(
                    chunk_id=chunk_id,
                    document_id=document.document_id,
                    document_sha256=document.sha256,
                    source=document.source,
                    title=document.title,
                    chapter=chapter,
                    category=document.category,
                    source_type=document.source_type,
                    publish_year=document.publish_year,
                    chunk_index=index,
                    total_chunks=total,
                    content=content,
                )
            )
        if not chunks:
            raise RAGDocumentError("document produced no indexable chunks")
        return tuple(chunks)

    def _merge_adjacent_small_chunks(
        self, raw_chunks: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Merge tiny neighboring sections without losing their citation headings."""

        if len(raw_chunks) < 2:
            return raw_chunks
        merged: list[tuple[str, str]] = []
        index = 0
        separator = "\n\n--- 相邻章节 ---\n\n"
        while index < len(raw_chunks):
            chapter, content = raw_chunks[index]
            while approximate_tokens(content) < self._min_tokens and index + 1 < len(raw_chunks):
                next_chapter, next_content = raw_chunks[index + 1]
                candidate = content + separator + next_content
                if approximate_tokens(candidate) > self._max_tokens:
                    break
                chapter = self._combine_chapters(chapter, next_chapter)
                content = candidate
                index += 1
            merged.append((chapter, content))
            index += 1

        if len(merged) > 1 and approximate_tokens(merged[-1][1]) < self._min_tokens:
            previous_chapter, previous_content = merged[-2]
            last_chapter, last_content = merged[-1]
            candidate = previous_content + separator + last_content
            if approximate_tokens(candidate) <= self._max_tokens:
                merged[-2:] = [(self._combine_chapters(previous_chapter, last_chapter), candidate)]
        return merged

    @staticmethod
    def _combine_chapters(left: str, right: str) -> str:
        chapters = list(dict.fromkeys([*left.split(" | "), *right.split(" | ")]))
        return " | ".join(chapters)[:1_024]

    def _units(self, text: str, token_budget: int) -> list[str]:
        units: list[str] = []
        for paragraph in re.split(r"\n{2,}", text):
            value = paragraph.strip()
            if not value:
                continue
            if approximate_tokens(value) <= token_budget:
                units.append(value)
                continue
            table_fragments = self._table_fragments(value, token_budget)
            if table_fragments is not None:
                units.extend(table_fragments)
                continue
            sentences = [item.strip() for item in _SENTENCE.split(value) if item.strip()]
            for sentence in sentences:
                if approximate_tokens(sentence) <= token_budget:
                    units.append(sentence)
                else:
                    units.extend(self._hard_split(sentence, token_budget))
        return units

    @staticmethod
    def _table_fragments(value: str, token_budget: int) -> list[str] | None:
        """Split long Markdown tables only between rows and repeat their header."""

        lines = [line.rstrip() for line in value.splitlines() if line.strip()]
        if (
            len(lines) < 2
            or _TABLE_SEPARATOR.fullmatch(lines[1]) is None
            or any("|" not in line for line in lines)
        ):
            return None
        header = lines[:2]
        if approximate_tokens("\n".join(header)) > token_budget:
            raise RAGDocumentError("Markdown table header exceeds the chunk token boundary")
        fragments: list[str] = []
        current = list(header)
        for row in lines[2:]:
            candidate = "\n".join([*current, row])
            if approximate_tokens(candidate) <= token_budget:
                current.append(row)
                continue
            if len(current) == len(header):
                raise RAGDocumentError("Markdown table row exceeds the chunk token boundary")
            fragments.append("\n".join(current))
            current = [*header, row]
            if approximate_tokens("\n".join(current)) > token_budget:
                raise RAGDocumentError("Markdown table row exceeds the chunk token boundary")
        fragments.append("\n".join(current))
        return fragments

    @staticmethod
    def _hard_split(value: str, token_budget: int) -> list[str]:
        parts: list[str] = []
        start = 0
        while start < len(value):
            end = min(len(value), start + max(32, token_budget * 2))
            while end > start + 1 and approximate_tokens(value[start:end]) > token_budget:
                end -= 1
            if end <= start:
                end = start + 1
            parts.append(value[start:end].strip())
            start = end
        return [part for part in parts if part]

    def _pack(self, units: list[str], prefix: str) -> list[str]:
        if not units:
            return []
        prefix_tokens = approximate_tokens(prefix)
        target_body = max(64, self._target_tokens - prefix_tokens)
        max_body = max(64, self._max_tokens - prefix_tokens)
        output: list[str] = []
        current: list[str] = []

        def body(parts: list[str]) -> str:
            return "\n\n".join(parts).strip()

        for unit in units:
            candidate = body([*current, unit])
            if current and approximate_tokens(candidate) > target_body:
                output.append(body(current))
                overlap = self._tail(output[-1], min(self._overlap_tokens, max_body // 3))
                current = [overlap, unit] if overlap else [unit]
                if approximate_tokens(body(current)) > max_body:
                    current = [unit]
            else:
                current.append(unit)
            if approximate_tokens(body(current)) > max_body:
                last = current.pop()
                if current:
                    output.append(body(current))
                current = [last]
        if current:
            output.append(body(current))
        return output

    @staticmethod
    def _tail(value: str, tokens: int) -> str:
        if tokens <= 0:
            return ""
        if any(_TABLE_SEPARATOR.fullmatch(line) is not None for line in value.splitlines()):
            return ""
        start = len(value)
        while start > 0 and approximate_tokens(value[start:]) < tokens:
            start -= 1
        tail = value[start:].lstrip()
        boundary = min((pos for pos in (tail.find("\n"), tail.find("。")) if pos >= 0), default=-1)
        return tail[boundary + 1 :].lstrip() if boundary >= 0 else tail
