"""Tests for operational command boundaries and PHI-free model egress auditing."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request

from gerclaw_api import admin_bootstrap, application
from gerclaw_api.api.routes import approvals as approvals_route
from gerclaw_api.api.routes import documents as documents_route
from gerclaw_api.api.routes import health as health_route
from gerclaw_api.api.routes import memory as memory_route
from gerclaw_api.api.routes import risk_alerts as risk_alerts_route
from gerclaw_api.api.routes import traces as traces_route
from gerclaw_api.database import session as database_session
from gerclaw_api.domain.enums import FeedbackRating, TraceEventStatus, TraceEventType, TraceStatus
from gerclaw_api.domain.trace_schemas import (
    FeedbackCreate,
    TraceEventCreate,
    TraceFinishRequest,
    TraceStartRequest,
)
from gerclaw_api.modules.document.models import (
    DocumentParseEgressFinish,
    UploadedDocumentCreate,
    UploadedDocumentRead,
)
from gerclaw_api.modules.document.service import DocumentContextError
from gerclaw_api.modules.evals import cli as eval_cli
from gerclaw_api.modules.evals import rag_cli as eval_rag_cli
from gerclaw_api.modules.memory.models import MemoryFactDecisionRequest
from gerclaw_api.modules.privacy_redaction.models import EgressPurpose, RedactionResult
from gerclaw_api.modules.rag import cli as rag_index_cli
from gerclaw_api.modules.rag import locking as rag_locking
from gerclaw_api.repositories.document import UploadedDocumentNotFoundError
from gerclaw_api.repositories.provider_egress import SqlAlchemyProviderEgressRepository
from gerclaw_api.services import model_egress_audit
from tests.conftest import make_settings


class _EvalResult:
    passed = True

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"case_id": self.case_id, "passed": self.passed}


def _result(case_id: str) -> _EvalResult:
    return _EvalResult(case_id)


def _model_prompt_decision() -> RedactionResult:
    return RedactionResult(
        text="已最小化的模型提示投影。",
        purpose=EgressPurpose.EXTERNAL_MODEL_PROMPT,
        policy_version="1.0.0",
    )


def test_safety_eval_cli_outputs_only_versioned_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(eval_cli, "run_golden_cases", lambda: (_result("safety.case"),))
    monkeypatch.setattr(
        eval_cli, "run_output_safety_golden_cases", lambda: (_result("output.case"),)
    )
    monkeypatch.setattr(
        eval_cli, "run_privacy_redaction_golden_cases", lambda: (_result("privacy.case"),)
    )
    monkeypatch.setattr(
        eval_cli, "run_medication_rule_golden_cases", lambda: (_result("medication.case"),)
    )
    monkeypatch.setattr(
        eval_cli, "run_skill_draft_golden_cases", lambda: (_result("skill-draft.case"),)
    )

    async def memory_results() -> tuple[_EvalResult, ...]:
        return (_result("memory-extraction.case"),)

    monkeypatch.setattr(eval_cli, "run_memory_extraction_golden_cases", memory_results)

    with pytest.raises(SystemExit, match="0"):
        eval_cli.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "eval-run-v1"
    assert payload["case_count"] == 6
    assert payload["passed_count"] == 6
    assert payload["external_model_or_rag"] is False


@pytest.mark.asyncio
async def test_rag_index_command_closes_runtime_and_client_on_failed_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    @dataclass(frozen=True)
    class Report:
        indexed: int
        failed: int

    client = FakeClient()
    runtime = SimpleNamespace(
        indexer=SimpleNamespace(sync=AsyncMock(return_value=Report(indexed=1, failed=1))),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(rag_index_cli, "get_settings", lambda: make_settings())
    monkeypatch.setattr(rag_index_cli, "AsyncQdrantClient", lambda **kwargs: client)
    monkeypatch.setattr(rag_index_cli, "create_rag_runtime", lambda _settings, _client: runtime)

    assert await rag_index_cli._sync() == 1
    assert json.loads(capsys.readouterr().out) == {"failed": 1, "indexed": 1}
    runtime.aclose.assert_awaited_once()
    assert client.closed is True


@pytest.mark.asyncio
async def test_model_prompt_egress_audit_records_and_finishes_only_owned_prepared_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle = SimpleNamespace(id=uuid.uuid4(), outcome="prepared")
    repositories: list[Any] = []

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            repositories.append(self)
            self.prepared: dict[str, object] | None = None
            self.finished: tuple[object, str] | None = None

        async def record_prepared_model_prompt(self, **kwargs: object) -> object:
            self.prepared = kwargs
            return handle

        async def get_model_prompt_for_owner(self, event_id: object, **kwargs: object) -> object:
            assert event_id == handle.id
            assert kwargs == {"tenant_id": "tenant_public0001", "actor_id": "usr_account_00000001"}
            return handle

        async def set_outcome(self, event: object, *, outcome: str) -> None:
            self.finished = (event, outcome)

    class FakeSession:
        commits = 0

        async def commit(self) -> None:
            self.commits += 1

    class FakeDatabase:
        def __init__(self) -> None:
            self.sessions: list[FakeSession] = []

        @asynccontextmanager
        async def session(self):  # type: ignore[no-untyped-def]
            session = FakeSession()
            self.sessions.append(session)
            yield session

    database = FakeDatabase()
    monkeypatch.setattr(model_egress_audit, "SqlAlchemyProviderEgressRepository", FakeRepository)
    audit = model_egress_audit.SqlAlchemyModelPromptEgressAudit(
        database,  # type: ignore[arg-type]
        tenant_id="tenant_public0001",
        actor_id="usr_account_00000001",
    )

    returned_handle = await audit.prepare(preference="primary", decision=_model_prompt_decision())
    await audit.finish(returned_handle, outcome="succeeded")

    assert returned_handle == handle.id
    assert repositories[0].prepared is not None
    assert repositories[0].prepared["processor"] == "model_primary"
    assert repositories[1].finished == (handle, "succeeded")
    assert [session.commits for session in database.sessions] == [1, 1]
    with pytest.raises(ValueError, match="handle"):
        await audit.finish("not-a-uuid", outcome="failed")


@pytest.mark.asyncio
async def test_admin_bootstrap_creates_only_valid_local_administrator(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: dict[str, object] = {}

    class FakeRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def create(self, **kwargs: object) -> object:
            calls["create"] = kwargs
            return SimpleNamespace(external_id="account-admin-001")

        async def record_security_event(self, **kwargs: object) -> None:
            calls["audit"] = kwargs

    class FakeSession:
        committed = False

        async def commit(self) -> None:
            self.committed = True

    class FakeDatabase:
        disposed = False

        def __init__(self, _settings: object) -> None:
            self.session_value = FakeSession()

        @asynccontextmanager
        async def session(self):  # type: ignore[no-untyped-def]
            yield self.session_value

        async def dispose(self) -> None:
            self.disposed = True

    database: FakeDatabase | None = None

    def build_database(settings: object) -> FakeDatabase:
        nonlocal database
        database = FakeDatabase(settings)
        return database

    monkeypatch.setattr(admin_bootstrap, "get_settings", lambda: make_settings())
    monkeypatch.setattr(admin_bootstrap, "Database", build_database)
    monkeypatch.setattr(admin_bootstrap, "SqlAlchemyAccountRepository", FakeRepository)
    monkeypatch.setattr(admin_bootstrap, "hash_password", lambda _password: "hashed-password")

    await admin_bootstrap._run("  AdminUser  ", "sufficient-secret")

    assert calls["create"] is not None
    assert calls["create"]["role"] == "admin"  # type: ignore[index]
    assert calls["audit"]["event_type"] == "bootstrap"  # type: ignore[index]
    assert database is not None and database.session_value.committed and database.disposed
    assert "administrator created: account-admin-001" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="username"):
        await admin_bootstrap._run("x", "sufficient-secret")
    with pytest.raises(SystemExit, match="password"):
        await admin_bootstrap._run("AdminUser", "short")


@pytest.mark.asyncio
async def test_database_rolls_back_on_error_and_closes_owned_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[object] = []

        async def execute(self, statement: object) -> None:
            self.executed.append(statement)

    class FakeEngine:
        def __init__(self) -> None:
            self.connection = FakeConnection()
            self.disposed = False

        @asynccontextmanager
        async def connect(self):  # type: ignore[no-untyped-def]
            yield self.connection

        async def dispose(self) -> None:
            self.disposed = True

    class FakeSession:
        rolled_back = False

        async def rollback(self) -> None:
            self.rolled_back = True

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    engine = FakeEngine()
    created_sessions: list[FakeSession] = []
    monkeypatch.setattr(database_session, "create_async_engine", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(
        database_session,
        "async_sessionmaker",
        lambda *_args, **_kwargs: (
            lambda: created_sessions.append(FakeSession()) or created_sessions[-1]
        ),
    )
    database = database_session.Database(make_settings())

    with pytest.raises(RuntimeError, match="rollback"):
        async with database.session():
            raise RuntimeError("rollback")
    await database.ping()
    await database.dispose()

    assert created_sessions[0].rolled_back is True
    assert len(engine.connection.executed) == 1
    assert engine.disposed is True


@pytest.mark.asyncio
async def test_postgres_rag_lock_releases_advisory_lock_and_disposes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDriverConnection:
        def __init__(self) -> None:
            self.listeners: list[object] = []

        def add_termination_listener(self, callback: object) -> None:
            self.listeners.append(callback)

        def remove_termination_listener(self, callback: object) -> None:
            self.listeners.remove(callback)

        def is_closed(self) -> bool:
            return False

    class FakeConnection:
        def __init__(self) -> None:
            self.driver = FakeDriverConnection()
            self.commits = 0
            self.scalars = iter((24, True))

        async def execute(self, _statement: object, _parameters: object) -> None:
            return None

        async def commit(self) -> None:
            self.commits += 1

        async def scalar(self, _statement: object, _parameters: object | None = None) -> object:
            return next(self.scalars)

        async def get_raw_connection(self) -> object:
            return SimpleNamespace(driver_connection=self.driver)

    class FakeEngine:
        def __init__(self) -> None:
            self.connection = FakeConnection()
            self.disposed = False

        @asynccontextmanager
        async def connect(self):  # type: ignore[no-untyped-def]
            yield self.connection

        async def dispose(self) -> None:
            self.disposed = True

    engine = FakeEngine()
    monkeypatch.setattr(rag_locking, "create_async_engine", lambda *_args, **_kwargs: engine)
    lock = rag_locking.PostgresAdvisoryRAGIndexLock("postgresql+asyncpg://example/test")

    async with lock.hold() as generation_id:
        assert generation_id.startswith("0000000000000018-")
        assert len(engine.connection.driver.listeners) == 1

    assert engine.connection.commits == 3
    assert engine.connection.driver.listeners == []
    assert engine.disposed is True


@pytest.mark.asyncio
async def test_provider_egress_repository_never_persists_prompt_text_in_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []
            self.flushed = 0

        def add(self, value: object) -> None:
            self.added.append(value)

        async def flush(self) -> None:
            self.flushed += 1

        async def scalar(self, _statement: object) -> object:
            return "owner-bound-event"

    session = FakeSession()
    repository = SqlAlchemyProviderEgressRepository(session)  # type: ignore[arg-type]
    event = await repository.record_prepared_model_prompt(
        tenant_id="tenant_public0001",
        actor_id="usr_account_00000001",
        processor="model_primary",
        decision=_model_prompt_decision(),
    )
    assert (
        await repository.get_model_prompt_for_owner(
            uuid.uuid4(), tenant_id="tenant_public0001", actor_id="usr_account_00000001"
        )
        == "owner-bound-event"
    )
    await repository.set_outcome(event, outcome="succeeded")

    assert event.findings == []
    assert event.purpose == "external_model_prompt"
    assert event.outcome == "succeeded"
    assert session.flushed == 2


def test_opt_in_rag_eval_cli_rejects_unreviewed_file_and_missing_cost_opt_in(
    tmp_path: Any,
) -> None:
    case_file = tmp_path / "cases.json"
    case_file.write_text("not-json", encoding="utf-8")
    with pytest.raises(eval_rag_cli.RAGEvaluationCliError, match="case file"):
        eval_rag_cli.load_rag_case_set(case_file)
    with pytest.raises(SystemExit, match="2"):
        eval_rag_cli.parse_args(["--cases", str(case_file), "--index-version", "test-v1"])


@pytest.mark.asyncio
async def test_application_lifespan_owns_and_closes_every_runtime_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClosable:
        def __init__(self) -> None:
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    class FakeDatabase(FakeClosable):
        async def dispose(self) -> None:
            self.closed = True

    class FakeQdrant(FakeClosable):
        async def close(self) -> None:
            self.closed = True

    class FakeRedis(FakeClosable):
        pass

    class FakeRuntime(FakeClosable):
        module = object()

    database = FakeDatabase()
    redis = FakeRedis()
    qdrant = FakeQdrant()
    rag = FakeRuntime()
    search = FakeRuntime()
    voice = FakeClosable()
    model = FakeClosable()
    cancellation = FakeClosable()
    cancellation.start = AsyncMock()  # type: ignore[attr-defined]

    monkeypatch.setattr(application, "configure_logging", lambda _level: None)
    monkeypatch.setattr(application, "configure_field_encryption", lambda **_kwargs: None)
    monkeypatch.setattr(application, "Database", lambda _settings: database)
    monkeypatch.setattr(application.Redis, "from_url", lambda *_args, **_kwargs: redis)
    monkeypatch.setattr(application, "AsyncQdrantClient", lambda **_kwargs: qdrant)
    monkeypatch.setattr(application, "create_rag_runtime", lambda _settings, _qdrant: rag)
    monkeypatch.setattr(application, "create_search_runtime", lambda _settings: search)
    monkeypatch.setattr(application, "create_voice_module", lambda _settings: voice)
    monkeypatch.setattr(application, "create_memory_store", lambda _settings, _qdrant: object())
    monkeypatch.setattr(application, "build_agentic_rag_middleware", lambda _module: object())
    monkeypatch.setattr(application, "ChatCancellationRegistry", lambda _redis: cancellation)
    monkeypatch.setattr(application, "FailoverChatModel", lambda _configs: model)

    app = application.create_app(make_settings(agent_model_configs=[]))
    async with app.router.lifespan_context(app):
        assert app.state.database is database
        assert app.state.redis is redis
        assert app.state.qdrant is qdrant
        assert app.state.agent_model is model
        cancellation.start.assert_awaited_once()  # type: ignore[attr-defined]

    assert all(
        item.closed for item in (database, redis, qdrant, rag, search, voice, model, cancellation)
    )


@pytest.mark.asyncio
async def test_application_exception_handlers_keep_error_codes_stable() -> None:
    app = application.create_app(make_settings())
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})

    trace_response = await app.exception_handlers[application.TraceNotFoundError](
        request, application.TraceNotFoundError("trace-001")
    )
    rate_response = await app.exception_handlers[application.RateLimitExceeded](
        request, application.RateLimitExceeded(3)
    )
    rag_response = await app.exception_handlers[application.RAGUnavailableError](
        request, application.RAGUnavailableError("unavailable")
    )

    assert trace_response.status_code == 404
    assert b"TRACE_NOT_FOUND" in trace_response.body
    assert rate_response.status_code == 429
    assert rate_response.headers["retry-after"] == "3"
    assert rag_response.status_code == 503
    assert b"RAG_UNAVAILABLE" in rag_response.body

    expected = (
        (application.ApprovalNotFoundError("approval"), 404),
        (application.ApprovalConflictError("approval"), 409),
        (application.ApprovalForbiddenError("approval"), 403),
        (application.TraceConflictError("trace"), 409),
        (application.TraceResourceLimitError("trace"), 409),
        (application.RateLimitUnavailable("redis"), 503),
        (application.SearchUnavailableError("search"), 503),
        (application.UnsafeSearchURLError("url"), 400),
        (application.SkillNotFoundError("skill"), 404),
        (application.SkillConflictError("skill"), 409),
        (application.SkillDisabledError("skill"), 409),
        (application.SkillFormatError("skill"), 422),
        (application.SkillGenerationError("skill"), 503),
        (application.CorruptSkillError("skill"), 500),
    )
    for error, status_code in expected:
        response = await app.exception_handlers[type(error)](request, error)
        assert response.status_code == status_code


@pytest.mark.asyncio
async def test_opt_in_rag_eval_cli_constructs_production_runtime_and_always_closes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    class FakeClosable:
        closed = False

        async def aclose(self) -> None:
            self.closed = True

        async def close(self) -> None:
            self.closed = True

    qdrant = FakeClosable()
    runtime = FakeClosable()
    runtime.module = object()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        eval_rag_cli, "load_rag_case_set", lambda _path: SimpleNamespace(cases=("case",))
    )
    monkeypatch.setattr(eval_rag_cli, "get_settings", lambda: make_settings())
    monkeypatch.setattr(eval_rag_cli, "AsyncQdrantClient", lambda **_kwargs: qdrant)
    monkeypatch.setattr(eval_rag_cli, "create_rag_runtime", lambda _settings, _qdrant: runtime)
    monkeypatch.setattr(
        eval_rag_cli,
        "run_opt_in_rag_retrieval_evaluation",
        AsyncMock(return_value=SimpleNamespace(model_dump=lambda *, mode: {"passed_count": 1})),
    )

    args = SimpleNamespace(
        cases=tmp_path / "reviewed.json", index_version="index-v1", top_k=3, max_cases=1
    )
    assert await eval_rag_cli.run(args) == {"passed_count": 1}
    assert runtime.closed is True
    assert qdrant.closed is True


@pytest.mark.asyncio
async def test_approval_and_alert_routes_delegate_with_verified_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    session = SimpleNamespace(commit=AsyncMock())
    record = SimpleNamespace(arguments={"safe": "value"})
    calls: list[str] = []

    class ApprovalRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_for_requester(self, *_args: object, **_kwargs: object) -> object:
            calls.append("requester")
            return record

        async def get_for_approver(self, *_args: object, **_kwargs: object) -> object:
            calls.append("approver")
            return record

    class ApprovalService:
        def __init__(self, _repository: object) -> None:
            pass

        async def decide(self, *_args: object, **_kwargs: object) -> object:
            calls.append("decide")
            return record

        async def cancel(self, *_args: object, **_kwargs: object) -> object:
            calls.append("cancel")
            return record

    class AlertService:
        def __init__(self, _repository: object) -> None:
            pass

        async def list(self, **_kwargs: object) -> object:
            calls.append("list")
            return record

        async def acknowledge(self, **_kwargs: object) -> object:
            calls.append("acknowledge")
            return record

    monkeypatch.setattr(approvals_route, "SqlAlchemyApprovalRepository", ApprovalRepository)
    monkeypatch.setattr(approvals_route, "ApprovalService", ApprovalService)
    monkeypatch.setattr(approvals_route.ApprovalRead, "model_validate", lambda _record: record)
    monkeypatch.setattr(
        approvals_route, "ApprovalReviewRead", lambda **kwargs: SimpleNamespace(**kwargs)
    )
    monkeypatch.setattr(
        risk_alerts_route, "SqlAlchemyRiskAlertRepository", lambda _session: object()
    )
    monkeypatch.setattr(risk_alerts_route, "RiskAlertService", AlertService)

    approval_id, alert_id = uuid.uuid4(), uuid.uuid4()
    assert await approvals_route.get_approval(approval_id, session, identity) is record
    assert (
        await approvals_route.review_approval(approval_id, session, identity)
    ).arguments == record.arguments
    assert await approvals_route.decide_approval(approval_id, object(), session, identity) is record
    assert await approvals_route.cancel_approval(approval_id, object(), session, identity) is record
    assert await risk_alerts_route.list_risk_alerts(session, identity, "active", 5) is record
    assert (
        await risk_alerts_route.acknowledge_risk_alert(
            alert_id,
            SimpleNamespace(expected_revision=1, idempotency_key="idem_0000000000000001"),
            session,
            identity,
        )
        is record
    )
    assert session.commit.await_count == 3
    assert calls == ["requester", "approver", "decide", "cancel", "list", "acknowledge"]


@pytest.mark.asyncio
async def test_document_routes_bind_documents_and_mineru_egress_to_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id, session_id, egress_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    limiter = SimpleNamespace(check=AsyncMock())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/documents",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    rate_limiter=limiter,
                    settings=SimpleNamespace(
                        mineru_supports_async_parse=True,
                        mineru_supports_markdown_export=True,
                        mineru_capability_version="mineru-capabilities-v1",
                    ),
                )
            ),
        }
    )
    session = SimpleNamespace(commit=AsyncMock())
    created = UploadedDocumentRead(
        document_id=document_id,
        session_id=session_id,
        filename="report.pdf",
        media_type="application/pdf",
        parse_source="mineru",
        status="active",
        content_characters=12,
        created_at=datetime.now(UTC),
    )
    document_service = SimpleNamespace(
        register=AsyncMock(return_value=created),
        get=AsyncMock(return_value=created),
        revoke=AsyncMock(),
    )
    required_sessions: list[uuid.UUID] = []

    async def require_session(
        _session: object, required_session_id: uuid.UUID, _identity: object
    ) -> None:
        required_sessions.append(required_session_id)

    class EgressRepository:
        def __init__(self, _session: object) -> None:
            self.event = SimpleNamespace(id=egress_id, outcome="prepared")
            self.outcomes: list[str] = []

        async def record_prepared_document_parse(self, **kwargs: object) -> object:
            assert kwargs == {
                "tenant_id": identity.tenant_id,
                "actor_id": identity.actor_id,
                "capability_version": "mineru-capabilities-v1",
            }
            return self.event

        async def get_document_parse_for_owner(self, event_id: object, **kwargs: object) -> object:
            assert event_id == egress_id
            assert kwargs == {"tenant_id": identity.tenant_id, "actor_id": identity.actor_id}
            return self.event

        async def set_outcome(self, event: object, *, outcome: str) -> None:
            assert event is self.event
            self.outcomes.append(outcome)

    monkeypatch.setattr(documents_route, "_documents", lambda _session, _request: document_service)
    monkeypatch.setattr(documents_route, "_require_session", require_session)
    monkeypatch.setattr(documents_route, "SqlAlchemyProviderEgressRepository", EgressRepository)
    payload = UploadedDocumentCreate(
        session_id=session_id,
        filename="report.pdf",
        media_type="application/pdf",
        parse_source="mineru",
        markdown="患者报告内容",
    )

    assert await documents_route.register_document(payload, request, session, identity) == created
    prepared = await documents_route.prepare_mineru_egress(request, session, identity)
    assert prepared.egress_id == egress_id
    assert (
        await documents_route.finish_mineru_egress(
            egress_id,
            DocumentParseEgressFinish(outcome="succeeded"),
            request,
            session,
            identity,
        )
        is None
    )
    assert (
        await documents_route.get_document(session_id, document_id, request, session, identity)
        == created
    )
    deleted = await documents_route.revoke_document(
        session_id, document_id, request, session, identity
    )

    assert deleted.document_id == document_id
    assert required_sessions == [session_id, session_id, session_id]
    assert session.commit.await_count == 4
    assert limiter.check.await_count == 5
    document_service.register.assert_awaited_once()
    document_service.get.assert_awaited_once()
    document_service.revoke.assert_awaited_once()


@pytest.mark.asyncio
async def test_document_egress_finish_hides_missing_or_completed_owner_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/documents/provider-egress/mineru/example",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(rate_limiter=SimpleNamespace(check=AsyncMock()))
            ),
        }
    )
    session = SimpleNamespace(commit=AsyncMock())
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")

    class MissingEgressRepository:
        def __init__(self, _session: object) -> None:
            pass

        async def get_document_parse_for_owner(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(
        documents_route, "SqlAlchemyProviderEgressRepository", MissingEgressRepository
    )
    with pytest.raises(HTTPException) as raised:
        await documents_route.finish_mineru_egress(
            uuid.uuid4(),
            DocumentParseEgressFinish(outcome="failed"),
            request,
            session,
            identity,
        )
    assert raised.value.status_code == 404
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_document_routes_translate_invalid_or_missing_owner_documents_to_safe_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_id, document_id = uuid.uuid4(), uuid.uuid4()
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/documents",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    rate_limiter=SimpleNamespace(check=AsyncMock()), settings=object()
                )
            ),
        }
    )
    session = SimpleNamespace(commit=AsyncMock())
    document_service = SimpleNamespace(
        register=AsyncMock(side_effect=DocumentContextError("invalid")),
        get=AsyncMock(side_effect=UploadedDocumentNotFoundError("missing")),
        revoke=AsyncMock(side_effect=UploadedDocumentNotFoundError("missing")),
    )
    monkeypatch.setattr(documents_route, "_documents", lambda _session, _request: document_service)
    monkeypatch.setattr(documents_route, "_require_session", AsyncMock())
    payload = UploadedDocumentCreate(
        session_id=session_id,
        filename="report.pdf",
        media_type="application/pdf",
        parse_source="mineru",
        markdown="患者报告内容",
    )

    with pytest.raises(HTTPException) as invalid:
        await documents_route.register_document(payload, request, session, identity)
    with pytest.raises(HTTPException) as missing_get:
        await documents_route.get_document(session_id, document_id, request, session, identity)
    with pytest.raises(HTTPException) as missing_delete:
        await documents_route.revoke_document(session_id, document_id, request, session, identity)

    assert invalid.value.status_code == 422
    assert missing_get.value.status_code == 404
    assert missing_delete.value.status_code == 404
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_trace_routes_preserve_identity_and_update_request_trace_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_id = "trace_abcdefgh12345678"
    identity = SimpleNamespace(
        tenant_id="tenant_public0001", actor_id="usr_account_00000001", account_role="patient"
    )
    limiter = SimpleNamespace(check=AsyncMock())
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/traces",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(rate_limiter=limiter)),
            "state": {"trace_id": trace_id, "request_id": "req_abcdefgh12345678"},
        }
    )
    trace = SimpleNamespace(actor_id=identity.actor_id, trace_id=trace_id)
    event = SimpleNamespace(trace_id=trace_id, event_id="event_abcdefgh12345678")
    feedback = SimpleNamespace(trace_id=trace_id, actor_id=identity.actor_id)
    service = SimpleNamespace(
        start_trace=AsyncMock(return_value=trace),
        get_trace=AsyncMock(return_value=trace),
        list_events=AsyncMock(return_value=([event], 4)),
        append_event=AsyncMock(return_value=event),
        finish_trace=AsyncMock(return_value=trace),
        submit_feedback=AsyncMock(return_value=feedback),
    )
    trace_read = SimpleNamespace(model_dump=lambda: {"trace_id": trace_id})

    class TraceDetail:
        def __init__(self, **kwargs: object) -> None:
            self.__dict__.update(kwargs)

    monkeypatch.setattr(traces_route.TraceRead, "model_validate", lambda _value: trace_read)
    monkeypatch.setattr(traces_route.TraceEventRead, "model_validate", lambda value: value)
    monkeypatch.setattr(traces_route.FeedbackRead, "model_validate", lambda value: value)
    monkeypatch.setattr(traces_route, "TraceDetail", TraceDetail)
    start = TraceStartRequest(execution_type="chat.request")
    trace_event = TraceEventCreate(
        event_id="event_abcdefgh12345678",
        event_type=TraceEventType.AGENT_START,
        status=TraceEventStatus.STARTED,
        payload={"channel": "chat"},
    )
    finish = TraceFinishRequest(
        idempotency_key="finish_abcdefgh12345678", status=TraceStatus.COMPLETED
    )
    feedback_payload = FeedbackCreate(
        idempotency_key="idem_abcdefgh12345678",
        trace_id=trace_id,
        rating=FeedbackRating.POSITIVE,
    )

    assert await traces_route.start_trace(start, request, service, identity) is trace_read
    detail = await traces_route.get_trace(trace_id, request, service, identity)
    assert detail.events == [event]
    assert detail.next_event_cursor == 4
    assert (
        await traces_route.append_trace_event(trace_id, trace_event, request, service, identity)
        is event
    )
    assert (
        await traces_route.finish_trace(trace_id, finish, request, service, identity) is trace_read
    )
    assert (
        await traces_route.submit_feedback(feedback_payload, request, service, identity) is feedback
    )

    assert request.state.trace_id == trace_id
    assert limiter.check.await_count == 5
    service.start_trace.assert_awaited_once_with(
        start,
        "req_abcdefgh12345678",
        trace_id=trace_id,
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
    )
    service.list_events.assert_awaited_once_with(
        identity.tenant_id, trace_id, after_sequence=0, limit=50
    )
    service.submit_feedback.assert_awaited_once_with(
        feedback_payload, tenant_id=identity.tenant_id, actor_id=identity.actor_id
    )


def test_trace_read_route_hides_a_different_owner_from_non_admin() -> None:
    identity = SimpleNamespace(actor_id="usr_account_00000001", account_role="doctor")
    with pytest.raises(traces_route.TraceNotFoundError, match="trace_abcdefgh12345678"):
        traces_route._ensure_trace_read_access(
            identity, "usr_account_00000002", "trace_abcdefgh12345678"
        )
    admin = SimpleNamespace(actor_id="usr_account_00000001", account_role="admin")
    traces_route._ensure_trace_read_access(admin, "usr_account_00000002", "trace_abcdefgh12345678")


@pytest.mark.asyncio
async def test_memory_routes_only_create_an_owner_bound_module_after_user_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    limiter = SimpleNamespace(check=AsyncMock())
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/memory/profile",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    rate_limiter=limiter,
                    settings=object(),
                    rag_runtime=SimpleNamespace(embedding_model=object()),
                    memory_store=object(),
                )
            ),
            "state": {"trace_id": "trace_abcdefgh12345678"},
        }
    )
    repository = SimpleNamespace(get_user=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())))
    module = SimpleNamespace(
        read_profile=AsyncMock(return_value=SimpleNamespace(version=3)),
        decide_fact=AsyncMock(return_value=SimpleNamespace(profile_version=4)),
        read_fact_history=AsyncMock(return_value=SimpleNamespace(items=[])),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )
    created: list[dict[str, object]] = []
    monkeypatch.setattr(memory_route, "SqlAlchemyMemoryRepository", lambda _session: repository)
    monkeypatch.setattr(memory_route, "_required_model", lambda _request: object())
    monkeypatch.setattr(
        memory_route,
        "create_memory_module",
        lambda **kwargs: created.append(kwargs) or module,
    )
    fact_id = uuid.uuid4()

    assert (
        await memory_route.get_profile(request, object(), identity)
        is module.read_profile.return_value
    )
    assert (
        await memory_route.decide_fact(
            fact_id,
            MemoryFactDecisionRequest(expected_revision=1, decision="confirm"),
            request,
            object(),
            identity,
        )
        is module.decide_fact.return_value
    )
    assert (
        await memory_route.get_fact_history(fact_id, request, object(), identity, limit=7)
        is module.read_fact_history.return_value
    )
    assert len(created) == 3
    assert all(item["tenant_id"] == identity.tenant_id for item in created)
    assert all(item["actor_id"] == identity.actor_id for item in created)
    assert all(item["trace_id"] == "trace_abcdefgh12345678" for item in created)
    module.commit.assert_awaited_once()
    module.rollback.assert_not_awaited()
    assert limiter.check.await_count == 3


@pytest.mark.asyncio
async def test_memory_routes_return_not_found_without_creating_or_mutating_foreign_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/memory/facts/example/history",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(rate_limiter=SimpleNamespace(check=AsyncMock()))
            ),
        }
    )
    repository = SimpleNamespace(get_user=AsyncMock(return_value=None))
    monkeypatch.setattr(memory_route, "SqlAlchemyMemoryRepository", lambda _session: repository)
    created = AsyncMock()
    monkeypatch.setattr(memory_route, "create_memory_module", created)
    fact_id = uuid.uuid4()

    profile = await memory_route.get_profile(request, object(), identity)
    assert profile.version == 0
    with pytest.raises(HTTPException) as decision_error:
        await memory_route.decide_fact(
            fact_id,
            MemoryFactDecisionRequest(expected_revision=1, decision="reject"),
            request,
            object(),
            identity,
        )
    with pytest.raises(HTTPException) as history_error:
        await memory_route.get_fact_history(fact_id, request, object(), identity)

    assert decision_error.value.status_code == 404
    assert history_error.value.status_code == 404
    created.assert_not_called()


def test_memory_route_fails_explicitly_when_the_configured_model_runtime_is_unavailable() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/memory/profile",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(agent_model=object())),
        }
    )
    with pytest.raises(HTTPException) as unavailable:
        memory_route._required_model(request)
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail["code"] == "MEMORY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_operations_routes_are_live_ready_and_metrics_protected() -> None:
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": "/health/ready",
        "headers": [],
    }
    scope["app"] = SimpleNamespace(
        state=SimpleNamespace(
            health_service=SimpleNamespace(check=AsyncMock(return_value={"status": "ready"})),
            rate_limiter=SimpleNamespace(check=AsyncMock()),
        )
    )
    request = Request(scope)
    identity = SimpleNamespace(tenant_id="tenant_public0001", actor_id="usr_account_00000001")
    assert await health_route.liveness() == {"status": "alive"}
    assert (await health_route.readiness(request)).status_code == 200
    assert (await health_route.metrics(request, identity)).status_code == 200
