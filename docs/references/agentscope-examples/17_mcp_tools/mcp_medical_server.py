# -*- coding: utf-8 -*-
"""GerClaw 医学工具 MCP stdio 服务端。

本模块演示如何使用 ``mcp.server.fastmcp.FastMCP`` 创建一个通过标准
输入/输出（stdio）对外提供医学工具的 MCP 服务器。客户端
（如 AgentScope 的 ``MCPClient`` + ``StdioMCPConfig``）可以启动本
脚本作为子进程，并通过 MCP 协议调用以下工具：

* ``get_drug_info`` — 常用老年慢性病用药查询（适应症 / 用法用量 /
  禁忌症 / 老年注意事项）。
* ``calculate_bmi`` — BMI 计算并返回中国成人 / 老年营养状态分级。

运行方式（独立运行，作为 stdio 服务）::

    python mcp_medical_server.py

或由 AgentScope ``StdioMCPConfig(command="python", args=[__file__])``
自动以子进程拉起。

本服务不需要任何 API Key，内置的药品知识库为演示用精简版数据，
生产环境应对接真实药品数据库（如 RxNorm、国家药品监督管理局数据）。
"""

from __future__ import annotations

from mcp.server import FastMCP

# ---------------------------------------------------------------------------
# 1. 创建 FastMCP 服务器实例
# ---------------------------------------------------------------------------
# 服务器名 "gerclaw_medical" 会出现在 MCP initialize 握手信息中，
# AgentScope 侧 MCPClient.name 与此解耦（客户端侧可自定义命名）。
mcp: FastMCP = FastMCP("gerclaw_medical")


# ---------------------------------------------------------------------------
# 2. 内置演示用药品知识库（生产请替换为真实数据库查询）
# ---------------------------------------------------------------------------
_DRUG_DB: dict[str, dict[str, str]] = {
    "二甲双胍": {
        "generic_name": "盐酸二甲双胍 (Metformin HCl)",
        "indications": (
            "首选用于单纯饮食控制及体育锻炼治疗无效的2型糖尿病，"
            "尤其适用于肥胖的2型糖尿病患者；可与磺脲类或胰岛素联用。"
        ),
        "dosage": (
            "成人起始剂量通常一次 0.25g，一日 2~3 次，随餐服用；"
            "根据血糖调整，一般每日 1~1.5g，最大不超过 2g。"
            "老年患者应慎用并定期监测肾功能（eGFR）。"
        ),
        "contraindications": (
            "1) 肾功能不全（男性血肌酐≥132.6μmol/L，女性≥123.8μmol/L，"
            "或 eGFR<30 mL/min/1.73m²）禁用；"
            "2) 对本品过敏者；3) 急性代谢性酸中毒、糖尿病酮症酸中毒；"
            "4) 严重感染、外伤、重大手术；5) 酗酒者。"
        ),
        "elderly_warning": (
            "【老年注意事项】65岁以上老年患者因肾功能生理性减退，"
            "剂量宜小，需定期监测 eGFR；不推荐 80 岁以上患者起始使用，"
            "除非肌酐清除率证实肾功能正常；避免与造影剂同日使用（应前后"
            "停用 48 小时）以降低乳酸酸中毒风险。"
        ),
    },
    "阿司匹林": {
        "generic_name": "阿司匹林 (Aspirin / Acetylsalicylic Acid)",
        "indications": (
            "1) 心脑血管疾病二级预防（冠心病、脑梗死、外周动脉疾病）；"
            "2) 急性冠脉综合征；3) 一过性脑缺血发作；"
            "4) 部分风湿性疾病抗炎镇痛（大剂量）。"
        ),
        "dosage": (
            "心脑血管二级预防：每日 75~100 mg，一日一次，餐前或餐后服用因"
            "剂型而异（肠溶片建议空腹）。镇痛抗炎：一次 300~600 mg。"
        ),
        "contraindications": (
            "1) 活动性消化性溃疡、出血倾向；2) 对水杨酸类过敏；"
            "3) 血友病或血小板减少症；4) 妊娠最后三个月。"
        ),
        "elderly_warning": (
            "【老年注意事项】老年人胃黏膜脆弱，消化道出血风险升高，"
            "宜选用肠溶剂型并观察黑便、牙龈出血等出血征象；"
            "合并使用抗凝药（华法林、利伐沙班）时出血风险显著增加，"
            "必须在医生指导下使用。"
        ),
    },
    "氨氯地平": {
        "generic_name": "苯磺酸氨氯地平 (Amlodipine Besylate)",
        "indications": (
            "1) 高血压（可单用或与其他降压药联用）；"
            "2) 慢性稳定性心绞痛、血管痉挛性心绞痛。"
        ),
        "dosage": (
            "起始 5 mg，一日一次；最大 10 mg，一日一次。"
            "老年、肝功能不全患者起始 2.5 mg。"
        ),
        "contraindications": (
            "1) 对二氢吡啶类钙拮抗剂过敏；2) 严重低血压、休克；"
            "3) 重度主动脉瓣狭窄。"
        ),
        "elderly_warning": (
            "【老年注意事项】老年人降压宜缓慢，起始 2.5 mg 并密切监测立位"
            "血压，警惕体位性低血压跌倒风险；常见下肢水肿不良反应，"
            "如出现应告知医生调整剂量或联合用药。"
        ),
    },
}


