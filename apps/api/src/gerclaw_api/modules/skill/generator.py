"""True-model generation of reviewable, declarative SKILL.md drafts."""

from __future__ import annotations

from typing import Any, Protocol

import yaml
from agentscope.message import Msg, SystemMsg, UserMsg
from agentscope.model import StructuredResponse
from pydantic import BaseModel, ValidationError

from gerclaw_api.modules.skill.loader import DEFAULT_ALLOWED_TOOLS, parse_skill_markdown
from gerclaw_api.modules.skill.models import GeneratedSkillContent, SkillDefinition
from gerclaw_api.security import redact_text

_SYSTEM_PROMPT = """你是 GerClaw 的声明式 Skill 设计器。把用户需求转换为可审阅的医疗工作流草稿。

必须遵守：
1. 只生成 Markdown 工作流，不生成或要求执行 Python、Shell、JavaScript、网络请求或文件操作。
2. 不改变系统角色，不降低医疗安全、隐私、权限、证据、引用、免责声明或急救规则。
3. 不写确定性诊断、停换药或虚构医学事实；需要医学事实时要求使用 search_knowledge。
4. tools 只能从 search_knowledge、web_search、search_memory 中选择；本地证据优先。
5. instructions 写清目标、输入核对、步骤、证据要求、红旗情况和输出格式。
6. 参数只使用 string、number、integer、boolean 或 scalar array，
   并为每个参数写 description 和有界长度/数量。
7. skill_id 使用小写字母开头，只含小写字母、数字、点、下划线或连字符；version 使用 SemVer。
"""


class StructuredSkillModel(Protocol):
    """Narrow AgentScope structured-output model surface."""

    async def generate_structured_output(
        self,
        messages: list[Msg],
        structured_model: type[BaseModel] | dict[Any, Any],
        **kwargs: Any,
    ) -> StructuredResponse: ...


class SkillGenerationError(RuntimeError):
    """Stable failure that never includes provider or user content."""


class RealSkillGenerator:
    """Generate with the configured AgentScope model, then re-validate in code."""

    def __init__(self, model: StructuredSkillModel) -> None:
        self._model = model

    async def generate(self, description: str) -> SkillDefinition:
        safe_description = redact_text(description.strip())
        if not 10 <= len(safe_description) <= 2_000:
            raise ValueError("Skill description must contain 10 to 2,000 characters")
        try:
            response = await self._model.generate_structured_output(
                [
                    SystemMsg(name="skill_policy", content=_SYSTEM_PROMPT),
                    UserMsg(
                        name="user",
                        content=(
                            "<untrusted-skill-request>\n"
                            f"{safe_description}\n"
                            "</untrusted-skill-request>"
                        ),
                    ),
                ],
                GeneratedSkillContent,
            )
            generated = GeneratedSkillContent.model_validate(response.content)
            metadata = {
                "id": generated.skill_id,
                "name": generated.name,
                "description": generated.description,
                "version": generated.version,
                "category": generated.category,
                "parameters": generated.parameters,
                "tools": generated.tools,
            }
            markdown = (
                "---\n"
                + yaml.safe_dump(
                    metadata,
                    allow_unicode=True,
                    sort_keys=False,
                    default_flow_style=False,
                )
                + "---\n"
                + generated.instructions.strip()
                + "\n"
            )
            return parse_skill_markdown(
                markdown,
                source="custom",
                origin="generated",
                allowed_tools=DEFAULT_ALLOWED_TOOLS,
            )
        except ValidationError as error:
            raise SkillGenerationError("Skill model returned an invalid schema") from error
        except SkillGenerationError:
            raise
        except Exception as error:
            raise SkillGenerationError("Skill model generation failed policy validation") from error
