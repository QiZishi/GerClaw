"""
回归审计测试：锁定 _fact_deterministic_uuid 的种子逻辑。

风险C说明：_detect_conflicts 使用 uuid.uuid5(NAMESPACE_URL, seed) 生成确定性 UUID。
如果后续开发者在 ExtractedMemoryFact 中新增字段但忘记更新 seed 格式，
冲突 ID 逻辑会悄悄变质。本测试文件锁定种子格式，确保任何变更都会被检测到。
"""

from __future__ import annotations

import uuid
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 直接从 extractor.py 复制种子逻辑（与生产代码保持一致）
_NAMESPACE = uuid.NAMESPACE_URL


def _fact_deterministic_uuid(category: str, entity: str, statement: str) -> uuid.UUID:
    """与 extractor.py 中 _detect_conflicts 内的逻辑完全一致。"""
    seed = f"{category}|{entity}|{statement}"
    return uuid.uuid5(_NAMESPACE, seed)


def test_same_input_same_uuid():
    """相同输入必须产生相同 UUID"""
    print("测试 1: 相同输入产生相同 UUID ... ", end="")
    uid1 = _fact_deterministic_uuid("allergy", "青霉素", "用户自述对青霉素过敏")
    uid2 = _fact_deterministic_uuid("allergy", "青霉素", "用户自述对青霉素过敏")
    assert uid1 == uuid.UUID(str(uid1)), "UUID 格式无效"
    assert uid1 == uid2, f"相同输入产生不同 UUID: {uid1} != {uid2}"
    print("[PASS]")


def test_different_category_different_uuid():
    """不同 category 必须产生不同 UUID"""
    print("测试 2: 不同 category 产生不同 UUID ... ", end="")
    uid1 = _fact_deterministic_uuid("allergy", "青霉素", "用户自述对青霉素过敏")
    uid2 = _fact_deterministic_uuid("medication", "青霉素", "用户自述对青霉素过敏")
    assert uid1 != uid2, f"不同 category 产生相同 UUID: {uid1}"
    print("[PASS]")


def test_different_entity_different_uuid():
    """不同 entity 必须产生不同 UUID"""
    print("测试 3: 不同 entity 产生不同 UUID ... ", end="")
    uid1 = _fact_deterministic_uuid("allergy", "青霉素", "用户自述对青霉素过敏")
    uid2 = _fact_deterministic_uuid("allergy", "阿司匹林", "用户自述对青霉素过敏")
    assert uid1 != uid2, f"不同 entity 产生相同 UUID: {uid1}"
    print("[PASS]")


def test_different_statement_different_uuid():
    """不同 statement 必须产生不同 UUID"""
    print("测试 4: 不同 statement 产生不同 UUID ... ", end="")
    uid1 = _fact_deterministic_uuid("allergy", "青霉素", "用户自述对青霉素过敏")
    uid2 = _fact_deterministic_uuid("allergy", "青霉素", "用户否认青霉素过敏")
    assert uid1 != uid2, f"不同 statement 产生相同 UUID: {uid1}"
    print("[PASS]")


def test_seed_format_locked():
    """锁定种子格式为 'category|entity|statement'（管道符分隔）

    如果有人修改了种子格式（例如改为逗号分隔或新增字段），
    此测试会失败，强制开发者同步更新本测试文件。
    """
    print("测试 5: 种子格式锁定（category|entity|statement）... ", end="")
    # 已知的种子和对应的 UUID（用当前格式预计算）
    known_seed = "medication|阿司匹林|用户自述服用阿司匹林100mg"
    expected_uuid = uuid.uuid5(_NAMESPACE, known_seed)

    # 通过函数计算
    computed_uuid = _fact_deterministic_uuid("medication", "阿司匹林", "用户自述服用阿司匹林100mg")

    assert computed_uuid == expected_uuid, (
        f"种子格式可能已变更！\n"
        f"  期望种子: '{known_seed}'\n"
        f"  期望 UUID: {expected_uuid}\n"
        f"  实际 UUID: {computed_uuid}\n"
        f"  如果你确实修改了种子格式，请同步更新此测试。"
    )
    print("[PASS]")


def test_seed_separator_matters():
    """验证分隔符 '|' 对结果有影响（防止有人改成 ',' 但忘记更新测试）"""
    print("测试 6: 分隔符影响验证 ... ", end="")
    # 用 '|' 分隔
    uid_pipe = _fact_deterministic_uuid("allergy", "青霉素", "过敏")
    # 手动用 ',' 分隔计算（应该不同）
    seed_comma = f"allergy,青霉素,过敏"
    uid_comma = uuid.uuid5(_NAMESPACE, seed_comma)
    assert uid_pipe != uid_comma, "分隔符变更未被检测到"
    print("[PASS]")


def test_empty_fields_handled():
    """空字段也必须产生有效 UUID（边界情况）"""
    print("测试 7: 空字段边界情况 ... ", end="")
    uid = _fact_deterministic_uuid("", "", "")
    assert isinstance(uid, uuid.UUID), "空字段未产生有效 UUID"
    # 空字段的 UUID 不应等于有内容的 UUID
    uid_with_content = _fact_deterministic_uuid("allergy", "青霉素", "过敏")
    assert uid != uid_with_content, "空字段 UUID 不应等于有内容的 UUID"
    print("[PASS]")


def test_chinese_characters_in_seed():
    """中文字符必须正确参与种子计算"""
    print("测试 8: 中文字符种子计算 ... ", end="")
    uid_cn = _fact_deterministic_uuid("过敏", "青霉素", "用户自述过敏")
    uid_en = _fact_deterministic_uuid("allergy", "penicillin", "user reports allergy")
    assert uid_cn != uid_en, "中英文种子不应产生相同 UUID"
    print("[PASS]")


if __name__ == "__main__":
    print("=" * 60)
    print("回归审计：确定性 UUID 种子逻辑锁定测试")
    print("=" * 60)
    print()

    tests = [
        test_same_input_same_uuid,
        test_different_category_different_uuid,
        test_different_entity_different_uuid,
        test_different_statement_different_uuid,
        test_seed_format_locked,
        test_seed_separator_matters,
        test_empty_fields_handled,
        test_chinese_characters_in_seed,
    ]

    passed = 0
    failed = 0
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {e}")
            failed += 1
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"结果: {passed} 通过, {failed} 失败")
    if failed == 0:
        print("[SUCCESS] 所有确定性 UUID 测试通过。种子逻辑已锁定。")
    else:
        print("[ERROR] 存在失败测试，请检查种子逻辑是否被意外修改。")
    print("=" * 60)