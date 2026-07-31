"""Derive a concise presentation contract from explicit user wording."""

from __future__ import annotations

import re

_ITEM_REQUEST = re.compile(
    r"(?P<count>[一二三四五六七八九十两\d]{1,3})"
    r"(?:条|点|项|个)"
    r"[^\u3002\uff01\uff1f\n]{0,16}"
    r"(?:建议|清单|要点|安排|结论|步骤|注意事项)"
)
_CHINESE_COUNTS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _requested_item_count(message: str) -> int | None:
    match = _ITEM_REQUEST.search(message)
    if match is None:
        return None
    token = match.group("count")
    count = int(token) if token.isdigit() else _CHINESE_COUNTS.get(token)
    return count if count is not None and 1 <= count <= 10 else None


def answer_presentation_contract(message: str) -> str | None:
    """Return a turn-specific layout instruction only for an explicit list request."""

    count = _requested_item_count(message)
    if count is None:
        return None
    audience = (
        "使用家属容易扫读和照做的自然中文。"
        if "家属" in message
        else "使用当前用户容易扫读和照做的自然中文。"
    )
    care_timing = (
        "用户要求保留就医时机: 把一个与当前情况直接相关的行动条件简短合并进对应条目; "
        "不要把用户已明确否认的症状改写成潜在致命疾病, 也不要扩写罕见风险。"
        if re.search(r"(?:何时|什么时候|何种情况).{0,8}(?:就医|急诊)", message)
        else ""
    )
    return (
        "本轮用户已明确指定答案形式, 必须遵守: "
        f"只输出 {count} 个编号顶层条目, 不写开场白、额外章节、重复总结或第 {count + 1} 项; "
        "每项使用短标题加一至两句可执行说明, 整段不超过 600 个中文字符; "
        f"{audience}{care_timing}"
    )
