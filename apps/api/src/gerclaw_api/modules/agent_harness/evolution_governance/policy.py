"""Fail-closed policy decisions over the trusted dual-track manifest."""

from __future__ import annotations

from types import MappingProxyType

from gerclaw_api.modules.agent_harness.evolution_governance.contracts import (
    CandidateProposal,
    ComponentCharter,
    EvolutionGovernanceError,
    EvolutionObjectRule,
    GovernanceTrack,
    OnlineMutationRequest,
)
from gerclaw_api.modules.agent_harness.evolution_governance.manifest import (
    COMPONENT_CHARTERS,
    OBJECT_RULES,
)

_RULES_BY_KIND = MappingProxyType({rule.object_kind: rule for rule in OBJECT_RULES})
_CHARTERS_BY_COMPONENT = MappingProxyType(
    {charter.component: charter for charter in COMPONENT_CHARTERS}
)
if len(_RULES_BY_KIND) != len(OBJECT_RULES):
    raise RuntimeError("evolution governance manifest contains duplicate object kinds")
if len(_CHARTERS_BY_COMPONENT) != len(COMPONENT_CHARTERS):
    raise RuntimeError("evolution governance manifest contains duplicate component charters")


class EvolutionGovernancePolicy:
    """Read-only classifier; it never writes candidates or production content."""

    __slots__ = ()

    def rule_for(self, object_kind: str) -> EvolutionObjectRule:
        """Unknown classes default to immutable and cannot mutate online."""

        rule = _RULES_BY_KIND.get(object_kind)
        if rule is not None:
            return rule
        return EvolutionObjectRule(
            object_kind=object_kind,
            track="immutable",
            authority="control_plane",
            owner="sealed_release_controller",
            update_policy="sealed_controller_only",
            candidate_readable=False,
            candidate_writable=False,
        )

    def charter_for(self, component: str) -> ComponentCharter:
        charter = _CHARTERS_BY_COMPONENT.get(component)
        if charter is None:
            raise EvolutionGovernanceError("EVOLUTION_CHARTER_UNKNOWN")
        return charter

    def classify_online_mutation(
        self,
        request: OnlineMutationRequest,
    ) -> EvolutionObjectRule:
        rule = self.rule_for(request.object_kind)
        if rule.track != "mutable" or rule.update_policy != "online_revisioned":
            raise EvolutionGovernanceError("EVOLUTION_ONLINE_CLASSIFICATION_FORBIDDEN")
        if request.requested_authority != rule.authority:
            raise EvolutionGovernanceError("EVOLUTION_AUTHORITY_ESCALATION")
        return rule

    def validate_candidate(
        self,
        proposal: CandidateProposal,
    ) -> tuple[EvolutionObjectRule, ...]:
        rules = tuple(self.rule_for(change.object_kind) for change in proposal.changes)
        tracks = {rule.track for rule in rules}
        if len(tracks) != 1:
            raise EvolutionGovernanceError("EVOLUTION_MIXED_TRACK_CANDIDATE")
        if proposal.declared_track not in tracks:
            raise EvolutionGovernanceError("EVOLUTION_DECLARED_TRACK_MISMATCH")
        if any(not rule.candidate_writable for rule in rules):
            raise EvolutionGovernanceError("EVOLUTION_SEALED_ASSET_FORBIDDEN")
        if any(
            not any(change.target.startswith(prefix) for prefix in rule.allowed_target_prefixes)
            for change, rule in zip(proposal.changes, rules, strict=True)
        ):
            raise EvolutionGovernanceError("EVOLUTION_TARGET_AUTHORITY_MISMATCH")
        targets = [change.target for change in proposal.changes]
        if len(targets) != len(set(targets)):
            raise EvolutionGovernanceError("EVOLUTION_DUPLICATE_TARGET")
        return rules

    @staticmethod
    def approval_required(
        track: GovernanceTrack,
        *,
        deployment_requires_approval: bool,
    ) -> bool:
        return track == "immutable" or deployment_requires_approval
