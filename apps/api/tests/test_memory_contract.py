"""Memory protocol surface must match design requirement §4.8."""

from gerclaw_api.modules.memory.protocols import MemoryModule


def test_memory_exposes_all_required_lifecycle_methods() -> None:
    for name in (
        "get_short_term",
        "get_long_term",
        "save_message",
        "extract_and_update_profile",
        "compress_context",
    ):
        assert hasattr(MemoryModule, name)
