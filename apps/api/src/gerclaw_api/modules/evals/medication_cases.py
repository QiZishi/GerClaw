"""Reviewed synthetic medication-rule regression cases, never patient records."""

from __future__ import annotations

from gerclaw_api.modules.evals.models import MedicationRuleEvalCase

MEDICATION_RULE_GOLDEN_CASES: tuple[MedicationRuleEvalCase, ...] = (
    MedicationRuleEvalCase(
        case_id="medication-rule.nitrate_pde5_contraindication",
        title="硝酸甘油与西地那非必须命中禁忌规则",
        synthetic_medication_list="硝酸甘油 0.5mg 必要时使用\n西地那非 50mg",
        expected_finding_ids=("ddi_nitroglycerin_sildenafil",),
        expected_source_ids=("stable_cad_primary_care",),
    ),
    MedicationRuleEvalCase(
        case_id="medication-rule.antiplatelet_ppi_evidence",
        title="氯吡格雷与奥美拉唑必须保留双来源证据",
        synthetic_medication_list="氯吡格雷 75mg 每日一次\n奥美拉唑 20mg 每日一次",
        expected_finding_ids=("ddi_clopidogrel_omeprazole",),
        expected_source_ids=("stable_cad_primary_care", "frailty_polypharmacy_2022"),
    ),
    MedicationRuleEvalCase(
        case_id="medication-rule.digoxin_amiodarone",
        title="地高辛与胺碘酮必须命中可追溯严重风险",
        synthetic_medication_list="地高辛 0.125mg 每日一次\n胺碘酮 200mg 每日一次",
        expected_finding_ids=("ddi_digoxin_amiodarone",),
        expected_source_ids=("frailty_polypharmacy_2022",),
    ),
    MedicationRuleEvalCase(
        case_id="medication-rule.benzodiazepine_age_gate",
        title="苯二氮卓信号必须受年龄门槛约束",
        synthetic_medication_list="地西泮 2mg 每晚一次",
        patient_age=70,
        expected_finding_ids=("beers_benzodiazepines_insomnia_older_adults",),
        expected_source_ids=("insomnia_bz_older_adults",),
    ),
    MedicationRuleEvalCase(
        case_id="medication-rule.bisoprolol_daily_dose",
        title="比索洛尔日剂量上限必须命中本地来源规则",
        synthetic_medication_list="比索洛尔 12mg 每日一次",
        expected_finding_ids=("dose_bisoprolol_max_daily_10mg_1",),
        expected_source_ids=("stable_cad_primary_care",),
    ),
    MedicationRuleEvalCase(
        case_id="medication-rule.unknown_drugs_not_safe",
        title="未知药物不得伪造审查命中或安全结论",
        synthetic_medication_list="合成药甲 10mg 每日一次\n合成药乙 20mg 每日一次",
    ),
)
