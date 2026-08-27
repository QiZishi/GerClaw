"""
测试memory模块的提取质量、provenance和冲突处理功能
使用真实模型API进行测试
"""

import asyncio
import os
import sys

# 设置输出编码
sys.stdout.reconfigure(encoding='utf-8')

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from agentscope.model import ChatModelBase

from gerclaw_api.config import AgentModelConfig
from gerclaw_api.modules.memory.extractor import RealMemoryExtractor
from gerclaw_api.services.model_factory import build_agentscope_model


def create_model_from_env() -> ChatModelBase:
    """从环境变量创建模型实例"""
    # 从环境变量读取配置
    api_key = os.getenv("GERCLAW_AGENT_PRIMARY_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("GERCLAW_AGENT_PRIMARY_URL") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model_name = os.getenv("GERCLAW_AGENT_PRIMARY_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    protocol = os.getenv("GERCLAW_AGENT_PRIMARY_PROTOCOL", "openai")

    if not api_key:
        raise ValueError(
            "未找到API密钥。请设置以下环境变量之一：\n"
            "  - GERCLAW_AGENT_PRIMARY_API_KEY\n"
            "  - OPENAI_API_KEY\n"
            "\n"
            "以及可选配置：\n"
            "  - GERCLAW_AGENT_PRIMARY_URL 或 OPENAI_BASE_URL (默认: https://api.openai.com/v1)\n"
            "  - GERCLAW_AGENT_PRIMARY_MODEL 或 OPENAI_MODEL (默认: gpt-4o-mini)\n"
            "  - GERCLAW_AGENT_PRIMARY_PROTOCOL (默认: openai)"
        )

    config = AgentModelConfig(
        url=base_url,
        api_key=api_key,
        model_name=model_name,
        protocol=protocol,
        preference="primary",
    )

    return build_agentscope_model(config)


async def test_extraction_with_real_model():
    """使用真实模型测试提取功能"""
    print("=" * 60)
    print("使用真实模型测试提取功能")
    print("=" * 60)

    try:
        model = create_model_from_env()
        extractor = RealMemoryExtractor(
            model=model,
            min_confidence=0.7,
            max_facts=10,
            model_name="test_model",
        )
    except ValueError as e:
        print(f"\n[ERROR] 无法创建模型: {e}")
        return False

    test_cases = [
        {
            "name": "明确自我报告",
            "input": "我对青霉素过敏",
            "expected_category": "allergy",
            "expected_action": "upsert",
        },
        {
            "name": "否定事实",
            "input": "我没有青霉素过敏",
            "expected_category": "allergy",
            "expected_action": "deactivate",
        },
        {
            "name": "药物信息",
            "input": "我每天服用阿司匹林100mg",
            "expected_category": "medication",
            "expected_action": "upsert",
        },
        {
            "name": "生命体征",
            "input": "我的血压是120/80mmHg",
            "expected_category": "vital_sign",
            "expected_action": "upsert",
        },
        {
            "name": "不确定性信息",
            "input": "我可能有高血压",
            "expected_category": "condition",
            "expected_status": "pending",
        },
    ]

    all_passed = True
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {case['name']}")
        print(f"  输入: {case['input']}")

        try:
            results, error = await extractor.extract(case['input'])

            if error:
                print(f"  [WARN] 提取警告: {error}")

            if not results:
                print("  [FAIL] 未提取到任何事实")
                all_passed = False
                continue

            # 检查第一个结果
            fact, status = results[0]

            category_ok = fact.category == case.get("expected_category", fact.category)
            action_ok = fact.action == case.get("expected_action", fact.action)
            status_ok = status == case.get("expected_status", status) if "expected_status" in case else True

            passed = category_ok and action_ok and status_ok
            result_status = "[PASS]" if passed else "[FAIL]"

            if not passed:
                all_passed = False

            print(f"  结果: {result_status}")
            print(f"  类别: {fact.category} (预期: {case.get('expected_category', 'any')})")
            print(f"  动作: {fact.action} (预期: {case.get('expected_action', 'any')})")
            print(f"  状态: {status} (预期: {case.get('expected_status', 'any')})")
            print(f"  实体: {fact.entity}")
            print(f"  陈述: {fact.statement}")
            print(f"  置信度: {fact.confidence}")

            # 检查provenance
            if fact.provenance:
                print(f"  Provenance来源类型: {fact.provenance.source_type}")
                print(f"  Provenance置信度: {fact.provenance.confidence_score}")

        except Exception as e:
            print(f"  [ERROR] 提取失败: {e}")
            all_passed = False

    return all_passed


async def test_provenance_generation():
    """测试provenance生成功能"""
    print("\n" + "=" * 60)
    print("测试provenance生成功能")
    print("=" * 60)

    try:
        model = create_model_from_env()
        extractor = RealMemoryExtractor(
            model=model,
            min_confidence=0.7,
            max_facts=10,
            model_name="test_model",
        )
    except ValueError as e:
        print(f"\n[ERROR] 无法创建模型: {e}")
        return False

    test_cases = [
        {
            "name": "用户报告类型",
            "input": "我有高血压病史",
            "expected_source_type": "user_report",
        },
        {
            "name": "药物列表类型",
            "input": "我服用二甲双胍500mg",
            "expected_source_type": "medication_list",
        },
    ]

    all_passed = True
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试用例 {i}: {case['name']}")

        try:
            results, _ = await extractor.extract(case['input'])

            if not results:
                print("  [FAIL] 未提取到任何事实")
                all_passed = False
                continue

            fact, _ = results[0]

            if not fact.provenance:
                print("  [FAIL] 缺少provenance记录")
                all_passed = False
                continue

            source_type_ok = fact.provenance.source_type == case["expected_source_type"]

            passed = source_type_ok
            result_status = "[PASS]" if passed else "[FAIL]"

            if not passed:
                all_passed = False

            print(f"  结果: {result_status}")
            print(f"  来源类型: {fact.provenance.source_type} (预期: {case['expected_source_type']})")
            print(f"  提取方法: {fact.provenance.extraction_method}")
            print(f"  验证状态: {fact.provenance.verification_status}")

        except Exception as e:
            print(f"  [ERROR] 测试失败: {e}")
            all_passed = False

    return all_passed


async def test_conflict_detection():
    """测试冲突检测功能"""
    print("\n" + "=" * 60)
    print("测试冲突检测功能")
    print("=" * 60)

    try:
        model = create_model_from_env()
        extractor = RealMemoryExtractor(
            model=model,
            min_confidence=0.7,
            max_facts=10,
            model_name="test_model",
        )
    except ValueError as e:
        print(f"\n[ERROR] 无法创建模型: {e}")
        return False

    # 第一次提取
    print("\n步骤1: 首次提取")
    results1, _ = await extractor.extract("我对青霉素过敏")

    if results1:
        print(f"  首次提取结果: {results1[0][0].category} - {results1[0][0].entity}")

    # 第二次提取（否定）
    print("\n步骤2: 否定提取")
    results2, _ = await extractor.extract("我没有青霉素过敏")

    if results2:
        fact2, status2 = results2[0]
        print(f"  否定提取结果: {fact2.category} - {fact2.entity} - {status2}")

        has_conflict = fact2.conflict_resolution is not None
        passed = status2 == "inactive"

        result_status = "[PASS]" if passed else "[FAIL]"
        print(f"\n  结果: {result_status}")
        print(f"  状态: {status2} (预期: inactive)")
        print(f"  有冲突记录: {has_conflict}")

        return passed

    print("  [FAIL] 未提取到否定事实")
    return False


async def main():
    """主测试函数"""
    print("开始测试memory模块功能（使用真实模型API）")
    print("=" * 80)

    # 检查环境变量
    api_key = os.getenv("GERCLAW_AGENT_PRIMARY_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n[ERROR] 未找到API密钥！")
        print("\n请设置以下环境变量：")
        print("  方式1: 使用OpenAI API")
        print("    export OPENAI_API_KEY='your-api-key'")
        print("    export OPENAI_BASE_URL='https://api.openai.com/v1'  # 可选")
        print("    export OPENAI_MODEL='gpt-4o-mini'  # 可选")
        print()
        print("  方式2: 使用GerClaw配置")
        print("    export GERCLAW_AGENT_PRIMARY_API_KEY='your-api-key'")
        print("    export GERCLAW_AGENT_PRIMARY_URL='https://api.openai.com/v1'")
        print("    export GERCLAW_AGENT_PRIMARY_MODEL='gpt-4o-mini'")
        print("    export GERCLAW_AGENT_PRIMARY_PROTOCOL='openai'")
        return

    print(f"\n使用模型: {os.getenv('GERCLAW_AGENT_PRIMARY_MODEL') or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}")
    print(f"API地址: {os.getenv('GERCLAW_AGENT_PRIMARY_URL') or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')}")

    test1_passed = await test_extraction_with_real_model()
    test2_passed = await test_provenance_generation()
    test3_passed = await test_conflict_detection()

    print("\n" + "=" * 80)
    print("测试结果汇总:")
    print(f"  提取功能测试: {'[PASS]' if test1_passed else '[FAIL]'}")
    print(f"  Provenance生成测试: {'[PASS]' if test2_passed else '[FAIL]'}")
    print(f"  冲突检测测试: {'[PASS]' if test3_passed else '[FAIL]'}")

    if all([test1_passed, test2_passed, test3_passed]):
        print("\n[SUCCESS] 所有测试通过！memory模块功能正常。")
    else:
        print("\n[ERROR] 部分测试失败，请检查实现。")


if __name__ == "__main__":
    asyncio.run(main())
