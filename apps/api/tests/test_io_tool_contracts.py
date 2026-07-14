"""Input/output and tool contracts remain independently replaceable."""

from gerclaw_api.modules.input_output.protocols import InputOutputModule
from gerclaw_api.modules.tools.protocols import ToolModule


def test_io_and_tool_boundaries_are_independent() -> None:
    assert hasattr(InputOutputModule, "normalize")
    assert hasattr(InputOutputModule, "render")
    assert hasattr(ToolModule, "execute")
