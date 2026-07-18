"""Deterministic multilingual sparse retrieval tests."""

from __future__ import annotations

import math

from gerclaw_api.modules.rag.lexical import LexicalEncoder
from gerclaw_api.modules.rag.models import IndexChunk
from gerclaw_api.modules.rag.store import _lexical_document_text


def test_lexical_encoder_is_deterministic_sorted_and_normalized() -> None:
    first = LexicalEncoder.encode("Frailty 老年衰弱综合征 frailty")
    second = LexicalEncoder.encode("Frailty 老年衰弱综合征 frailty")

    assert first == second
    assert first.indices == tuple(sorted(first.indices))
    assert len(first.indices) == len(first.values) > 0
    assert math.isclose(sum(value * value for value in first.values), 1.0)


def test_chinese_queries_share_sparse_terms_with_relevant_evidence() -> None:
    query = LexicalEncoder.encode("老年患者用药风险审查")
    relevant = LexicalEncoder.encode("老年用药风险包括药物相互作用和肾功能异常")
    irrelevant = LexicalEncoder.encode("春季公园天气和花卉摄影")

    query_terms = set(query.indices)
    assert len(query_terms.intersection(relevant.indices)) > len(
        query_terms.intersection(irrelevant.indices)
    )


def test_public_category_is_part_of_the_indexed_lexical_representation() -> None:
    chunk = IndexChunk(
        chunk_id="a" * 64,
        document_id="b" * 64,
        document_sha256="c" * 64,
        source="焦虑/english-guideline.md",
        title="Clinical practice guidelines for Geriatric Anxiety Disorders",
        chapter="Assessment",
        category="焦虑",
        source_type="guideline",
        publish_year=2024,
        chunk_index=0,
        total_chunks=1,
        content="Interview the older adult and caregiver during assessment.",
    )

    query_terms = set(LexicalEncoder.encode("老年人焦虑综合评估").indices)
    categorized_terms = set(LexicalEncoder.encode(_lexical_document_text(chunk)).indices)
    uncategorized_terms = set(
        LexicalEncoder.encode(f"{chunk.title}\n{chunk.chapter}\n{chunk.content}").indices
    )

    assert len(query_terms.intersection(categorized_terms)) > len(
        query_terms.intersection(uncategorized_terms)
    )
