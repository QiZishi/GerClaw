"""Tenant-, actor- and session-scoped parsed-document persistence."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gerclaw_api.database.models import UploadedDocument


class UploadedDocumentNotFoundError(RuntimeError):
    """The caller cannot access the requested parsed document."""


class SqlAlchemyDocumentRepository:
    """Every lookup is restricted by verified owner and session boundaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        filename: str,
        media_type: str,
        parse_source: str,
        content: str,
    ) -> UploadedDocument:
        record = UploadedDocument(
            tenant_id=tenant_id,
            actor_id=actor_id,
            session_id=session_id,
            filename=filename,
            media_type=media_type,
            parse_source=parse_source,
            status="active",
            content=content,
            content_characters=len(content),
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def get(
        self,
        document_id: uuid.UUID,
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
        include_revoked: bool = False,
        lock: bool = False,
    ) -> UploadedDocument:
        statement = select(UploadedDocument).where(
            UploadedDocument.id == document_id,
            UploadedDocument.tenant_id == tenant_id,
            UploadedDocument.actor_id == actor_id,
            UploadedDocument.session_id == session_id,
        )
        if not include_revoked:
            statement = statement.where(UploadedDocument.status == "active")
        if lock:
            statement = statement.with_for_update()
        record = cast(UploadedDocument | None, await self._session.scalar(statement))
        if record is None:
            raise UploadedDocumentNotFoundError(str(document_id))
        return record

    async def get_many_active(
        self,
        document_ids: Sequence[uuid.UUID],
        *,
        tenant_id: str,
        actor_id: str,
        session_id: uuid.UUID,
    ) -> list[UploadedDocument]:
        if not document_ids:
            return []
        statement = select(UploadedDocument).where(
            UploadedDocument.id.in_(document_ids),
            UploadedDocument.tenant_id == tenant_id,
            UploadedDocument.actor_id == actor_id,
            UploadedDocument.session_id == session_id,
            UploadedDocument.status == "active",
        )
        records = list((await self._session.scalars(statement)).all())
        by_id = {record.id: record for record in records}
        if len(by_id) != len(document_ids):
            raise UploadedDocumentNotFoundError("one or more uploaded documents are unavailable")
        return [by_id[document_id] for document_id in document_ids]
