#!/usr/bin/env python3
"""Generate a deterministic CycloneDX inventory of the API image's Python runtime.

This intentionally inventories packages installed in the *built production image*,
not the developer virtual environment. Debian/base-image packages and licence legal
approval are outside this focused report and are stated in the accompanying policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

_IMAGE_METADATA_SCRIPT = r"""
from importlib.metadata import distributions
import json

items = []
for distribution in distributions():
    metadata = distribution.metadata
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        continue
    licence = metadata.get("License-Expression") or metadata.get("License")
    items.append({"name": name, "version": version, "license": licence or None})
print(json.dumps(sorted(items, key=lambda item: (item["name"].lower(), item["version"]))))
"""


def _run(*command: str) -> str:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _component(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item["name"])
    version = str(item["version"])
    value: dict[str, Any] = {
        "type": "library",
        "name": name,
        "version": version,
        "purl": f"pkg:pypi/{name.lower()}@{version}",
        "bom-ref": f"pkg:pypi/{name.lower()}@{version}",
    }
    license_value = item.get("license")
    if isinstance(license_value, str) and license_value.strip():
        value["licenses"] = [{"license": {"name": license_value.strip()}}]
    else:
        value["properties"] = [{"name": "gerclaw:license-status", "value": "unknown"}]
    return value


def build_bom(
    *, image: str, image_id: str, lock_sha256: str, packages: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build stable CycloneDX JSON without timestamps or host-specific paths."""

    components = sorted(
        (_component(item) for item in packages), key=lambda item: item["bom-ref"]
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"gerclaw:{image_id}:{lock_sha256}")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "gerclaw-api-runtime",
                "version": "locked",
                "bom-ref": "gerclaw-api-runtime",
            },
            "properties": [
                {"name": "gerclaw:container-image", "value": image},
                {"name": "gerclaw:container-image-id", "value": image_id},
                {"name": "gerclaw:uv-lock-sha256", "value": lock_sha256},
                {"name": "gerclaw:scope", "value": "python-runtime-only"},
            ],
        },
        "components": components,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="locally built production API image"
    )
    parser.add_argument(
        "--lock", type=Path, required=True, help="the corresponding uv.lock"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="CycloneDX JSON output path"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.lock.is_file():
        raise SystemExit("lock file does not exist")
    try:
        image_id = _run("docker", "image", "inspect", "--format", "{{.Id}}", args.image)
        package_json = _run(
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "python",
            args.image,
            "-c",
            _IMAGE_METADATA_SCRIPT,
        )
    except subprocess.CalledProcessError as error:
        sys.stderr.write(error.stderr or "could not inspect runtime image\n")
        return error.returncode or 1
    packages = json.loads(package_json)
    if not isinstance(packages, list) or not packages:
        raise SystemExit("production image did not report Python runtime packages")
    bom = build_bom(
        image=args.image,
        image_id=image_id,
        lock_sha256=_sha256(args.lock),
        packages=packages,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bom, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"SBOM: {args.output} ({len(bom['components'])} Python runtime components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
