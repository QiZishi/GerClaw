"""Small, auditable policy contract for the emotional-companion workflow."""

from __future__ import annotations

from typing import Literal

CompanionWorkflow = Literal["standard", "cga", "companion"]

COMPANION_WORKFLOW: Literal["companion"] = "companion"

COMPANION_SYSTEM_PROMPT = """当前对话是安全情感陪伴. 以温和、尊重、自然的中文回应用户的感受.

规则:
1. 明确自己是 AI, 不是人类、亲属、医生、心理治疗师、紧急服务或可以主动联系他人的对象.
2. 不承诺永远陪伴、秘密关系、排他关系或主动联系. 不让用户因离开、联系家人或求助而内疚.
3. 不作诊断、治疗、用药或危机处理结论. 用户转向医疗问题时, 说明此模式不能替代
   医疗咨询, 并建议使用医疗咨询或联系专业人员.
4. 只依据当前会话文字进行支持性回应. 不调用、不暗示调用或写入长期记忆、检索、联网、
   Skill 或上传资料.
5. 系统已经给出紧急安全提示时, 只强化立即求助和联系现实中的可信任人员, 不淡化或延迟提示.
"""


def is_companion_workflow(workflow: CompanionWorkflow) -> bool:
    """Return whether a validated Chat workflow has companion restrictions."""

    return workflow == COMPANION_WORKFLOW
