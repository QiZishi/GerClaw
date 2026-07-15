"""Safe ingestion, revocation and bounded context rendering for uploaded documents."""

from __future__ import annotations

import re
import uuid

from gerclaw_api.config import Settings
from gerclaw_api.database.models import UploadedDocument
from gerclaw_api.modules.document.models import (
    UploadedDocumentContext,
    UploadedDocumentCreate,
    UploadedDocumentRead,
)
from gerclaw_api.repositories.document import (
    SqlAlchemyDocumentRepository,
    UploadedDocumentNotFoundError,
)

_HTML_ACTIVE_CONTENT = re.compile(
    r"<(?:script|style|iframe|object|embed|svg|meta)[^>]*>.*?</(?:script|style|iframe|object|embed|svg|meta)>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_ACTIVE_SINGLE = re.compile(
    r"<(?:script|style|iframe|object|embed|svg|meta)[^>]*?/?>", re.IGNORECASE
)
_INJECTION_LINE = re.compile(
    r"(?:ignore|disregard|override).{0,40}(?:previous|above|system|instruction)"
    r"|(?:系统提示|忽略.{0,20}(?:指令|规则)|执行(?:以下|工具|命令))"
    r"|(?:tool[_ -]?call|developer message|system message)",
    re.IGNORECASE,
)


class DocumentContextError(RuntimeError):
    """A document cannot safely be used as the requested chat context."""


class DocumentService:
    """One service boundary for session-minimal document lifecycle control."""

    def __init__(self, repository: SqlAlchemyDocumentRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    async def register(
        self,
        payload: UploadedDocumentCreate,
        *,
        tenant_id: str,
        actor_id: str,
    ) -> UploadedDocumentRead:
        if len(payload.markdown) > self._settings.document_max_markdown_characters:
            raise DocumentContextError("parsed document exceeds the configured storage limit")
        content = self._sanitize_markdown(payload.markdown)
        if not content:
            raise DocumentContextError("parsed document did not contain safe reference text")
        record = await self._repository.create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=payload.session_id,
            filename=payload.filename,
            media_type=payload.media_type,
            parse_source=payload.parse_source,
            content=content,
        )
        return self._read(record)

    async def get(
        self,
        document_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
    ) -> UploadedDocumentRead:
        record = await self._repository.get(
            document_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            include_revoked=True,
        )
        return self._read(record)

    async def revoke(
        self,
        document_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
    ) -> None:
        record = await self._repository.get(
            document_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            include_revoked=True,
            lock=True,
        )
        record.status = "revoked"
        # Wipe the encrypted body immediately. Keeping only an inaccessible tombstone
        # makes repeat deletion idempotent without retaining health-document content.
        record.content = "[revoked]"
        record.content_characters = 9

    async def resolve_context(
        self,
        document_ids: list[uuid.UUID],
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        max_characters: int,
    ) -> list[UploadedDocumentContext]:
        if len(set(document_ids)) != len(document_ids):
            raise DocumentContextError("duplicate uploaded document reference")
        try:
            records = await self._repository.get_many_active(
                document_ids,
                tenant_id=tenant_id,
                actor_id=actor_id,
                session_id=session_id,
            )
        except UploadedDocumentNotFoundError as error:
            raise DocumentContextError("uploaded document is not active in this session") from error
        remaining = max_characters
        resolved: list[UploadedDocumentContext] = []
        for record in records:
            if remaining <= 0:
                break
            content = record.content[:remaining].strip()
            if not content:
                continue
            resolved.append(
                UploadedDocumentContext(
                    document_id=record.id,
                    filename=record.filename,
                    content=content,
                )
            )
            remaining -= len(content)
        if len(resolved) != len(document_ids):
            raise DocumentContextError("uploaded document context exceeds the configured limit")
        return resolved

    @staticmethod
    def _sanitize_markdown(markdown: str) -> str:
        without_active_html = _HTML_ACTIVE_CONTENT.sub("", markdown)
        without_active_html = _HTML_ACTIVE_SINGLE.sub("", without_active_html)
        lines = []
        for line in without_active_html.splitlines():
            if _INJECTION_LINE.search(line):
                lines.append("[已移除疑似指令性文本]")
            else:
                lines.append(line)
        return "\n".join(lines).strip()

    @staticmethod
    def _read(record: UploadedDocument) -> UploadedDocumentRead:
        return UploadedDocumentRead(
            document_id=record.id,
            session_id=record.session_id,
            filename=record.filename,
            media_type=record.media_type,
            parse_source=record.parse_source,
            status=record.status,
            content_characters=record.content_characters,
            created_at=record.created_at,
        )
