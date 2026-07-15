"""Resource-bounded Skill Markdown and ZIP installer."""

from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath


class UnsafeSkillArchiveError(ValueError):
    """Raised when an uploaded archive is malformed, ambiguous, or resource unsafe."""


def _safe_member(info: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(info.filename.replace("\\", "/"))
    unix_mode = info.external_attr >> 16
    file_type = stat.S_IFMT(unix_mode)
    return (
        bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and not info.is_dir()
        and not stat.S_ISLNK(unix_mode)
        and file_type in {0, stat.S_IFREG}
        and not (unix_mode & 0o111)
        and not (info.flag_bits & 0x1)
    )


def extract_skill_markdown(
    filename: str,
    content: bytes,
    *,
    max_archive_bytes: int = 262_144,
    max_markdown_characters: int = 10_000,
) -> str:
    """Extract exactly one UTF-8 SKILL.md without writing attacker-controlled paths."""

    if not 1 <= len(content) <= max_archive_bytes:
        raise UnsafeSkillArchiveError("uploaded Skill file exceeds the configured size limit")
    suffix = PurePosixPath(filename).suffix.casefold()
    if suffix in {".md", ".skill"}:
        raw = content
    elif suffix == ".zip":
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) != 1:
                    raise UnsafeSkillArchiveError("Skill archive must contain only one SKILL.md")
                if any(not _safe_member(info) for info in members):
                    raise UnsafeSkillArchiveError("Skill archive contains an unsafe entry")
                total_size = sum(info.file_size for info in members)
                if total_size > 1_048_576:
                    raise UnsafeSkillArchiveError("Skill archive expands beyond the safe limit")
                candidates = [
                    info
                    for info in members
                    if PurePosixPath(info.filename).name.casefold() == "skill.md"
                ]
                if len(candidates) != 1:
                    raise UnsafeSkillArchiveError("Skill archive must contain exactly one SKILL.md")
                target = candidates[0]
                if target.file_size > max_markdown_characters * 4:
                    raise UnsafeSkillArchiveError("SKILL.md expands beyond the safe limit")
                if target.compress_size and target.file_size / target.compress_size > 100:
                    raise UnsafeSkillArchiveError("Skill archive compression ratio is unsafe")
                raw = archive.read(target)
        except zipfile.BadZipFile as error:
            raise UnsafeSkillArchiveError("Skill archive is not a valid ZIP file") from error
    else:
        raise UnsafeSkillArchiveError("only Markdown, .skill, or ZIP uploads are supported")
    try:
        markdown = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UnsafeSkillArchiveError("SKILL.md must use UTF-8 encoding") from error
    if not 1 <= len(markdown.strip()) <= max_markdown_characters:
        raise UnsafeSkillArchiveError("SKILL.md violates the configured character limit")
    return markdown
