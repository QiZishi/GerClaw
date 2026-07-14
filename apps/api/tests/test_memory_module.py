"""Medical Memory extraction, profile, vector, compression, and orchestration tests."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from agentscope.credential import CredentialBase
from agentscope.message import Msg
from agentscope.model import (
    ChatModelBase,
    ChatResponse,
    StructuredResponse,
)
from agentscope.tool import ToolChoice
from qdrant_client import AsyncQdrantClient
from starlette.requests import Request

from gerclaw_api.api.routes import memory as memory_routes
from gerclaw_api.auth import AuthContext
from gerclaw_api.database.models import (
    ConversationSession,
    HealthProfile,
    MemoryFact,
    MemoryFactRevision,
    Message,
)
from gerclaw_api.modules.memory.agentscope_adapter import (
    AgentScopeMemoryAdapterError,
    GerClawMem0Client,
)
from gerclaw_api.modules.memory.compressor import (
    AgentScopeContextCompressor,
    CompressionResult,
)
from gerclaw_api.modules.memory.extractor import MemoryExtractionError, RealMemoryExtractor
from gerclaw_api.modules.memory.memory_module import MemoryDataError, ProductionMemoryModule
from gerclaw_api.modules.memory.models import (
    ExtractedMemoryFact,
    MemoryFactDecisionRequest,
    MemoryFactDetails,
    MemoryVectorCandidate,
    MemoryVectorRecord,
)
from gerclaw_api.modules.memory.profile import empty_profile, rebuild_profile, render_core_profile
from gerclaw_api.modules.memory.protocols import MemoryMessage
from gerclaw_api.modules.memory.store import (
    MemoryStoreError,
    QdrantMemoryStore,
    memory_namespace,
    memory_point_id,
)
from gerclaw_api.repositories.memory import MemoryConflictError, MemoryNotFoundError


def _now() -> datetime:
    return datetime.now(UTC)


def _candidate(
    entity: str,
    *,
    category: str = "allergy",
    confidence: float = 0.95,
    action: str = "upsert",
    evidence: str | None = None,
    statement: str | None = None,
    occurred_at: datetime | None = None,
    details: MemoryFactDetails | None = None,
) -> ExtractedMemoryFact:
    return ExtractedMemoryFact(
        category=category,
        memory_type="stable" if category != "event" else "event",
        entity=entity,
        statement=statement or f"用户自述对{entity}过敏",
        evidence_span=evidence or f"对{entity}过敏",
        action=action,
        confidence=confidence,
        occurred_at=occurred_at,
        details=details or MemoryFactDetails(reaction="皮疹" if category == "allergy" else None),
    )


def _fact(
    *,
    user_id: uuid.UUID,
    category: str = "allergy",
    status: str = "confirmed",
    statement: str = "用户自述对青霉素过敏",
    entity: str = "青霉素",
    revision: int = 1,
) -> MemoryFact:
    now = _now()
    return MemoryFact(
        id=uuid.uuid4(),
        tenant_id="tenant_memory0001",
        user_id=user_id,
        source_session_id=None,
        source_trace_id="trace_memory_unit0001",
        category=category,
        memory_type="stable",
        fact_key=uuid.uuid4().hex,
        status=status,
        statement=statement,
        details={"entity": entity, "source": "user_self_report"},
        confidence=0.95,
        revision=revision,
        vector_revision=revision if status == "confirmed" else 0,
        confirmed_at=now if status == "confirmed" else None,
        created_at=now,
        updated_at=now,
    )


class _StructuredModel:
    def __init__(self, content: dict[str, object] | None = None, error: Exception | None = None):
        self.content = content or {"facts": []}
        self.error = error
        self.messages: list[Msg] = []

    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: object,
        **_kwargs: object,
    ) -> StructuredResponse:
        del structured_model
        self.messages = messages
        if self.error:
            raise self.error
        return StructuredResponse(content=self.content)


@pytest.mark.asyncio
async def test_real_extractor_enforces_redaction_evidence_deduplication_and_statuses() -> None:
    facts = [
        _candidate("青霉素").model_dump(mode="json"),
        _candidate("青霉素", statement="重复事实").model_dump(mode="json"),
        _candidate("头孢", evidence="不存在的证据").model_dump(mode="json"),
        _candidate(
            "阿司匹林",
            category="medication",
            confidence=0.4,
            evidence="服用阿司匹林",
        ).model_dump(mode="json"),
        _candidate("磺胺", evidence="没有磺胺过敏").model_dump(mode="json"),
        _candidate(
            "布洛芬",
            category="medication",
            action="deactivate",
            evidence="停用布洛芬",
        ).model_dump(mode="json"),
    ]
    model = _StructuredModel({"facts": facts})
    extractor = RealMemoryExtractor(cast(Any, model), min_confidence=0.8, max_facts=12)

    result = await extractor.extract(
        "手机号13812345678; 我对青霉素过敏; 目前服用阿司匹林; 我没有磺胺过敏; 我已停用布洛芬"
    )

    assert [(item.entity, status) for item, status in result] == [
        ("青霉素", "confirmed"),
        ("阿司匹林", "pending"),
        ("磺胺", "inactive"),
        ("布洛芬", "inactive"),
    ]
    model_input = "\n".join(message.get_text_content() or "" for message in model.messages)
    assert "13812345678" not in model_input
    assert "[PHONE]" in model_input

    with pytest.raises(ValueError):
        await extractor.extract(" ")
    with pytest.raises(MemoryExtractionError):
        await RealMemoryExtractor(
            cast(Any, _StructuredModel(error=RuntimeError("provider payload"))),
            min_confidence=0.8,
            max_facts=2,
        ).extract("对青霉素过敏")
    with pytest.raises(MemoryExtractionError):
        await RealMemoryExtractor(
            cast(Any, _StructuredModel({"facts": [{"bad": "shape"}]})),
            min_confidence=0.8,
            max_facts=2,
        ).extract("对青霉素过敏")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "candidate", "expected_status"),
    [
        (
            "我否认青霉素过敏",
            _candidate("青霉素", evidence="否认青霉素过敏"),
            "inactive",
        ),
        (
            "我未服用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="未服用阿司匹林",
                statement="用户自述服用阿司匹林",
            ),
            "inactive",
        ),
        (
            "我没有青霉素过敏",
            _candidate("青霉素", evidence="青霉素过敏"),
            "inactive",
        ),
        (
            "我对青霉素没有过敏反应",
            _candidate("青霉素", evidence="我对青霉素没有过敏反应"),
            "inactive",
        ),
        (
            "我对青霉素无过敏反应",
            _candidate("青霉素", evidence="我对青霉素无过敏反应"),
            "inactive",
        ),
        (
            "我未服用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="服用阿司匹林",
                statement="用户自述服用阿司匹林",
            ),
            "inactive",
        ),
        (
            "青霉素过敏史阴性",
            _candidate("青霉素", evidence="青霉素过敏史阴性"),
            "inactive",
        ),
        (
            "我没有高血压，正在服用阿司匹林",  # noqa: RUF001
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="服用阿司匹林",
                statement="用户自述服用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "阿司匹林应该怎么服用？",  # noqa: RUF001
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="阿司匹林应该怎么服用？",  # noqa: RUF001
                statement="用户自述服用阿司匹林",
            ),
            None,
        ),
        (
            "我可能有高血压",
            _candidate(
                "高血压",
                category="condition",
                evidence="我可能有高血压",
                statement="用户自述患有高血压",
            ),
            "pending",
        ),
        (
            "我父亲有高血压",
            _candidate(
                "高血压",
                category="condition",
                evidence="我父亲有高血压",
                statement="用户自述患有高血压",
            ),
            None,
        ),
        (
            "我计划服用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="我计划服用阿司匹林",
                statement="用户自述服用阿司匹林",
            ),
            None,
        ),
        (
            "我无青霉素过敏史",
            _candidate("青霉素", evidence="青霉素过敏史"),
            "inactive",
        ),
        (
            "我从没对青霉素过敏",
            _candidate("青霉素", evidence="青霉素过敏"),
            "inactive",
        ),
        (
            "我可能没有青霉素过敏",
            _candidate("青霉素", evidence="我可能没有青霉素过敏"),
            "pending",
        ),
        (
            "我好像已经不服用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="我好像已经不服用阿司匹林",
            ),
            "pending",
        ),
        (
            "我不得不服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不得不服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不能不服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不能不服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不能停用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                action="deactivate",
                evidence="我不能停用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我没有完全停用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                action="deactivate",
                evidence="我没有完全停用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我并未停用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                action="deactivate",
                evidence="我并未停用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我并没有停用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                action="deactivate",
                evidence="我并没有停用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我尚未停用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                action="deactivate",
                evidence="我尚未停用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我不仅服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不仅服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不但服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不但服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不是每天服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不是每天服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不定期服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不定期服用阿司匹林"),
            "confirmed",
        ),
        (
            "我不是只有高血压",
            _candidate("高血压", category="condition", evidence="我不是只有高血压"),
            None,
        ),
        (
            "我不是最近才确诊高血压",
            _candidate("高血压", category="condition", evidence="我不是最近才确诊高血压"),
            None,
        ),
        (
            "我不只是对青霉素过敏",
            _candidate("青霉素", evidence="我不只是对青霉素过敏"),
            None,
        ),
        (
            "我不是仅对青霉素过敏",
            _candidate("青霉素", evidence="我不是仅对青霉素过敏"),
            None,
        ),
        (
            "我不是对青霉素不过敏",
            _candidate("青霉素", action="deactivate", evidence="我不是对青霉素不过敏"),
            None,
        ),
        (
            "我正在服用阿托伐他汀",
            _candidate(
                "阿托伐他汀",
                category="medication",
                evidence="我正在服用阿托伐他汀",
                statement="用户自述服用阿托伐他汀",
            ),
            "confirmed",
        ),
        (
            "我还有高血压",
            _candidate("高血压", category="condition", evidence="我还有高血压"),
            "confirmed",
        ),
        (
            "我也有高血压",
            _candidate("高血压", category="condition", evidence="我也有高血压"),
            "confirmed",
        ),
        (
            "我自己患有高血压",
            _candidate("高血压", category="condition", evidence="我自己患有高血压"),
            "confirmed",
        ),
        (
            "我最近在服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我最近在服用阿司匹林"),
            "confirmed",
        ),
        (
            "我目前还在服用阿司匹林",
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="我目前还在服用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我常年服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我常年服用阿司匹林"),
            "confirmed",
        ),
        (
            "我每日都服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我每日都服用阿司匹林"),
            "confirmed",
        ),
        (
            "我也对青霉素过敏",
            _candidate("青霉素", evidence="我也对青霉素过敏"),
            "confirmed",
        ),
        (
            "这是我的明确健康资料：我对青霉素过敏",  # noqa: RUF001
            _candidate("青霉素", evidence="青霉素过敏"),
            "confirmed",
        ),
        (
            "我确诊过高血压",
            _candidate("高血压", category="condition", evidence="我确诊过高血压"),
            "confirmed",
        ),
        (
            "我查出过高血压",
            _candidate("高血压", category="condition", evidence="我查出过高血压"),
            "confirmed",
        ),
        (
            "我被查出高血压",
            _candidate("高血压", category="condition", evidence="我被查出高血压"),
            "confirmed",
        ),
        (
            "我和老伴都有高血压",
            _candidate("高血压", category="condition", evidence="我和老伴都有高血压"),
            "confirmed",
        ),
        (
            "医生说高血压要控制",
            _candidate(
                "高血压",
                category="condition",
                evidence="医生说高血压要控制",
                statement="用户自述患有高血压",
            ),
            None,
        ),
        (
            "我想了解高血压有哪些风险",
            _candidate(
                "高血压",
                category="condition",
                evidence="我想了解高血压有哪些风险",
                statement="用户自述患有高血压",
            ),
            None,
        ),
        (
            "我无糖尿病史",
            _candidate("糖尿病", category="condition", evidence="糖尿病"),
            "inactive",
        ),
        (
            "我不患高血压",
            _candidate("高血压", category="condition", evidence="高血压"),
            "inactive",
        ),
        (
            "我未确诊高血压",
            _candidate("高血压", category="condition", evidence="高血压"),
            "inactive",
        ),
        (
            "我对高血压还未确诊",
            _candidate("高血压", category="condition", evidence="我对高血压还未确诊"),
            "inactive",
        ),
        (
            "我对高血压没有确诊",
            _candidate("高血压", category="condition", evidence="我对高血压没有确诊"),
            "inactive",
        ),
        (
            "我对高血压尚未确诊",
            _candidate("高血压", category="condition", evidence="我对高血压尚未确诊"),
            "pending",
        ),
        (
            "我无高血压",
            _candidate("高血压", category="condition", evidence="高血压"),
            "inactive",
        ),
        (
            "我没得高血压",
            _candidate("高血压", category="condition", evidence="高血压"),
            "inactive",
        ),
        (
            "我想服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我想服用阿司匹林"),
            None,
        ),
        (
            "我不要吃阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="我不要吃阿司匹林"),
            None,
        ),
        (
            "我爷爷有高血压",
            _candidate("高血压", category="condition", evidence="我爷爷有高血压"),
            None,
        ),
        (
            "父亲目前服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="父亲目前服用阿司匹林"),
            None,
        ),
        (
            "张三正在服用阿司匹林",
            _candidate("阿司匹林", category="medication", evidence="张三正在服用阿司匹林"),
            None,
        ),
        (
            "我知道邻居有高血压",
            _candidate("高血压", category="condition", evidence="我知道邻居有高血压"),
            None,
        ),
        (
            "我照顾的老人有高血压",
            _candidate("高血压", category="condition", evidence="我照顾的老人有高血压"),
            None,
        ),
        (
            "我们医院的张三有高血压",
            _candidate("高血压", category="condition", evidence="我们医院的张三有高血压"),
            None,
        ),
        (
            "我确认张三有高血压",
            _candidate("高血压", category="condition", evidence="我确认张三有高血压"),
            None,
        ),
        (
            "我未跌倒",
            _candidate("跌倒", category="event", evidence="我未跌倒"),
            "inactive",
        ),
        (
            "我无跌倒史",
            _candidate("跌倒", category="event", evidence="我无跌倒史"),
            "inactive",
        ),
        (
            "我未做过手术",
            _candidate("手术", category="event", evidence="我未做过手术"),
            "inactive",
        ),
        (
            "我不吸烟",
            _candidate("吸烟", category="social", evidence="我不吸烟"),
            "inactive",
        ),
        (
            "我从不喝酒",
            _candidate("喝酒", category="social", evidence="我从不喝酒"),
            "inactive",
        ),
        (
            "我不需要助行器",
            _candidate("助行器", category="social", evidence="我不需要助行器"),
            "inactive",
        ),
        (
            "我不是每天吸烟",
            _candidate("吸烟", category="social", evidence="我不是每天吸烟"),
            "confirmed",
        ),
        (
            "我不常吸烟",
            _candidate("吸烟", category="social", evidence="我不常吸烟"),
            "confirmed",
        ),
        (
            "我不仅吸烟还喝酒",
            _candidate("吸烟", category="social", evidence="我不仅吸烟还喝酒"),
            "confirmed",
        ),
        (
            "我不是青霉素过敏而是头孢过敏",
            _candidate("头孢", evidence="我不是青霉素过敏而是头孢过敏"),
            "confirmed",
        ),
        (
            "我没有高血压但有糖尿病",
            _candidate(
                "糖尿病",
                category="condition",
                evidence="我没有高血压但有糖尿病",
            ),
            "confirmed",
        ),
        (
            "我未服用阿司匹林但正在服用他汀",
            _candidate(
                "他汀",
                category="medication",
                evidence="我未服用阿司匹林但正在服用他汀",
            ),
            "confirmed",
        ),
        (
            "我以前未服用阿司匹林，现在正在服用阿司匹林",  # noqa: RUF001
            _candidate(
                "阿司匹林",
                category="medication",
                evidence="现在正在服用阿司匹林",
            ),
            "confirmed",
        ),
        (
            "我以前没有青霉素过敏，但现在出现青霉素过敏",  # noqa: RUF001
            _candidate("青霉素", evidence="现在出现青霉素过敏"),
            "confirmed",
        ),
    ],
)
async def test_real_extractor_never_confirms_deterministic_negation(
    user_text: str,
    candidate: ExtractedMemoryFact,
    expected_status: str | None,
) -> None:
    extractor = RealMemoryExtractor(
        cast(Any, _StructuredModel({"facts": [candidate.model_dump(mode="json")]})),
        min_confidence=0.8,
        max_facts=2,
    )

    result = await extractor.extract(user_text)

    if expected_status is None:
        assert result == []
    else:
        assert [(fact.entity, status) for fact, status in result] == [
            (candidate.entity, expected_status)
        ]


@pytest.mark.asyncio
async def test_real_extractor_reaches_all_core_profile_categories() -> None:
    candidates = [
        _candidate(
            "年龄",
            category="basic_info",
            evidence="我的年龄是70岁",
            details=MemoryFactDetails(value="70", unit="岁"),
        ),
        _candidate(
            "血压",
            category="vital_sign",
            evidence="我的血压是130/80mmHg",
            details=MemoryFactDetails(value="130/80", unit="mmHg"),
        ),
        _candidate(
            "跌倒风险",
            category="assessment",
            evidence="我的跌倒风险评分是5分",
            details=MemoryFactDetails(value="5", unit="分"),
        ),
        _candidate(
            "髋关节手术",
            category="event",
            evidence="我去年做过髋关节手术",
            details=MemoryFactDetails(source_status="historical"),
        ),
        _candidate("独居", category="social", evidence="我是独居"),
        _candidate("每天走3000步", category="goal", evidence="我的目标是每天走3000步"),
    ]
    source = (
        "我的年龄是70岁; 我的血压是130/80mmHg; 我的跌倒风险评分是5分; "
        "我去年做过髋关节手术; 我是独居; 我的目标是每天走3000步"
    )
    extractor = RealMemoryExtractor(
        cast(
            Any,
            _StructuredModel(
                {"facts": [candidate.model_dump(mode="json") for candidate in candidates]}
            ),
        ),
        min_confidence=0.8,
        max_facts=12,
    )
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    module = _module(repository, cast(Any, extractor), _VectorStore())

    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": source}])],
    )

    assert repository.profile is not None
    profile = repository.profile.profile
    assert set(module.last_update.categories) == {
        "basic_info",
        "vital_sign",
        "assessment",
        "event",
        "social",
        "goal",
    }
    assert len(cast(dict[str, object], profile["basic_info"])) == 1
    assert len(cast(list[object], profile["vital_signs"])) == 1
    assert len(cast(dict[str, object], profile["assessments"])) == 1
    assert len(cast(list[object], profile["events"])) == 1
    assert len(cast(list[object], profile["social_context"])) == 1
    assert len(cast(list[object], profile["goals"])) == 1
    rendered, _version, _refs = await module.core_profile_context()
    assert "70岁" in rendered


@pytest.mark.asyncio
async def test_real_extractor_binds_entity_details_and_time_to_evidence() -> None:
    wrong_entity = ExtractedMemoryFact(
        category="allergy",
        memory_type="stable",
        entity="头孢",
        statement="用户自述对头孢过敏并发生过敏性休克",
        evidence_span="我对青霉素过敏",
        confidence=0.99,
        details=MemoryFactDetails(reaction="过敏性休克", severity="severe"),
        occurred_at=datetime(2024, 1, 2, tzinfo=UTC),
    )
    correct_entity_with_inventions = wrong_entity.model_copy(update={"entity": "青霉素"})
    model = _StructuredModel(
        {
            "facts": [
                wrong_entity.model_dump(mode="json"),
                correct_entity_with_inventions.model_dump(mode="json"),
            ]
        }
    )
    extractor = RealMemoryExtractor(cast(Any, model), min_confidence=0.8, max_facts=4)

    result = await extractor.extract("我对青霉素过敏")

    assert len(result) == 1
    candidate, status = result[0]
    assert (candidate.entity, status) == ("青霉素", "confirmed")
    assert candidate.details.reaction is None
    assert candidate.details.severity is None
    assert candidate.occurred_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_text", "candidates", "expected_status"),
    [
        (
            "我有高血压，刚才说错了，我没有高血压",  # noqa: RUF001
            [
                _candidate("高血压", category="condition", evidence="我有高血压"),
                _candidate("高血压", category="condition", evidence="我没有高血压"),
            ],
            "inactive",
        ),
        (
            "我以前没有高血压，但现在确诊为高血压",  # noqa: RUF001
            [
                _candidate("高血压", category="condition", evidence="我以前没有高血压"),
                _candidate("高血压", category="condition", evidence="现在确诊为高血压"),
            ],
            "confirmed",
        ),
    ],
)
async def test_real_extractor_uses_latest_valid_correction_for_same_fact(
    user_text: str,
    candidates: list[ExtractedMemoryFact],
    expected_status: str,
) -> None:
    extractor = RealMemoryExtractor(
        cast(
            Any,
            _StructuredModel(
                {"facts": [candidate.model_dump(mode="json") for candidate in candidates]}
            ),
        ),
        min_confidence=0.8,
        max_facts=4,
    )

    result = await extractor.extract(user_text)

    assert [(fact.entity, status) for fact, status in result] == [("高血压", expected_status)]


def test_profile_projection_includes_only_confirmed_and_bounded_pending() -> None:
    user_id = uuid.uuid4()
    allergy = _fact(user_id=user_id)
    medication = _fact(
        user_id=user_id,
        category="medication",
        statement="用户自述每天服用阿司匹林",
        entity="阿司匹林",
    )
    pending = _fact(user_id=user_id, status="pending", statement="用户不确定是否高血压")
    inactive = _fact(user_id=user_id, status="inactive", statement="用户已停用二甲双胍")
    basic = _fact(
        user_id=user_id,
        category="basic_info",
        statement="用户自述出生于1948年",
        entity="birth_year",
    )
    assessment = _fact(
        user_id=user_id,
        category="assessment",
        statement="用户自述跌倒风险评估待复核",
        entity="fall_risk",
    )

    profile = rebuild_profile([inactive, pending, medication, allergy, basic, assessment])

    assert len(cast(list[object], profile["allergies"])) == 1
    assert len(cast(list[object], profile["medications"])) == 1
    assert len(cast(list[object], profile["pending_items"])) == 1
    assert "birth_year" in cast(dict[str, object], profile["basic_info"])
    assert "fall_risk" in cast(dict[str, object], profile["assessments"])
    rendered = render_core_profile(profile, max_characters=5_000)
    assert "青霉素" in rendered
    assert "阿司匹林" in rendered
    assert "用户不确定" not in rendered
    assert "<untrusted-user-memory>" in rendered
    assert render_core_profile(empty_profile()) == ""


@pytest.mark.asyncio
async def test_qdrant_memory_store_has_phi_free_payload_and_strict_namespaces() -> None:
    client = AsyncQdrantClient(location=":memory:")
    store = QdrantMemoryStore(
        client,
        collection="unit_memory",
        dimensions=4,
        min_score=0.1,
    )
    user_id = uuid.uuid4()
    tenant_ns, user_ns = memory_namespace(
        b"memory-secret", tenant_id="tenant_memory0001", user_id=user_id
    )
    record = MemoryVectorRecord(
        id=uuid.uuid4(),
        category="allergy",
        status="confirmed",
        revision=3,
        statement="用户自述对青霉素过敏",
    )
    await store.upsert(
        [record],
        [[1.0, 0.0, 0.0, 0.0]],
        tenant_namespace=tenant_ns,
        user_namespace=user_ns,
    )

    points, _ = await client.scroll(
        collection_name="unit_memory", with_payload=True, with_vectors=False
    )
    assert len(points) == 1
    payload = points[0].payload or {}
    assert "statement" not in payload
    assert "青霉素" not in repr(payload)
    assert "tenant_memory0001" not in repr(payload)
    assert str(points[0].id) == str(memory_point_id(record.id, 3))
    assert await store.count() == 1

    found = await store.search(
        [1.0, 0.0, 0.0, 0.0],
        tenant_namespace=tenant_ns,
        user_namespace=user_ns,
        limit=5,
    )
    assert [(item.fact_id, item.revision) for item in found] == [(record.id, 3)]
    assert (
        await store.search(
            [1.0, 0.0, 0.0, 0.0],
            tenant_namespace=tenant_ns,
            user_namespace="0" * 64,
            limit=5,
        )
        == []
    )
    current = record.model_copy(update={"revision": 4})
    await store.upsert(
        [current],
        [[0.0, 1.0, 0.0, 0.0]],
        tenant_namespace=tenant_ns,
        user_namespace=user_ns,
    )
    assert await store.count() == 2
    assert (
        await store.search(
            [1.0, 0.0, 0.0, 0.0],
            tenant_namespace=tenant_ns,
            user_namespace=user_ns,
            limit=5,
            point_ids=[memory_point_id(record.id, 4)],
        )
        == []
    )
    current_result = await store.search(
        [0.0, 1.0, 0.0, 0.0],
        tenant_namespace=tenant_ns,
        user_namespace=user_ns,
        limit=5,
        point_ids=[memory_point_id(record.id, 4)],
    )
    assert [item.revision for item in current_result] == [4]
    await store.delete_points([memory_point_id(record.id, 4)])
    assert await store.count() == 1
    await store.delete([record.id])
    assert await store.count() == 0
    with pytest.raises(ValueError):
        await store.upsert([record], [], tenant_namespace=tenant_ns, user_namespace=user_ns)
    with pytest.raises(MemoryStoreError):
        await store.upsert([record], [[1.0]], tenant_namespace=tenant_ns, user_namespace=user_ns)
    with pytest.raises(MemoryStoreError):
        await store.search([1.0], tenant_namespace=tenant_ns, user_namespace=user_ns, limit=5)
    await client.close()


@pytest.mark.asyncio
async def test_qdrant_memory_store_force_check_recreates_deleted_collection() -> None:
    client = AsyncQdrantClient(":memory:")
    store = QdrantMemoryStore(
        client,
        collection="memory_force_check",
        dimensions=3,
        min_score=0.0,
    )

    await store.ensure_collection()
    await client.delete_collection("memory_force_check")
    await store.ensure_collection(force=True)

    assert await client.collection_exists("memory_force_check")
    await client.close()


@pytest.mark.asyncio
async def test_qdrant_memory_store_initialization_is_replica_race_safe() -> None:
    client = AsyncQdrantClient(":memory:")
    stores = [
        QdrantMemoryStore(
            client,
            collection="memory_replica_race",
            dimensions=3,
            min_score=0.0,
        )
        for _ in range(2)
    ]

    await asyncio.gather(*(store.ensure_collection(force=True) for store in stores))

    assert await client.collection_exists("memory_replica_race")
    await client.close()


class _CompressionModel(ChatModelBase):
    class Parameters(ChatModelBase.Parameters):
        pass

    def __init__(self, *, high_tokens: bool) -> None:
        self.high_tokens = high_tokens
        super().__init__(
            credential=CredentialBase(name="memory-compression-test"),
            model="compression-test",
            parameters=self.Parameters(),
            stream=False,
            max_retries=0,
            context_size=100,
        )

    async def count_tokens(self, messages: list[Msg], tools: list[dict] | None) -> int:
        del tools
        if not self.high_tokens:
            return 5
        return 10 if len(messages) <= 1 else 80

    async def generate_structured_output(
        self, messages: list[Msg], structured_model: object, **kwargs: Any
    ) -> StructuredResponse:
        del messages, structured_model, kwargs
        return StructuredResponse(
            content={
                "task_overview": "复查慢病",
                "current_state": "待评估",
                "important_discoveries": "用户自述血压偏高",
                "next_steps": "核验",
                "context_to_preserve": "尊重偏好",
                "allergies": "青霉素",
                "current_medications": "阿司匹林",
                "red_flags": "无",
                "pending_confirmations": "剂量",
            }
        )

    async def _call_api(
        self,
        model_name: str,
        messages: list[Msg],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        raise AssertionError((model_name, messages, tools, tool_choice, kwargs))


@pytest.mark.asyncio
async def test_agentscope_compressor_preserves_existing_or_generates_medical_summary() -> None:
    messages = [
        MemoryMessage(role="user", content=[{"type": "text", "text": "我对青霉素过敏"}]),
        MemoryMessage(role="assistant", content=[{"type": "text", "text": "请医生核验"}]),
    ]
    unchanged = await AgentScopeContextCompressor(_CompressionModel(high_tokens=False)).compress(
        messages, session_id=str(uuid.uuid4()), max_tokens=50, existing_summary="旧摘要"
    )
    assert unchanged.compressed is False
    assert unchanged.messages[0].role == "system"
    assert unchanged.messages[0].text() == "旧摘要"

    compressed = await AgentScopeContextCompressor(_CompressionModel(high_tokens=True)).compress(
        messages, session_id=str(uuid.uuid4()), max_tokens=30
    )
    assert compressed.compressed is True
    assert "青霉素" in compressed.summary
    assert compressed.messages[0].role == "system"
    with pytest.raises(ValueError):
        await AgentScopeContextCompressor(_CompressionModel(high_tokens=False)).compress(
            messages, session_id=str(uuid.uuid4()), max_tokens=0
        )


class _Extractor:
    def __init__(self, facts: list[tuple[ExtractedMemoryFact, str]]) -> None:
        self.facts = facts
        self.inputs: list[str] = []

    async def extract(self, text: str) -> list[tuple[ExtractedMemoryFact, str]]:
        self.inputs.append(text)
        return self.facts


class _Compressor:
    def __init__(self, *, compressed: bool = False) -> None:
        self.compressed = compressed

    async def compress(
        self,
        messages: list[MemoryMessage],
        *,
        session_id: str,
        max_tokens: int,
        existing_summary: str = "",
    ) -> CompressionResult:
        del session_id, max_tokens
        summary = "新摘要" if self.compressed else existing_summary
        projected = list(messages)
        if summary:
            projected.insert(
                0,
                MemoryMessage(role="system", content=[{"type": "text", "text": summary}]),
            )
        return CompressionResult(projected, summary, self.compressed)


class _Embedding:
    async def __call__(self, inputs: list[str]) -> Any:
        return SimpleNamespace(embeddings=[[1.0, 0.0, 0.0, 0.0] for _ in inputs])


class _VectorStore:
    def __init__(self) -> None:
        self.records: list[MemoryVectorRecord] = []
        self.candidates: list[MemoryVectorCandidate] = []
        self.deleted_point_ids: list[uuid.UUID] = []

    async def upsert(
        self,
        records: list[MemoryVectorRecord],
        vectors: list[list[float]],
        **_kwargs: object,
    ) -> None:
        assert len(records) == len(vectors)
        self.records.extend(records)

    async def search(self, _vector: list[float], **_kwargs: object) -> list[MemoryVectorCandidate]:
        return self.candidates

    async def delete_points(self, point_ids: list[uuid.UUID] | tuple[uuid.UUID, ...]) -> None:
        self.deleted_point_ids.extend(point_ids)
        deleted = set(point_ids)
        self.records = [
            record
            for record in self.records
            if memory_point_id(record.id, record.revision) not in deleted
        ]


class _Repository:
    def __init__(self, *, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        now = _now()
        self.session = ConversationSession(
            id=session_id,
            user_id=user_id,
            tenant_id="tenant_memory0001",
            agent_id="gerclaw-geriatric-specialist",
            status="active",
            context_summary={},
            created_at=now,
            updated_at=now,
        )
        self.profile: HealthProfile | None = None
        self.facts: list[MemoryFact] = []
        self.revisions: list[MemoryFactRevision] = []
        self.messages: list[Message] = []
        self.commits = 0
        self.rollbacks = 0

    async def require_session(
        self, session_id: uuid.UUID, **_kwargs: object
    ) -> ConversationSession:
        if session_id != self.session.id:
            raise MemoryNotFoundError("session")
        return self.session

    async def list_messages(self, session_id: uuid.UUID, **_kwargs: object) -> list[Message]:
        assert session_id == self.session.id
        return self.messages

    async def add_message(self, message: Message) -> None:
        message.created_at = _now()
        self.messages.append(message)

    async def get_profile(self, **_kwargs: object) -> HealthProfile | None:
        return self.profile

    async def lock_or_create_profile(self, **kwargs: object) -> HealthProfile:
        if self.profile is None:
            now = _now()
            self.profile = HealthProfile(
                id=uuid.uuid4(),
                tenant_id=cast(str, kwargs["tenant_id"]),
                user_id=cast(uuid.UUID, kwargs["user_id"]),
                schema_version=1,
                version=1,
                profile={},
                created_at=now,
                updated_at=now,
            )
        return self.profile

    async def get_fact_by_key_for_update(self, **kwargs: object) -> MemoryFact | None:
        key = cast(str, kwargs["fact_key"])
        return next((fact for fact in self.facts if fact.fact_key == key), None)

    async def get_fact_for_update(self, **kwargs: object) -> MemoryFact | None:
        fact_id = cast(uuid.UUID, kwargs["fact_id"])
        return next((fact for fact in self.facts if fact.id == fact_id), None)

    async def list_facts(
        self,
        *,
        statuses: list[str] | None = None,
        fact_ids: list[uuid.UUID] | None = None,
        **_kwargs: object,
    ) -> list[MemoryFact]:
        result = self.facts
        if statuses is not None:
            result = [fact for fact in result if fact.status in statuses]
        if fact_ids is not None:
            result = [fact for fact in result if fact.id in fact_ids]
        return list(result)

    async def add_fact(self, fact: MemoryFact) -> None:
        now = _now()
        fact.created_at = now
        fact.updated_at = now
        self.facts.append(fact)

    async def add_fact_revision(self, revision: MemoryFactRevision) -> None:
        revision.created_at = _now()
        self.revisions.append(revision)

    async def flush(self) -> None:
        now = _now()
        for fact in self.facts:
            fact.updated_at = now

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def _module(
    repository: _Repository,
    extractor: _Extractor,
    vector_store: _VectorStore,
    *,
    compressor: _Compressor | None = None,
    trace_id: str = "trace_memory_unit0001",
) -> ProductionMemoryModule:
    return ProductionMemoryModule(
        repository=cast(Any, repository),
        extractor=cast(Any, extractor),
        compressor=cast(Any, compressor or _Compressor()),
        embedding_model=cast(Any, _Embedding()),
        vector_store=cast(Any, vector_store),
        namespace_secret=b"memory-secret",
        tenant_id="tenant_memory0001",
        actor_id="usr_memory_unit0001",
        user_id=cast(uuid.UUID, repository.session.user_id),
        session_id=repository.session.id,
        trace_id=trace_id,
        retrieval_top_k=5,
        retrieval_candidates=20,
    )


@pytest.mark.asyncio
async def test_production_memory_updates_profile_retrieves_revision_and_is_idempotent() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    repository = _Repository(user_id=user_id, session_id=session_id)
    extractor = _Extractor(
        [
            (_candidate("青霉素"), "confirmed"),
            (_candidate("阿司匹林", category="medication"), "pending"),
        ]
    )
    vector_store = _VectorStore()
    module = _module(repository, extractor, vector_store)
    source = MemoryMessage(
        role="user",
        content=[{"type": "text", "text": "对青霉素过敏并服用阿司匹林"}],
    )

    await module.extract_and_update_profile("usr_memory_unit0001", [source])
    assert module.last_update.confirmed_count == 1
    assert module.last_update.pending_count == 1
    assert len(repository.facts) == 2
    assert len(vector_store.records) == 1
    assert repository.profile is not None
    assert len(cast(list[object], repository.profile.profile["allergies"])) == 1

    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="assistant", content=[{"type": "text", "text": "不应提取"}])],
    )
    assert module.last_update.profile_version == 0

    confirmed = next(fact for fact in repository.facts if fact.status == "confirmed")
    assert confirmed.statement == "用户自述: 对青霉素过敏"
    vector_store.candidates = [
        MemoryVectorCandidate(
            fact_id=confirmed.id,
            revision=confirmed.revision,
            category="allergy",
            score=0.98,
        ),
        MemoryVectorCandidate(
            fact_id=confirmed.id,
            revision=confirmed.revision + 1,
            category="allergy",
            score=0.99,
        ),
    ]
    recalled = await module.get_long_term("usr_memory_unit0001", query="我有什么过敏史")
    assert [fact.id for fact in recalled.relevant_facts] == [confirmed.id]
    assert recalled.provenance_refs == [str(confirmed.id)]
    assert await module.get_long_term("usr_memory_unit0001", query="我有什么过敏史") is recalled

    await module.extract_and_update_profile("usr_memory_unit0001", [source])
    assert module.last_update.changed_fact_ids == []
    with pytest.raises(MemoryNotFoundError):
        await module.get_long_term("other_actor", query="过敏")
    with pytest.raises(ValueError):
        await module.get_long_term("usr_memory_unit0001", query="x" * 4_001)


@pytest.mark.asyncio
async def test_distinct_dated_events_keep_separate_idempotent_fact_keys() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    first = _module(
        repository,
        _Extractor(
            [
                (
                    _candidate(
                        "跌倒",
                        category="event",
                        evidence="2024年1月2日我发生跌倒",
                        occurred_at=datetime(2024, 1, 2, tzinfo=UTC),
                    ),
                    "confirmed",
                )
            ]
        ),
        vector_store,
        trace_id="trace_event_2024",
    )
    second = _module(
        repository,
        _Extractor(
            [
                (
                    _candidate(
                        "跌倒",
                        category="event",
                        evidence="2025年1月2日我发生跌倒",
                        occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
                    ),
                    "confirmed",
                )
            ]
        ),
        vector_store,
        trace_id="trace_event_2025",
    )

    message = MemoryMessage(role="user", content=[{"type": "text", "text": "跌倒事件"}])
    await first.extract_and_update_profile("usr_memory_unit0001", [message])
    await first.commit()
    await second.extract_and_update_profile("usr_memory_unit0001", [message])
    await second.commit()
    await first.extract_and_update_profile("usr_memory_unit0001", [message])

    assert len(repository.facts) == 2
    assert len({fact.fact_key for fact in repository.facts}) == 2
    assert {fact.occurred_at for fact in repository.facts} == {
        datetime(2024, 1, 2, tzinfo=UTC),
        datetime(2025, 1, 2, tzinfo=UTC),
    }
    assert first.last_update.changed_fact_ids == []
    assert repository.profile is not None
    assert len(cast(list[object], repository.profile.profile["events"])) == 2


@pytest.mark.asyncio
async def test_fact_mutation_preserves_encrypted_revision_audit_projection() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    first = _module(
        repository,
        _Extractor(
            [
                (
                    _candidate(
                        "阿司匹林",
                        category="medication",
                        evidence="我每日服用阿司匹林100mg",
                        details=MemoryFactDetails(
                            dose="100mg", frequency="每日", source_status="active"
                        ),
                    ),
                    "confirmed",
                )
            ]
        ),
        vector_store,
        trace_id="trace_medication_active",
    )
    await first.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "服药"}])],
    )
    await first.commit()
    second = _module(
        repository,
        _Extractor(
            [
                (
                    _candidate(
                        "阿司匹林",
                        category="medication",
                        action="deactivate",
                        evidence="我已停用阿司匹林",
                        details=MemoryFactDetails(source_status="stopped"),
                    ),
                    "inactive",
                )
            ]
        ),
        vector_store,
        trace_id="trace_medication_stopped",
    )

    await second.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "停药"}])],
    )

    fact = repository.facts[0]
    assert (fact.status, fact.revision, fact.source_trace_id) == (
        "inactive",
        2,
        "trace_medication_stopped",
    )
    assert len(repository.revisions) == 1
    history = repository.revisions[0]
    assert (history.fact_id, history.revision) == (fact.id, 1)
    assert history.snapshot["status"] == "confirmed"
    assert history.snapshot["source_trace_id"] == "trace_medication_active"
    assert cast(dict[str, object], history.snapshot["details"])["dose"] == "100mg"


@pytest.mark.asyncio
async def test_memory_decision_route_compensates_vector_after_post_upsert_database_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    pending = _fact(user_id=cast(uuid.UUID, repository.session.user_id), status="pending")
    repository.facts.append(pending)
    module = _module(repository, _Extractor([]), vector_store)

    async def failing_flush() -> None:
        raise RuntimeError("database flush failed after vector upsert")

    repository.flush = failing_flush  # type: ignore[method-assign]

    class _RouteRepository:
        async def get_user(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(id=repository.session.user_id)

    class _RateLimiter:
        async def check(self, **_kwargs: object) -> None:
            return None

    app = SimpleNamespace(
        state=SimpleNamespace(
            rate_limiter=_RateLimiter(),
            settings=object(),
            rag_runtime=SimpleNamespace(embedding_model=object()),
            memory_store=object(),
        )
    )
    request = Request({"type": "http", "app": app})
    request.state.trace_id = "trace_memory_route_failure"
    identity = AuthContext(
        tenant_id="tenant_memory0001",
        actor_id="usr_memory_unit0001",
        scopes=frozenset({"memory:write"}),
    )
    monkeypatch.setattr(
        memory_routes, "SqlAlchemyMemoryRepository", lambda _session: _RouteRepository()
    )
    monkeypatch.setattr(memory_routes, "_required_model", lambda _request: cast(Any, object()))
    monkeypatch.setattr(memory_routes, "create_memory_module", lambda **_kwargs: module)

    with pytest.raises(RuntimeError, match="database flush failed after vector upsert"):
        await memory_routes.decide_fact(
            pending.id,
            MemoryFactDecisionRequest(expected_revision=1, decision="confirm"),
            request,
            cast(Any, object()),
            identity,
        )

    assert repository.commits == 0
    assert repository.rollbacks == 1
    assert repository.profile is not None
    assert repository.profile.version == 1
    assert vector_store.records == []
    assert vector_store.deleted_point_ids == [memory_point_id(pending.id, 2)]


@pytest.mark.asyncio
async def test_negative_fact_is_inactive_and_cannot_be_confirmed_or_injected() -> None:
    user_id = uuid.uuid4()
    repository = _Repository(user_id=user_id, session_id=uuid.uuid4())
    candidate = _candidate("青霉素", evidence="青霉素过敏")
    extractor = RealMemoryExtractor(
        cast(
            Any,
            _StructuredModel({"facts": [candidate.model_dump(mode="json")]}),
        ),
        min_confidence=0.8,
        max_facts=2,
    )
    vector_store = _VectorStore()
    module = _module(repository, cast(Any, extractor), vector_store)

    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "我没有青霉素过敏"}])],
    )

    assert len(repository.facts) == 1
    negative = repository.facts[0]
    assert negative.status == "inactive"
    assert negative.details["polarity"] == "negative"
    assert vector_store.records == []
    assert repository.profile is not None
    assert cast(list[object], repository.profile.profile["allergies"]) == []
    with pytest.raises(MemoryConflictError, match="does not accept"):
        await module.decide_fact(
            negative.id,
            MemoryFactDecisionRequest(expected_revision=1, decision="confirm"),
        )
    rendered, _version, _refs = await module.core_profile_context()
    assert "青霉素" not in rendered
    assert vector_store.records == []


@pytest.mark.asyncio
async def test_memory_commit_failure_compensates_only_current_fenced_vector_points() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    module = _module(
        repository,
        _Extractor([(_candidate("青霉素"), "confirmed")]),
        vector_store,
    )

    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "我对青霉素过敏"}])],
    )
    fact = repository.facts[0]
    expected_point = memory_point_id(fact.id, fact.revision)
    assert len(vector_store.records) == 1

    async def failing_commit() -> None:
        raise RuntimeError("database commit failed")

    repository.commit = failing_commit  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="database commit failed"):
        await module.commit()
    await module.compensate_uncommitted_vectors()

    assert vector_store.deleted_point_ids == [expected_point]
    assert vector_store.records == []


@pytest.mark.asyncio
async def test_uncertain_updates_never_downgrade_an_existing_confirmed_fact() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    extractor = _Extractor([(_candidate("青霉素"), "confirmed")])
    vector_store = _VectorStore()
    module = _module(repository, extractor, vector_store)

    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "我对青霉素过敏"}])],
    )
    await module.commit()
    fact = repository.facts[0]
    original = (fact.revision, fact.vector_revision, fact.statement, dict(fact.details))

    extractor.facts = [
        (
            _candidate(
                "青霉素",
                action="deactivate",
                evidence="我可能没有青霉素过敏",
            ),
            "pending",
        )
    ]
    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [
            MemoryMessage(
                role="user",
                content=[{"type": "text", "text": "我可能没有青霉素过敏"}],
            )
        ],
    )
    extractor.facts = [(_candidate("青霉素", evidence="我可能有青霉素过敏"), "pending")]
    await module.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "我可能有青霉素过敏"}])],
    )

    assert (fact.status, fact.revision, fact.vector_revision) == (
        "confirmed",
        original[0],
        original[1],
    )
    assert (fact.statement, fact.details) == (original[2], original[3])
    assert len(vector_store.records) == 1
    assert repository.profile is not None
    assert len(cast(list[object], repository.profile.profile["allergies"])) == 1
    assert module.last_update.changed_fact_ids == []


@pytest.mark.asyncio
async def test_continued_use_never_retires_an_existing_confirmed_medication() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    first = _module(
        repository,
        _Extractor(
            [
                (
                    _candidate(
                        "阿司匹林",
                        category="medication",
                        evidence="我服用阿司匹林",
                        statement="用户自述服用阿司匹林",
                    ),
                    "confirmed",
                )
            ]
        ),
        vector_store,
    )
    await first.extract_and_update_profile(
        "usr_memory_unit0001",
        [MemoryMessage(role="user", content=[{"type": "text", "text": "我服用阿司匹林"}])],
    )
    await first.commit()

    candidate = _candidate(
        "阿司匹林",
        category="medication",
        action="deactivate",
        evidence="我没有完全停用阿司匹林",
    )
    extractor = RealMemoryExtractor(
        cast(
            Any,
            _StructuredModel({"facts": [candidate.model_dump(mode="json")]}),
        ),
        min_confidence=0.8,
        max_facts=2,
    )
    second = _module(repository, cast(Any, extractor), vector_store)
    await second.extract_and_update_profile(
        "usr_memory_unit0001",
        [
            MemoryMessage(
                role="user",
                content=[{"type": "text", "text": "我没有完全停用阿司匹林"}],
            )
        ],
    )

    medication = repository.facts[0]
    assert (medication.status, medication.revision, medication.vector_revision) == (
        "confirmed",
        2,
        2,
    )
    assert repository.profile is not None
    assert len(cast(list[object], repository.profile.profile["medications"])) == 1
    assert second.last_update.confirmed_count == 1


@pytest.mark.asyncio
async def test_memory_short_term_compression_decision_and_adapter_fail_closed() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    repository = _Repository(user_id=user_id, session_id=session_id)
    repository.messages = [
        Message(
            id=uuid.uuid4(),
            tenant_id="tenant_memory0001",
            session_id=session_id,
            trace_id="trace_old_memory0001",
            role="user",
            content=[{"type": "text", "text": "既往消息"}],
            message_metadata={},
            created_at=_now(),
        ),
        Message(
            id=uuid.uuid4(),
            tenant_id="tenant_memory0001",
            session_id=session_id,
            trace_id="trace_memory_unit0001",
            role="assistant",
            content=[{"type": "text", "text": "本轮应排除"}],
            message_metadata={},
            created_at=_now(),
        ),
    ]
    vector_store = _VectorStore()
    module = _module(
        repository,
        _Extractor([]),
        vector_store,
        compressor=_Compressor(compressed=True),
    )
    short = await module.get_short_term(str(session_id), max_turns=2)
    assert [item.text() for item in short] == ["既往消息"]
    compressed = await module.compress_context(short, max_tokens=100)
    assert compressed[0].role == "system"
    assert cast(dict[str, object], repository.session.context_summary)["text"] == "新摘要"

    pending = _fact(user_id=user_id, status="pending")
    repository.facts.append(pending)
    decision = await module.decide_fact(
        pending.id,
        MemoryFactDecisionRequest(expected_revision=1, decision="confirm"),
    )
    assert decision.fact.status == "confirmed"
    assert decision.fact.revision == 2
    assert len(repository.revisions) == 1
    assert repository.revisions[0].snapshot["status"] == "pending"
    assert vector_store.records[-1].revision == 2
    with pytest.raises(MemoryConflictError, match="does not accept"):
        await module.decide_fact(
            pending.id,
            MemoryFactDecisionRequest(expected_revision=2, decision="confirm"),
        )
    with pytest.raises(MemoryConflictError):
        await module.decide_fact(
            pending.id,
            MemoryFactDecisionRequest(expected_revision=1, decision="reject"),
        )
    with pytest.raises(MemoryNotFoundError):
        await module.decide_fact(
            uuid.uuid4(),
            MemoryFactDecisionRequest(expected_revision=1, decision="reject"),
        )

    profile = await module.read_profile()
    assert profile.facts[0].statement
    rendered, version, refs = await module.core_profile_context()
    assert "青霉素" in rendered
    assert version >= 1
    assert refs == []
    await module.save_message(
        str(session_id),
        MemoryMessage(role="user", content=[{"type": "text", "text": "补充消息"}]),
    )
    assert repository.commits == 1
    await module.commit()
    await module.rollback()
    assert (repository.commits, repository.rollbacks) == (2, 1)

    adapter = GerClawMem0Client(
        module,
        actor_id="usr_memory_unit0001",
        source_user_message="我今天感觉不错",
    )
    vector_store.candidates = [
        MemoryVectorCandidate(
            fact_id=pending.id,
            revision=pending.revision,
            category="allergy",
            score=0.9,
        )
    ]
    assert (await adapter.search("过敏", filters={"user_id": "usr_memory_unit0001"}, top_k=5))[
        "results"
    ]
    write = await adapter.add([], user_id="usr_memory_unit0001")
    assert write["results"][0]["id"] == "no-op"
    assert await adapter.add([], user_id="usr_memory_unit0001") == write

    invalid_search = GerClawMem0Client(
        module,
        actor_id="usr_memory_unit0001",
        source_user_message="无新增资料",
    )
    with pytest.raises(AgentScopeMemoryAdapterError):
        await invalid_search.search("过敏", filters={"user_id": "other"}, top_k=5)
    with pytest.raises(AgentScopeMemoryAdapterError):
        invalid_search.raise_if_failed()

    invalid_limit = GerClawMem0Client(
        module,
        actor_id="usr_memory_unit0001",
        source_user_message="无新增资料",
    )
    with pytest.raises(AgentScopeMemoryAdapterError):
        await invalid_limit.search("过敏", filters={"user_id": "usr_memory_unit0001"}, top_k=21)
    with pytest.raises(AgentScopeMemoryAdapterError):
        invalid_limit.raise_if_failed()

    invalid_write = GerClawMem0Client(
        module,
        actor_id="usr_memory_unit0001",
        source_user_message="无新增资料",
    )
    with pytest.raises(AgentScopeMemoryAdapterError):
        await invalid_write.add([], user_id="other")
    with pytest.raises(AgentScopeMemoryAdapterError):
        invalid_write.raise_if_failed()


@pytest.mark.asyncio
async def test_memory_rejects_corrupt_encrypted_shapes_and_invalid_identity() -> None:
    repository = _Repository(user_id=uuid.uuid4(), session_id=uuid.uuid4())
    vector_store = _VectorStore()
    module = _module(repository, _Extractor([]), vector_store)
    repository.session.context_summary = cast(Any, "corrupt")
    with pytest.raises(MemoryDataError):
        await module.compress_context([], max_tokens=100)
    with pytest.raises(ValueError):
        await module.get_short_term("not-a-uuid")
    with pytest.raises(MemoryNotFoundError):
        await module.get_short_term(str(uuid.uuid4()))
    with pytest.raises(ValueError):
        await module.get_short_term(str(repository.session.id), max_turns=0)
