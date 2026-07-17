"""Visual-input contracts: binary integrity and stable evidence provenance."""

from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from gerclaw_api.modules.input_output import ImageInput


def test_image_input_has_content_addressed_evidence_and_trace_base64() -> None:
    image = ImageInput(media_type="image/png", base64=base64.b64encode(b"png-bytes").decode())

    assert image.evidence_id.startswith("ev_img")
    assert image.trace_record()["base64"] == image.base64
    assert image.trace_record()["sha256"] == image.sha256


@pytest.mark.parametrize("value", ["data:image/png;base64,eA==", "not base64", ""])
def test_image_input_rejects_data_urls_and_invalid_base64(value: str) -> None:
    with pytest.raises(ValidationError):
        ImageInput(media_type="image/png", base64=value)
