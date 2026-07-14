"""Dependency-free multilingual sparse lexical vectors for Qdrant hybrid search."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_LATIN_TERM = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")
_CJK_BLOCK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_MAX_SPARSE_INDEX = 2_147_483_647


@dataclass(frozen=True, slots=True)
class LexicalVector:
    """Sorted sparse vector compatible with Qdrant's SparseVector."""

    indices: tuple[int, ...]
    values: tuple[float, ...]


class LexicalEncoder:
    """Hash normalized Latin terms and Chinese n-grams into a stable sparse space."""

    VERSION = "lexical-cjk-ngram-v1"

    @staticmethod
    def tokens(value: str) -> tuple[str, ...]:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        terms: list[str] = _LATIN_TERM.findall(normalized)
        for match in _CJK_BLOCK.finditer(normalized):
            block = match.group(0)
            if 2 <= len(block) <= 8:
                terms.append(block)
            for size in (2, 3):
                terms.extend(block[index : index + size] for index in range(len(block) - size + 1))
        return tuple(terms)

    @classmethod
    def encode(cls, value: str) -> LexicalVector:
        """Return L2-normalized log-TF weights with deterministic collision merging."""

        counts = Counter(cls.tokens(value))
        buckets: dict[int, float] = {}
        for term, count in counts.items():
            digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % _MAX_SPARSE_INDEX
            buckets[index] = buckets.get(index, 0.0) + 1.0 + math.log(float(count))
        norm = math.sqrt(sum(weight * weight for weight in buckets.values())) or 1.0
        ordered = sorted(buckets.items())
        return LexicalVector(
            indices=tuple(index for index, _ in ordered),
            values=tuple(weight / norm for _, weight in ordered),
        )