# ---------------------------------------------------------------------------
# 3. 工具实现
# ---------------------------------------------------------------------------
@mcp.tool()
async def get_drug_info(drug_name: str) -> str:
    """查询常用老年慢性病用药信息，返回适应症、用法用量、禁忌症及老年患者注意事项。

    适用于老年患者常见慢性病（糖尿病、高血压、冠心病、脑梗死等）
    的口服药物查询。如查询不到将返回提示，建议进一步咨询医生或药师。

    Args:
        drug_name: 药品通用名或商品名，如 "二甲双胍"、"阿司匹林"、"氨氯地平"。
                   目前演示库支持上述三种药品。
    """
    # 简单别名归一化
    alias = {
        "metformin": "二甲双胍",
        "aspirin": "阿司匹林",
        "amlodipine": "氨氯地平",
        "拜糖平": "二甲双胍",  # 演示用简化映射
        "络活喜": "氨氯地平",
    }
    key = alias.get(drug_name.strip(), drug_name.strip())
    info = _DRUG_DB.get(key)

    if info is None:
        return (
            f"【用药查询结果】抱歉，演示库暂未收录「{drug_name}」的信息。\n"
            "当前内置示例药品：二甲双胍、阿司匹林、氨氯地平。\n"
            "生产环境建议对接国家药品监督管理局药品数据库或 RxNorm 等权威数据源，"
            "并提醒老年患者：所有用药请遵医嘱，切勿自行调整剂量。"
        )

    return (
        f"【用药查询结果 — {info['generic_name']}】\n\n"
        f"▶ 适应症：\n{info['indications']}\n\n"
        f"▶ 用法用量：\n{info['dosage']}\n\n"
        f"▶ 禁忌症：\n{info['contraindications']}\n\n"
        f"▶ {info['elderly_warning']}\n\n"
        "⚠ 本结果仅供健康科普参考，不能替代执业医师或药师的专业诊断与处方。"
    )


@mcp.tool()
async def calculate_bmi(height_cm: float, weight_kg: float) -> str:
    """计算体质指数（BMI）并按中国成人标准给出体重分级与老年营养评估建议。

    BMI = 体重(kg) / 身高(m)²。
    中国成人标准：偏瘦 <18.5；正常 18.5~23.9；超重 24.0~27.9；肥胖 ≥28。
    老年（≥65岁）额外提示：BMI 20.0~26.9 区间可能对应更好的临床结局，
    过瘦（<20）需评估肌少症与营养不良风险。

    Args:
        height_cm: 身高，单位厘米 (cm)，建议范围 100~230。
        weight_kg: 体重，单位千克 (kg)，建议范围 25~200。
    """
    # 参数合法性校验
    if not (100 <= height_cm <= 230):
        return f"身高 {height_cm} cm 超出合理范围（100~230），请核对输入。"
    if not (25 <= weight_kg <= 200):
        return f"体重 {weight_kg} kg 超出合理范围（25~200），请核对输入。"

    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)
    bmi_rounded = round(bmi, 2)

    # 中国成人分级
    if bmi < 18.5:
        grade = "偏瘦"
        advice = "建议增加优质蛋白与能量摄入，老年人需警惕肌少症风险。"
    elif bmi < 24.0:
        grade = "正常"
        advice = "体重在健康范围，建议保持均衡饮食与适度运动。"
    elif bmi < 28.0:
        grade = "超重"
        advice = "建议控制总热量、增加有氧运动；老年人减重不宜过快（每周≤0.5kg）。"
    else:
        grade = "肥胖"
        advice = (
            "建议在医生/营养师指导下科学减重；关注血压、血糖、血脂等代谢指标，"
            "老年患者避免极低热量节食。"
        )

    # 老年专项提示
    elderly_note = ""
    if bmi < 20.0:
        elderly_note = (
            "\n\n【老年营养专项提示】BMI < 20.0 在老年人群中与营养不良、"
            "肌少症、跌倒风险升高相关，建议进行 MNA-SF 营养筛查并就诊营养科。"
        )
    elif 20.0 <= bmi <= 26.9:
        elderly_note = (
            "\n\n【老年营养专项提示】BMI 20.0~26.9 是多项老年队列研究中"
            "全因死亡率较低的区间，请继续保持。"
        )

    return (
        f"【BMI 计算结果】\n"
        f"身高：{height_cm} cm\n"
        f"体重：{weight_kg} kg\n"
        f"BMI ＝ {weight_kg} ÷ ({height_m}²) ＝ {bmi_rounded}\n"
        f"体重分级（中国成人标准）：{grade}\n\n"
        f"建议：{advice}"
        f"{elderly_note}"
    )


# ---------------------------------------------------------------------------
# 4. 入口：以 stdio 方式运行 MCP 服务
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # transport="stdio" 表示通过标准输入/输出与客户端通信，
    # 这是 AgentScope StdioMCPConfig 的默认对接方式。
    mcp.run(transport="stdio")
