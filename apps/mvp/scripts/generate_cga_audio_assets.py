#!/usr/bin/env python3
# ruff: noqa: E402, I001, RUF001
"""Generate version-bound CGA speech assets with the configured live TTS provider.

This is an explicit release-time operation, not a request-path fallback.  It
reads the immutable Python scale definitions, writes WAV files below
``public/audio/cga`` and emits a manifest with source/version/text hashes.
No patient data is read, sent to the provider, or written to the manifest.

Run from the repository root:

    python3 apps/mvp/scripts/generate_cga_audio_assets.py --confirm-live-provider

The command deliberately refuses to contact the provider unless the explicit
confirmation flag is supplied, because generation has a provider cost.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[3]
API_SOURCE = ROOT / "apps" / "api" / "src"
PUBLIC_AUDIO_ROOT = ROOT / "apps" / "mvp" / "public" / "audio" / "cga"
MANIFEST_PATH = PUBLIC_AUDIO_ROOT / "manifest.json"
CLIENT_MANIFEST_PATH = ROOT / "apps" / "mvp" / "src" / "generated" / "cgaAudioManifest.ts"

sys.path.insert(0, str(API_SOURCE))

from gerclaw_api.modules.cga.phq9 import (
    PHQ9_OPTIONS,
    PHQ9_QUESTIONS,
    PHQ9_SCALE_ID,
    PHQ9_VERSION,
)
from gerclaw_api.modules.cga.psqi import (
    PSQI_QUESTIONS,
    PSQI_SCALE_ID,
    PSQI_VERSION,
    psqi_options_for,
)
from gerclaw_api.modules.cga.sas import (
    SAS_OPTIONS,
    SAS_QUESTIONS,
    SAS_SCALE_ID,
    SAS_VERSION,
)


@dataclass(frozen=True)
class QuestionDefinition:
    scale_id: str
    definition_version: str
    question_id: str
    text: str
    sensitive_prefix: str | None
    input_kind: str
    options: tuple[tuple[int, str], ...]


def read_environment() -> dict[str, str]:
    """Load local configuration without printing credential values."""

    values = dict(os.environ)
    for environment_file in (
        ROOT / ".env",
        ROOT / "apps" / "mvp" / ".env",
        ROOT / "apps" / "mvp" / ".env.local",
    ):
        if not environment_file.is_file():
            continue
        for raw_line in environment_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def scale_questions() -> tuple[QuestionDefinition, ...]:
    definitions: list[QuestionDefinition] = []
    definitions.extend(
        QuestionDefinition(
            PHQ9_SCALE_ID,
            PHQ9_VERSION,
            question.id,
            question.text,
            question.sensitive_prefix,
            "ordinal",
            PHQ9_OPTIONS,
        )
        for question in PHQ9_QUESTIONS
    )
    definitions.extend(
        QuestionDefinition(
            SAS_SCALE_ID,
            SAS_VERSION,
            question.id,
            question.text,
            None,
            "ordinal",
            SAS_OPTIONS,
        )
        for question in SAS_QUESTIONS
    )
    definitions.extend(
        QuestionDefinition(
            PSQI_SCALE_ID,
            PSQI_VERSION,
            question.id,
            question.text,
            None,
            question.input_kind,
            psqi_options_for(question.id),
        )
        for question in PSQI_QUESTIONS
    )
    return tuple(definitions)


def spoken_question(definition: QuestionDefinition) -> str:
    parts = [part for part in (definition.sensitive_prefix, definition.text) if part]
    if definition.options:
        parts.extend(["可选择的答案有", *(label for _, label in definition.options)])
    elif definition.input_kind == "clock_minutes":
        parts.append("请直接填写具体时间")
    elif definition.input_kind == "duration_minutes":
        parts.append("请填写实际睡眠时长")
    return "。".join(parts) + "。"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def option_path(scale_id: str, definition_version: str, label: str) -> Path:
    # Identical labels deliberately share one immutable asset. The manifest
    # retains the question/ordinal mapping so this does not lose semantics.
    return Path(scale_id) / definition_version / "options" / f"{sha256_text(label)[:20]}.wav"


def question_path(definition: QuestionDefinition) -> Path:
    return (
        Path(definition.scale_id)
        / definition.definition_version
        / "questions"
        / f"{definition.question_id}.wav"
    )


def tts_wav(text: str, environment: dict[str, str], *, attempts: int = 4) -> bytes:
    tts_url = environment.get("MIMO_TTS_URL") or environment.get("TTS_URL")
    api_key = environment.get("MIMO_API_KEY") or environment.get("TTS_API_KEY")
    if not tts_url or not api_key:
        raise RuntimeError(
            "缺少 MIMO_TTS_URL/TTS_URL 或 MIMO_API_KEY/TTS_API_KEY，无法生成预录制音频。"
        )

    model = environment.get("MIMO_TTS_MODEL") or environment.get("TTS_MODEL") or "mimo-v2.5-tts"
    voice = environment.get("TTS_VOICE") or "冰糖"
    authorization_header = environment.get("GERCLAW_MIMO_AUTH_HEADER", "authorization").lower()
    headers = {"Content-Type": "application/json"}
    if authorization_header == "api-key":
        headers["api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "assistant", "content": text}],
            "audio": {"format": "wav", "voice": voice},
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    endpoint = f"{tts_url.rstrip('/')}/chat/completions"
    for attempt in range(attempts):
        try:
            request = Request(endpoint, data=payload, headers=headers, method="POST")
            with urlopen(request, timeout=90) as response:
                parsed = json.loads(response.read().decode("utf-8"))
            encoded_audio = parsed["choices"][0]["message"]["audio"]["data"]
            audio = base64.b64decode(encoded_audio, validate=True)
            if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
                raise RuntimeError("TTS 返回的内容不是有效 WAV 音频。")
            return audio
        except (
            HTTPError,
            URLError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            if attempt == attempts - 1:
                raise RuntimeError("TTS 音频生成失败，请检查服务配置和额度后重试。") from error
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def write_asset(path: Path, text: str, environment: dict[str, str], force: bool) -> dict[str, Any]:
    absolute_path = PUBLIC_AUDIO_ROOT / path
    if force or not absolute_path.is_file():
        audio = tts_wav(text, environment)
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(audio)
    audio = absolute_path.read_bytes()
    if len(audio) < 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError(f"已有音频不是有效 WAV：{absolute_path}")
    return {
        "path": f"/audio/cga/{path.as_posix()}",
        "sha256": sha256_bytes(audio),
        "bytes": len(audio),
        "spoken_text_sha256": sha256_text(text),
    }


def client_manifest_source(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    return (
        "// Generated by scripts/generate_cga_audio_assets.py. Do not edit manually.\n"
        "// The runtime only plays an asset when its scale and definition version match.\n"
        f"export const CGA_AUDIO_MANIFEST = {payload} as const;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 CGA 题干和选项的预录制 WAV 资源。")
    parser.add_argument(
        "--confirm-live-provider", action="store_true", help="确认调用已配置的真实 TTS 服务。"
    )
    parser.add_argument("--force", action="store_true", help="即使文件已存在也重新生成。")
    parser.add_argument(
        "--dry-run", action="store_true", help="只显示将生成的数量，不写文件也不调用 TTS。"
    )
    args = parser.parse_args()
    definitions = scale_questions()
    unique_options = {
        (item.scale_id, item.definition_version, label)
        for item in definitions
        for _, label in item.options
    }
    print(f"发现 {len(definitions)} 个题干、{len(unique_options)} 个去重选项音频。")
    if args.dry_run:
        return 0
    if not args.confirm_live_provider:
        parser.error("生成会调用真实 TTS 服务；请显式传入 --confirm-live-provider。")

    environment = read_environment()
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": {
            "kind": "live_tts_release_asset",
            "model": environment.get("MIMO_TTS_MODEL")
            or environment.get("TTS_MODEL")
            or "mimo-v2.5-tts",
            "voice": environment.get("TTS_VOICE") or "冰糖",
            "audio_format": "wav",
        },
        "scales": [],
    }
    option_assets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, definition in enumerate(definitions, start=1):
        print(
            f"[{index}/{len(definitions)}] 生成题干：{definition.scale_id}/{definition.question_id}"
        )
        question_asset = write_asset(
            question_path(definition), spoken_question(definition), environment, args.force
        )
        option_entries: list[dict[str, Any]] = []
        for ordinal, label in definition.options:
            key = (definition.scale_id, definition.definition_version, label)
            if key not in option_assets:
                print(f"生成选项：{definition.scale_id}/{sha256_text(label)[:8]}")
                option_assets[key] = write_asset(option_path(*key), label, environment, args.force)
            option_entries.append(
                {
                    "ordinal": ordinal,
                    "label_sha256": sha256_text(label),
                    "audio": option_assets[key],
                }
            )
        manifest["scales"].append(
            {
                "scale_id": definition.scale_id,
                "definition_version": definition.definition_version,
                "question_id": definition.question_id,
                "question": question_asset,
                "options": option_entries,
            }
        )

    PUBLIC_AUDIO_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    CLIENT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    CLIENT_MANIFEST_PATH.write_text(client_manifest_source(manifest), encoding="utf-8")
    print(f"已写入 {MANIFEST_PATH.relative_to(ROOT)} 和 {CLIENT_MANIFEST_PATH.relative_to(ROOT)}。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
