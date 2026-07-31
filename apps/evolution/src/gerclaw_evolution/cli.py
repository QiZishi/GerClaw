"""Secret-file-only CLI for dangerous custom Skill review."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from gerclaw_api.modules.skill.offline_activation import (
    SkillActivationVerificationKey,
    SkillOfflineActivator,
)
from gerclaw_api.modules.skill.offline_bridge import (
    SkillProposalExporter,
    SkillProposalExporterKey,
    SkillProposalRecipientKey,
)
from gerclaw_api.modules.skill.offline_contracts import (
    SkillReviewEventAppend,
)
from gerclaw_api.repositories.skill_evolution_control import (
    SkillEvolutionControlConflictError,
    SkillEvolutionControlRepository,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gerclaw_evolution.approval import (
    ApprovalVerificationKeyRecord,
    HumanApprovalProof,
    HumanApprovalVerifier,
)
from gerclaw_evolution.attestation import (
    AttestationKeyRecord,
    AttestationKeyring,
    SealedEvaluatorProfile,
    SealedGateAttestation,
)
from gerclaw_evolution.contracts import CandidateControlError
from gerclaw_evolution.evaluation import PairedEvaluationGate
from gerclaw_evolution.git_repository import GitRepository
from gerclaw_evolution.runner import CaseIdentityAuthority
from gerclaw_evolution.sandbox import DockerCandidateExecutor
from gerclaw_evolution.skill_authorization import (
    SkillActivationAuthorizer,
    SkillActivationSigningKey,
)
from gerclaw_evolution.skill_operator import (
    PreparedSkillReviewPackage,
    SkillReviewOperator,
)
from gerclaw_evolution.skill_proposal import (
    SkillExportRecipientPrivateKey,
    SkillExportVerificationKey,
    SkillProposalEnvelopeOpener,
)
from gerclaw_evolution.skill_runner import SubprocessSkillPairedRunner


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gerclaw-evolution")
    commands = parser.add_subparsers(dest="command", required=True)
    pair = commands.add_parser("skill-pair")
    pair.add_argument("--proposal-id", required=True)
    _add_runner_arguments(pair)
    activate = commands.add_parser("skill-activate")
    activate.add_argument("--package", required=True)
    activate.add_argument("--sealed-attestation", required=True)
    activate.add_argument("--human-approval", required=True)
    activate.add_argument("--sealed-profile", required=True)
    _add_runner_arguments(activate)
    return parser


def _add_runner_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evaluator-repository", required=True)
    parser.add_argument("--evaluator-commit", required=True)


async def _pair(args: argparse.Namespace) -> dict[str, object]:
    settings = _settings(require_activation=False)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            control = SkillEvolutionControlRepository(session)
            envelope = await SkillProposalExporter(
                control,
                exporter_key=SkillProposalExporterKey(
                    key_id=settings.exporter_key_id,
                    private_key_seed=_secret_file(
                        "GERCLAW_EVOLUTION_EXPORTER_PRIVATE_KEY_FILE",
                        exact=32,
                    ),
                ),
                owner_binding_secret=_secret_file(
                    "GERCLAW_EVOLUTION_OWNER_BINDING_SECRET_FILE",
                    minimum=32,
                ),
                allowed_tools=settings.allowed_tools,
            ).export(
                uuid.UUID(args.proposal_id),
                recipient=SkillProposalRecipientKey(
                    key_id=settings.recipient_key_id,
                    public_key=_recipient_public_key(),
                ),
            )
            await control.commit()
        package = _operator(
            settings,
            args,
        ).pair(
            GitRepository(Path(args.evaluator_repository)),
            envelope,
        )
        if not package.paired_report.gate.passed:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                control = SkillEvolutionControlRepository(session)
                await control.append_event(
                    uuid.UUID(args.proposal_id),
                    _review_rejection(
                        event_type="paired_rejected",
                        artifact_sha256=PairedEvaluationGate.digest(package.paired_report),
                        reason_code="SKILL_PAIRED_GATE_REJECTED",
                    ),
                )
                await control.commit()
        return package.model_dump(mode="json")
    finally:
        await engine.dispose()


async def _activate(args: argparse.Namespace) -> dict[str, object]:
    settings = _settings(require_activation=True)
    package = PreparedSkillReviewPackage.model_validate_json(_public_file(args.package))
    attestation = SealedGateAttestation.model_validate_json(_public_file(args.sealed_attestation))
    approval = HumanApprovalProof.model_validate_json(_public_file(args.human_approval))
    profile = SealedEvaluatorProfile.model_validate_json(_public_file(args.sealed_profile))
    attestation_keyring = AttestationKeyring(
        (
            AttestationKeyRecord(
                key_id=_required_env("GERCLAW_EVOLUTION_ATTESTATION_KEY_ID"),
                secret=_secret_file(
                    "GERCLAW_EVOLUTION_ATTESTATION_SECRET_FILE",
                    minimum=32,
                ),
                profile=profile,
                promotion_active=True,
            ),
        )
    )
    approval_verifier = HumanApprovalVerifier(
        (
            ApprovalVerificationKeyRecord(
                key_id=_required_env("GERCLAW_EVOLUTION_APPROVAL_KEY_ID"),
                public_key=_secret_file(
                    "GERCLAW_EVOLUTION_APPROVAL_PUBLIC_KEY_FILE",
                    exact=32,
                ),
                approver_principal_id=_required_env("GERCLAW_EVOLUTION_APPROVER_PRINCIPAL_ID"),
                allowed_tracks=frozenset({"immutable"}),
                promotion_active=True,
            ),
        ),
        attestation_verifier=attestation_keyring,
    )
    activation_seed = _secret_file(
        "GERCLAW_EVOLUTION_ACTIVATION_PRIVATE_KEY_FILE",
        exact=32,
    )
    activation_public = (
        Ed25519PrivateKey.from_private_bytes(activation_seed)
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    expected_public = _secret_file(
        "GERCLAW_EVOLUTION_ACTIVATION_PUBLIC_KEY_FILE",
        exact=32,
    )
    if activation_public != expected_public:
        raise CandidateControlError("EVOLUTION_SKILL_ACTIVATION_KEYPAIR_MISMATCH")
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            operator = _operator(
                settings,
                args,
                authorizer=SkillActivationAuthorizer(
                    key=SkillActivationSigningKey(
                        key_id=settings.activation_key_id,
                        private_key_seed=activation_seed,
                        active=True,
                    ),
                    approval_verifier=approval_verifier,
                ),
                activator=SkillOfflineActivator(
                    SkillEvolutionControlRepository(session),
                    verification_key=SkillActivationVerificationKey(
                        key_id=settings.activation_key_id,
                        public_key=expected_public,
                        active=True,
                    ),
                    allowed_tools=settings.allowed_tools,
                ),
            )
            try:
                outcome = await operator.activate(
                    GitRepository(Path(args.evaluator_repository)),
                    package,
                    sealed_attestation=attestation,
                    human_approval=approval,
                )
            except CandidateControlError as error:
                if error.code == "EVOLUTION_EVALUATION_GATE_REJECTED":
                    control = SkillEvolutionControlRepository(session)
                    await control.append_event(
                        _proposal_uuid(package.paired_report.proposal_id),
                        _review_rejection(
                            event_type="sealed_rejected",
                            artifact_sha256=_artifact_digest(attestation.model_dump(mode="json")),
                            reason_code="SKILL_SEALED_GATE_REJECTED",
                        ),
                    )
                    await control.commit()
                raise
        return outcome.model_dump(mode="json")
    finally:
        await engine.dispose()


class _Settings:
    def __init__(self, *, require_activation: bool) -> None:
        self.database_url = _required_env("GERCLAW_EVOLUTION_DATABASE_URL")
        self.exporter_key_id = _required_env("GERCLAW_EVOLUTION_EXPORTER_KEY_ID")
        self.recipient_key_id = _required_env("GERCLAW_EVOLUTION_RECIPIENT_KEY_ID")
        self.activation_key_id = (
            _required_env("GERCLAW_EVOLUTION_ACTIVATION_KEY_ID")
            if require_activation
            else os.getenv("GERCLAW_EVOLUTION_ACTIVATION_KEY_ID", "").strip()
        )
        self.image_id = _required_env("GERCLAW_EVOLUTION_DOCKER_IMAGE_ID")
        allowed = {
            item.strip()
            for item in _required_env("GERCLAW_EVOLUTION_ALLOWED_TOOLS").split(",")
            if item.strip()
        }
        if not allowed:
            raise CandidateControlError("EVOLUTION_SKILL_ALLOWED_TOOLS_INVALID")
        self.allowed_tools = frozenset(allowed)


def _settings(*, require_activation: bool) -> _Settings:
    return _Settings(require_activation=require_activation)


def _operator(
    settings: _Settings,
    args: argparse.Namespace,
    *,
    authorizer: SkillActivationAuthorizer | None = None,
    activator: SkillOfflineActivator | None = None,
) -> SkillReviewOperator:
    recipient_private = _secret_file(
        "GERCLAW_EVOLUTION_RECIPIENT_PRIVATE_KEY_FILE",
        exact=32,
    )
    exporter_public = _secret_file(
        "GERCLAW_EVOLUTION_EXPORTER_PUBLIC_KEY_FILE",
        exact=32,
    )
    return SkillReviewOperator(
        opener=SkillProposalEnvelopeOpener(
            exporter_key=SkillExportVerificationKey(
                key_id=settings.exporter_key_id,
                public_key=exporter_public,
            ),
            recipient_key=SkillExportRecipientPrivateKey(
                key_id=settings.recipient_key_id,
                private_key=recipient_private,
            ),
        ),
        paired_runner=SubprocessSkillPairedRunner(
            case_identity=CaseIdentityAuthority(
                _secret_file(
                    "GERCLAW_EVOLUTION_CASE_IDENTITY_SECRET_FILE",
                    minimum=32,
                )
            ),
            executor=DockerCandidateExecutor(image_id=settings.image_id),
            evaluator_commit=args.evaluator_commit,
            allowed_tools=settings.allowed_tools,
        ),
        activation_authorizer=authorizer,
        offline_activator=activator,
    )


def _recipient_public_key() -> bytes:
    return (
        X25519PrivateKey.from_private_bytes(
            _secret_file(
                "GERCLAW_EVOLUTION_RECIPIENT_PRIVATE_KEY_FILE",
                exact=32,
            )
        )
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise CandidateControlError("EVOLUTION_OPERATOR_CONFIG_MISSING")
    return value


def _secret_file(
    env_name: str,
    *,
    exact: int | None = None,
    minimum: int | None = None,
) -> bytes:
    path = Path(_required_env(env_name))
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            mode = stat.S_IMODE(metadata.st_mode)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or mode & 0o077
            ):
                raise CandidateControlError("EVOLUTION_OPERATOR_SECRET_FILE_PERMISSIONS")
            value = stream.read()
    except CandidateControlError:
        raise
    except OSError as error:
        raise CandidateControlError("EVOLUTION_OPERATOR_SECRET_FILE_UNAVAILABLE") from error
    if exact is not None and len(value) != exact:
        raise CandidateControlError("EVOLUTION_OPERATOR_SECRET_FILE_INVALID")
    if minimum is not None and len(value) < minimum:
        raise CandidateControlError("EVOLUTION_OPERATOR_SECRET_FILE_INVALID")
    return value


def _public_file(value: str) -> bytes:
    try:
        return Path(value).read_bytes()
    except OSError as error:
        raise CandidateControlError("EVOLUTION_OPERATOR_ARTIFACT_UNAVAILABLE") from error


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = asyncio.run(_pair(args) if args.command == "skill-pair" else _activate(args))
    except (CandidateControlError, SkillEvolutionControlConflictError, ValueError) as error:
        code = (
            error.code
            if isinstance(error, CandidateControlError)
            else str(error)
            if isinstance(error, SkillEvolutionControlConflictError)
            else "EVOLUTION_OPERATOR_ARTIFACT_INVALID"
        )
        print(
            json.dumps({"status": "failed", "reason_code": code}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    except SQLAlchemyError:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason_code": "EVOLUTION_OPERATOR_DATABASE_UNAVAILABLE",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


def _review_rejection(
    *,
    event_type: Literal["paired_rejected", "sealed_rejected"],
    artifact_sha256: str,
    reason_code: str,
) -> SkillReviewEventAppend:
    return SkillReviewEventAppend.model_validate(
        {
            "event_type": event_type,
            "artifact_sha256": artifact_sha256,
            "reason_codes": [reason_code],
        }
    )


def _artifact_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proposal_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(hex=value.removeprefix("skill-proposal-"))
    except ValueError as error:
        raise CandidateControlError("EVOLUTION_SKILL_PROPOSAL_ID_INVALID") from error
