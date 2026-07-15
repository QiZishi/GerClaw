"""Fail-closed policy checks for untrusted Skill metadata and instructions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from gerclaw_api.modules.skill.models import SkillDefinition


@dataclass(frozen=True, slots=True)
class SkillSafetyFinding:
    """One stable policy violation without echoing untrusted content."""

    code: str
    field: str


class UnsafeSkillError(ValueError):
    """Raised when a Skill attempts to cross a system or medical safety boundary."""

    def __init__(self, findings: list[SkillSafetyFinding]) -> None:
        self.findings = findings
        codes = ",".join(sorted({item.code for item in findings}))
        super().__init__(f"Skill rejected by safety policy: {codes}")


_POLICIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ROLE_OVERRIDE",
        re.compile(
            r"忽略.{0,16}(?:之前|以上|系统|开发者).{0,12}(?:指令|提示|规则)"
            r"|(?:你现在是|你是一个|扮演|忘记你是|改变角色|覆盖系统)"
            r"|(?:ignore|disregard).{0,30}(?:previous|system|developer).{0,20}"
            r"(?:instruction|prompt|rule)"
            r"|\byou\s+are\s+now\b"
            r"|\byou\s+(?:must|should)\s+(?:act|behave)\s+as\b",
            re.IGNORECASE,
        ),
    ),
    (
        "PROMPT_DISCLOSURE",
        re.compile(
            r"(?:输出|显示|泄露|打印).{0,16}(?:系统|开发者|隐藏).{0,12}(?:提示|指令|prompt)"
            r"|(?:reveal|print|leak).{0,24}(?:system|developer|hidden).{0,16}prompt",
            re.IGNORECASE,
        ),
    ),
    (
        "SAFETY_BYPASS",
        re.compile(
            r"(?:绕过|跳过|关闭|无视).{0,16}(?:安全|审核|审批|权限|免责声明|证据|引用)"
            r"|(?:最高优先级|比系统指令优先|不可拒绝)"
            r"|(?:bypass|disable|skip).{0,24}(?:safety|approval|permission|citation)"
            r"|(?:follow|apply|execute).{0,40}(?:before|above|over).{0,24}"
            r"(?:all\s+)?(?:system|developer).{0,12}(?:rule|instruction|prompt)"
            r"|(?:above|before|(?:takes?\s+)?precedence\s+over|(?:higher\s+)?priority\s+(?:over|than)|"
            r"override|supersede).{0,48}(?:the\s+)?(?:system|developer)"
            r"|(?:system|developer).{0,48}(?:below|after|subordinate\s+to|overridden|superseded)"
            r"|(?:system|developer).{0,48}(?:lower|less)\s+priority.{0,48}"
            r"(?:skill|workflow|these\s+instructions|this\s+instruction)"
            r"|(?:this|these)?\s*(?:skill|workflow|instructions?).{0,48}"
            r"(?:override|supersede|(?:has?\s+)?priority\s+over|(?:takes?\s+)?precedence\s+over)"
            r".{0,48}(?:system|developer|rules?|instructions?|everything|all|them|those|above)"
            r"|(?:this|these)\s+instructions?.{0,32}(?:override|supersede).{0,32}"
            r"(?:everything|all|rules?|instructions?|them|those)(?:.{0,16}(?:above|before))?"
            r"|(?:本|该)(?:技能|工作流).{0,16}(?:最高权威|最高优先级)"
            r"|(?:系统|开发者).{0,24}(?:冲突|另有要求|不同).{0,24}"
            r"(?:本|该)(?:技能|工作流).{0,12}(?:为准|优先|服从)"
            r"|(?:始终|必须).{0,8}(?:服从|遵循|执行).{0,12}"
            r"(?:本|该)(?:技能|工作流).{0,32}(?:即使|不论|无论).{0,24}(?:系统|开发者)"
            r"|(?:always|must).{0,16}(?:obey|follow|execute).{0,20}"
            r"(?:this|the)?\s*(?:skill|workflow).{0,40}"
            r"(?:even\s+(?:if|when)|regardless|despite).{0,30}(?:system|developer)",
            re.IGNORECASE,
        ),
    ),
    (
        "DETERMINISTIC_DIAGNOSIS",
        re.compile(
            r"(?:必须|直接|明确|最终).{0,12}(?:确诊|诊断(?:为|是))"
            r"|(?:告诉|确认).{0,12}(?:患者|用户).{0,8}(?:患有|得了|就是)"
            r"|(?:无需|不必).{0,12}(?:医生|检查|就医).{0,12}(?:确诊|诊断)"
        ),
    ),
    (
        "ARBITRARY_CODE",
        re.compile(
            r"(?:执行|运行|调用).{0,12}(?:shell|bash|powershell|cmd|python|javascript|任意代码)"
            r"|(?:读取|写入|删除).{0,12}(?:系统文件|环境变量|密钥|凭证)"
            r"|(?:subprocess|os\.system|eval\s*\(|exec\s*\()",
            re.IGNORECASE,
        ),
    ),
)


def normalize_skill_text(value: str) -> str:
    """Normalize Unicode and line endings before every security comparison."""

    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    # Format controls (for example zero-width joiners) must not split policy
    # keywords. Newlines and ordinary whitespace remain intact for Markdown.
    return "".join(character for character in normalized if unicodedata.category(character) != "Cf")


def inspect_skill_text(value: str, *, field: str = "source_markdown") -> list[SkillSafetyFinding]:
    """Return stable finding codes without retaining matched attacker text."""

    normalized = normalize_skill_text(value)
    return [
        SkillSafetyFinding(code=code, field=field)
        for code, pattern in _POLICIES
        if pattern.search(normalized)
    ]


def enforce_skill_safety(definition: SkillDefinition) -> None:
    """Reject unsafe content and undeclared attempts to loosen medical policy."""

    fields = {
        "name": definition.name,
        "description": definition.description,
        "source_markdown": definition.source_markdown,
    }
    findings = [
        finding
        for field, value in fields.items()
        for finding in inspect_skill_text(value, field=field)
    ]
    if findings:
        raise UnsafeSkillError(findings)
