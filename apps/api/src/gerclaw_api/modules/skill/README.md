# Skill

对应设计要求 §4.9。契约覆盖 list/load/register/execute/generate/evolve；执行实现复用 AgentScope SkillLoader/Toolkit。

自然语言“自进化”是受控修订，而不是自动发布：`POST /skills/{skill_id}/evolve` 仅对当前调用者的自定义 Skill 生成下一版本的 Markdown 草稿。后端校验当前 revision、原 ID 与递增 SemVer；草稿不会写入数据库、不会启用，也不会改变当前对话加载的版本。用户仍须在界面完整审阅后调用正常更新接口保存。
