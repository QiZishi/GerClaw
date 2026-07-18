"""Cross-stack regression tests for environment-owned provider model IDs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / ".env.example").is_file() and (parent / "apps/mvp").is_dir()
    ),
    None,
)
pytestmark = pytest.mark.skipif(
    ROOT is None,
    reason="repository-level configuration is not included in the isolated API test image",
)
MODEL_KEYS = {
    "AGENT_PRIMARY_MODEL",
    "AGENT_BACKUP1_MODEL",
    "AGENT_BACKUP2_MODEL",
    "ASR_MODEL",
    "TTS_MODEL",
    "EMBEDDING_MODEL",
    "RERANK_MODEL",
}


def _example_model_ids() -> set[str]:
    assert ROOT is not None
    values: set[str] = set()
    for raw_line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in MODEL_KEYS and value:
            values.add(value)
    return values


def test_provider_model_ids_are_not_hard_coded_in_production_sources() -> None:
    assert ROOT is not None
    source_roots = (
        ROOT / "apps/api/src",
        ROOT / "apps/mvp/src",
        ROOT / "apps/mvp/scripts",
    )
    model_ids = _example_model_ids()
    issues: list[str] = []
    for source_root in source_roots:
        for path in source_root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"} or "generated" in path.parts:
                continue
            content = path.read_text(encoding="utf-8")
            for model_id in model_ids:
                if model_id in content:
                    issues.append(f"{path.relative_to(ROOT)} -> {model_id}")
    assert issues == []


def test_cga_audio_generator_requires_environment_model_and_voice() -> None:
    assert ROOT is not None
    script = ROOT / "apps/mvp/scripts/generate_cga_audio_assets.py"
    spec = importlib.util.spec_from_file_location("generate_cga_audio_assets_contract", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.tts_release_configuration(
        {"TTS_MODEL": "configured-model", "TTS_VOICE": "configured-voice"}
    ) == ("configured-model", "configured-voice")
    with pytest.raises(RuntimeError, match="TTS_MODEL"):
        module.tts_release_configuration({})
