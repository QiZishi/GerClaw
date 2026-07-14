"""Agent Harness protocol surface must match design requirement §4.6."""

from gerclaw_api.modules.agent_harness.protocols import AgentHarness, StreamEvent


def test_agent_harness_exposes_context_and_stream_methods() -> None:
    assert hasattr(AgentHarness, "process_message")
    assert hasattr(AgentHarness, "assemble_context")
    assert "thinking" not in StreamEvent.model_fields["event_type"].annotation.__args__
