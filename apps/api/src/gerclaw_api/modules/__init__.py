"""Independent capability module contracts aligned with design requirement chapter 4."""

from gerclaw_api.modules.agent_harness.protocols import AgentHarness
from gerclaw_api.modules.contracts import AgentRequest, AgentResponse
from gerclaw_api.modules.input_output.protocols import InputOutputModule
from gerclaw_api.modules.memory.protocols import MemoryModule
from gerclaw_api.modules.rag.protocols import RAGModule
from gerclaw_api.modules.skill.protocols import SkillModule
from gerclaw_api.modules.tools.protocols import ToolModule

__all__ = [
    "AgentHarness",
    "AgentRequest",
    "AgentResponse",
    "InputOutputModule",
    "MemoryModule",
    "RAGModule",
    "SkillModule",
    "ToolModule",
]
