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
_NUMBERED_TOP_LEVEL_ITEM = re.compile(r"(?m)^\s*(?P<index>\d{1,2})[.、]\s+")


class AnswerPresentationContractError(RuntimeError):
    """A useful answer that did not preserve the user's explicit layout."""

    def __init__(self, expected_count: int, observed_indices: tuple[int, ...]) -> None:
        super().__init__("answer does not match the requested numbered-list contract")
        self.expected_count = expected_count
        self.observed_indices = observed_indices

    @property
    def repair_instruction(self) -> str:
        return (
            f"上一尝试没有完成用户明确要求的 {self.expected_count} 点编号清单。"
            "请从用户原任务重新生成完整答案, 保留已核验事实及其真实引用; "
            f"必须恰好输出 {self.expected_count} 个顶层条目, 每项单独一行, 依次使用 "
            f"1. 到 {self.expected_count}. (数字、英文句点、空格), "
            "不得丢项、合并成段落或增加其他章节。"
            "不要提及格式检查或重新生成过程。"
        )


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
        f"只输出 {count} 个编号顶层条目, 每项单独一行并依次使用 "
        f"1. 到 {count}. (数字、英文句点、空格), "
        f"不写开场白、额外章节、重复总结或第 {count + 1} 项; "
        "每项使用短标题加一至两句可执行说明, 整段不超过 600 个中文字符; "
        f"{audience}{care_timing}"
    )


def validate_answer_presentation_contract(message: str, answer: str) -> None:
    """Validate only an explicit item-count request before publication."""

    expected_count = _requested_item_count(message)
    if expected_count is None:
        return
    observed = tuple(
        int(match.group("index")) for match in _NUMBERED_TOP_LEVEL_ITEM.finditer(answer)
    )
    expected = tuple(range(1, expected_count + 1))
    if observed != expected:
        raise AnswerPresentationContractError(expected_count, observed)
