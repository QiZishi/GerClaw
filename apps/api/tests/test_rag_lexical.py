"""Deterministic multilingual sparse retrieval tests."""

from __future__ import annotations

import math

from gerclaw_api.modules.rag.lexical import LexicalEncoder


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
