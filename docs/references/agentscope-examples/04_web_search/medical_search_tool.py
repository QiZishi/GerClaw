# -*- coding: utf-8 -*-
"""
GerClaw 老年医疗AI平台 — 医学搜索工具示例

本示例演示在AgentScope中两种创建医学搜索工具的方式：
  方式一：继承ToolBase，定义ParamsBase参数类，实现check_permissions和call方法。
          适用于需要精细权限控制、权威分级、流式输出的核心搜索工具。
  方式二：使用FunctionTool适配器包装普通Python函数。
          适用于快速原型开发、简单查询工具。

工具注册到Toolkit后，可被医生Agent在ReAct循环中自动调用。
本示例使用mock数据模拟搜索"老年高血压最新指南"，无需真实联网。

运行方式：
    export DASHSCOPE_API_KEY="your-key"   # 可选，有则演示Agent真实推理
    python medical_search_tool.py
"""
import asyncio
import json
import os
from typing import Any

from pydantic import Field

from agentscope.credential import DashScopeCredential
from agentscope.message import Msg, TextBlock, ToolCallBlock, ToolResultBlock, ToolResultState
from agentscope.model import DashScopeChatModel
from agentscope.permission import PermissionBehavior, PermissionContext, PermissionDecision
from agentscope.state import AgentState
from agentscope.tool import FunctionTool, ParamsBase, ToolBase, ToolChunk, Toolkit


# ============================================================
# 方式一：继承 ToolBase 定义医学文献搜索工具
# ============================================================

class MedicalLiteratureSearchTool(ToolBase):
    """医学文献与临床指南检索工具。

    支持PubMed、NICE、AHA、NCCN、中华医学会等权威来源检索，
    结果按S/A/B/C四级权威等级标注，适用于老年医疗场景的循证查询。
    """

    # ---- 必须定义的类属性 ----
    name: str = "medical_literature_search"
    description: str = (
        "搜索权威医学文献和临床诊疗指南数据库，"
        "涵盖PubMed、NICE、WHO、AHA/ACC、NCCN、中华医学会等来源。"
        "用于获取最新老年慢病诊疗指南、循证医学证据、药品信息。"
        "结果按来源权威性标注为S/A/B/C级，S级为政府/国际组织最高权威。"
        "当用户询问最新诊疗方案、指南更新、药品用法时应调用此工具。"
    )

    class Params(ParamsBase):
        """工具参数定义"""
        query: str = Field(
            ...,
            description="搜索关键词，如'老年高血压最新指南'、'2型糖尿病诊疗标准2024'",
        )
        source: str = Field(
            "all",
            description="数据源筛选: guideline(临床指南)/pubmed(医学文献)/drug(药品)/all(全部)",
        )
        max_results: int = Field(
            5, ge=1, le=10,
            description="返回结果数量，默认5条，最多10条",
        )
        year_from: int | None = Field(
            None, ge=2018,
            description="起始年份，用于限定文献/指南发布时间",
        )

    input_schema: dict = Params.model_json_schema()
    is_concurrency_safe: bool = True
    is_read_only: bool = True  # 搜索为只读操作

    # 模拟数据库：键=搜索关键词，值=结果列表
    _MOCK_DB: dict[str, list[dict]] = {
        "老年高血压": [
            {
                "level": "S", "org": "国家卫生健康委员会", "year": 2024,
                "title": "中国老年高血压管理指南(2024版)",
                "url": "https://www.nhc.gov.cn/wjw/gfxwj/202403/t20240315_xxx.shtml",
                "summary": (
                    "65岁以上老年高血压患者降压目标："
                    "65-79岁老年人血压降至<140/90mmHg，如能耐受可降至<130/80mmHg；"
                    "80岁及以上高龄老年人降压目标为<150/90mmHg，"
                    "衰弱老年人应个体化制定降压目标，避免体位性低血压。"
                ),
            },
            {
                "level": "A", "org": "中华医学会心血管病学分会", "year": 2023,
                "title": "中国高血压防治指南(2023年修订版)",
                "url": "https://www.cma.org.cn/xxx/hypertension2023",
                "summary": (
                    "推荐老年高血压初始治疗可选用CCB(钙通道阻滞剂)、"
                    "噻嗪类利尿剂或ARB/ACEI；合并糖尿病或肾病者首选ARB/ACEI；"
                    "起始小剂量单药或两药联合，逐步滴定。"
                ),
            },
            {
                "level": "A", "org": "美国心脏协会AHA/ACC", "year": 2023,
                "title": "2023 ACC/AHA Hypertension in Older Adults Scientific Statement",
                "url": "https://www.heart.org/xxx/hypertension-older-adults-2023",
                "summary": (
                    "For adults aged 65+, target BP <130/80mmHg if tolerated; "
                    "consider deintensification when SBP <130mmHg; "
                    "regular monitoring for orthostatic hypotension is recommended."
                ),
            },
            {
                "level": "A", "org": "欧洲心脏病学会ESC", "year": 2024,
                "title": "2024 ESC Guidelines for the management of elevated BP",
                "url": "https://www.escardio.org/xxx/2024-esh-esc-hypertension",
                "summary": (
                    "2024 ESC/ESH指南推荐65-79岁老年人目标血压130-139/70-79mmHg，"
                    "80岁以上老年人目标SBP 140-150mmHg，根据衰弱程度个体化。"
                ),
            },
            {
                "level": "B", "org": "丁香园", "year": 2025,
                "title": "老年高血压用药注意事项汇总",
                "url": "https://www.dxy.cn/xxx/elderly-hypertension",
                "summary": (
                    "注意α受体阻滞剂易致体位性低血压，老年患者慎用；"
                    "利尿剂需监测电解质；CCB类可能引起下肢水肿。"
                    "建议家庭自测血压，定期随访调整方案。【B级来源，仅供参考】"
                ),
            },
        ],
    }

    async def check_permissions(
        self,
        tool_input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionDecision:
        """权限检查：只读搜索默认允许执行。"""
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="医学文献检索为只读操作，允许执行。",
        )

    async def call(self, **kwargs: Any) -> ToolChunk:
        """执行搜索逻辑，返回格式化的搜索结果。"""
        params = self.Params(**kwargs)

        # 模拟网络延迟
        await asyncio.sleep(0.3)

        # 匹配mock数据（真实场景应调用Tavily/Serper/PubMed API）
        results = []
        for keyword, items in self._MOCK_DB.items():
            if keyword in params.query or params.query in keyword:
                results = items[: params.max_results]
                break

        if not results:
            results = [{
                "level": "C",
                "org": "通用搜索结果",
                "year": 2025,
                "title": f"关于'{params.query}'的参考信息",
                "url": "",
                "summary": (
                    f"未找到与'{params.query}'匹配的权威指南。"
                    "建议通过PubMed或NICE官网进一步检索，或咨询专科医生。"
                ),
            }]

        # 按年份过滤
        if params.year_from is not None:
            results = [r for r in results if r["year"] >= params.year_from]

        # 按数据源过滤
        if params.source == "guideline":
            results = [r for r in results if "指南" in r["title"] or "Guideline" in r["title"]]
        elif params.source == "pubmed":
            results = [r for r in results if "pubmed" in r.get("url", "") or r["org"] in ("PubMed", "NIH")]

        # 格式化为可读文本，每条结果标注来源等级
        lines = [f"=== 医学搜索结果（关键词：{params.query}，共{len(results)}条）===\n"]
        for i, r in enumerate(results, 1):
            level_tag = f"[{r['level']}级-{r['org']}, {r['year']}]"
            lines.append(f"{i}. {level_tag} {r['title']}")
            if r["url"]:
                lines.append(f"   URL: {r['url']}")
            lines.append(f"   摘要: {r['summary']}")
            lines.append("")

        lines.append("---")
        lines.append("免责声明：以上信息仅供医学参考，具体诊疗方案请遵医嘱。")

        result_text = "\n".join(lines)
        return ToolChunk(content=[TextBlock(text=result_text)])


# ============================================================
# 方式二：使用 FunctionTool 适配器包装搜索函数
# ============================================================

async def quick_drug_search(drug_name: str, region: str = "cn") -> str:
    """快速查询药品基本信息，包括适应症、老年用药注意事项。

    基于内置药品知识库查询常用老年慢病药品的关键信息。
    适用于快速确认药品基本用法和注意事项。

    Args:
        drug_name: 药品通用名或商品名，如'氨氯地平'、'二甲双胍'
        region: 地区: cn(中国NMPA)/us(美国FDA)/both(两者)
    """
    # 模拟药品数据库
    drug_db = {
        "氨氯地平": {
            "cn": (
                "【药品名称】苯磺酸氨氯地平片 (Amlodipine Besylate)\n"
                "【适应症】高血压、冠心病（慢性稳定型心绞痛）\n"
                "【老年用药】老年患者可用，但起始剂量宜小(2.5mg/日)，"
                "因老年人药物清除率降低，易发生体位性低血压。\n"
                "【常见不良反应】下肢水肿、面部潮红、头痛、心悸\n"
                "【来源】NMPA批准说明书 [S级来源]"
            ),
            "us": (
                "Drug: Amlodipine besylate (Norvasc)\n"
                "Indication: Hypertension, CAD\n"
                "Geriatric: Start at 2.5mg daily; increased sensitivity "
                "to hypotension in elderly. Monitor BP closely.\n"
                "Source: FDA Label [S级来源]"
            ),
        },
        "二甲双胍": {
            "cn": (
                "【药品名称】盐酸二甲双胍片 (Metformin HCl)\n"
                "【适应症】2型糖尿病\n"
                "【老年用药】65岁以上老年患者应定期监测肾功能，"
                "80岁以上不推荐起始使用；eGFR<30禁用。\n"
                "【注意事项】可能引起胃肠道反应，罕见乳酸酸中毒\n"
                "【来源】NMPA批准说明书 [S级来源]"
            ),
            "us": (
                "Drug: Metformin HCl (Glucophage)\n"
                "Indication: Type 2 Diabetes\n"
                "Geriatric: Assess renal function regularly; "
                "not recommended in patients >80yo unless normal renal function.\n"
                "Contraindicated if eGFR <30.\n"
                "Source: FDA Label [S级来源]"
            ),
        },
    }

    await asyncio.sleep(0.2)  # 模拟查询延迟

    drug_info = drug_db.get(drug_name)
    if drug_info is None:
        return (
            f"未找到药品'{drug_name}'的详细信息。建议查阅最新版药典或药品说明书，"
            f"具体用药请遵医嘱。"
        )

    if region == "both":
        return f"=== 药品查询：{drug_name} ===\n\n【中国NMPA】\n{drug_info['cn']}\n\n【美国FDA】\n{drug_info['us']}"
    elif region in ("cn", "us"):
        return f"=== 药品查询：{drug_name} ===\n\n{drug_info.get(region, drug_info['cn'])}"
    else:
        return f"未知的region参数'{region}'，支持cn/us/both。"


# ============================================================
# 主函数：注册工具到Toolkit，演示调用流程
# ============================================================

SYSTEM_PROMPT = (
    "你是GerClaw老年医疗AI平台的医生助手。"
    "当用户询问最新诊疗指南、药品信息、医学文献时，请使用提供的搜索工具查询。"
    "回答时：\n"
    "1. 优先引用S级和A级来源的信息\n"
    "2. 标注每条信息的来源等级和机构\n"
    "3. 如果不同来源有差异，请指出\n"
    "4. 回答末尾必须附加：'以上信息仅供参考，具体诊疗方案请遵医嘱。'\n"
    "5. 如用户描述紧急症状（胸痛/呼吸困难/意识障碍），立即建议拨打120"
)


async def demo_tool_registration() -> Toolkit:
    """演示两种工具的创建和注册到Toolkit。"""
    print("=" * 60)
    print("步骤1：创建并注册医学搜索工具到Toolkit")
    print("=" * 60)

    # 创建工具实例
    literature_tool = MedicalLiteratureSearchTool()
    drug_tool = FunctionTool(
        func=quick_drug_search,
        name="quick_drug_search",
        is_read_only=True,
        is_concurrency_safe=True,
    )

    # 注册到Toolkit
    toolkit = Toolkit(tools=[literature_tool, drug_tool])

    # 查看工具schema
    schemas = await toolkit.get_tool_schemas()
    print(f"\n已注册 {len(schemas)} 个工具：")
    for s in schemas:
        fn = s["function"]
        params = fn.get("parameters", {}).get("properties", {})
        param_names = list(params.keys())
        print(f"  - {fn['name']}")
        print(f"    描述: {fn['description'][:60]}...")
        print(f"    参数: {param_names}")

    return toolkit


async def demo_direct_tool_call(toolkit: Toolkit) -> None:
    """演示直接通过Toolkit调用工具（不经过Agent ReAct循环）。"""
    print("\n" + "=" * 60)
    print("步骤2：直接调用工具 — 搜索'老年高血压最新指南'")
    print("=" * 60)

    state = AgentState()

    # 构造工具调用：医学文献搜索
    tool_call = ToolCallBlock(
        id="call_literature_001",
        name="medical_literature_search",
        input=json.dumps({
            "query": "老年高血压最新指南",
            "max_results": 5,
            "year_from": 2020,
        }),
    )

    print(f"\n调用工具: {tool_call.name}")
    print(f"参数: {tool_call.input}\n")

    # 执行工具调用
    async for result in toolkit.call_tool(tool_call, state):
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    print(block.text)

    # 再演示药品搜索
    print("\n" + "=" * 60)
    print("步骤3：直接调用FunctionTool — 查询'氨氯地平'药品信息")
    print("=" * 60)

    tool_call_2 = ToolCallBlock(
        id="call_drug_001",
        name="quick_drug_search",
        input=json.dumps({"drug_name": "氨氯地平", "region": "cn"}),
    )

    print(f"\n调用工具: {tool_call_2.name}")
    print(f"参数: {tool_call_2.input}\n")

    async for result in toolkit.call_tool(tool_call_2, state):
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    print(block.text)


async def demo_agent_with_model(toolkit: Toolkit) -> None:
    """当DASHSCOPE_API_KEY存在时，演示Agent真实ReAct推理调用工具。"""
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        print("\n" + "=" * 60)
        print("步骤4：Agent推理演示（跳过）")
        print("=" * 60)
        print("未检测到 DASHSCOPE_API_KEY 环境变量，跳过Agent推理演示。")
        print("如需运行Agent推理，请设置: export DASHSCOPE_API_KEY='your-key'")
        print("\n示例运行完成。")
        return

    print("\n" + "=" * 60)
    print("步骤4：Agent真实推理演示（DashScope模型）")
    print("=" * 60)

    # 初始化模型
    model = DashScopeChatModel(
        credential=DashScopeCredential(api_key=api_key),
        model="qwen3.5-plus",
        stream=False,
        context_size=131072,
    )

    # 手动模拟单轮ReAct：用户问题 → 模型选择工具 → 工具结果 → 最终回答
    tools = await toolkit.get_tool_schemas()

    msgs = [
        Msg(
            name="system",
            role="system",
            content=[TextBlock(text=SYSTEM_PROMPT)],
        ),
        Msg(
            name="user",
            role="user",
            content=[TextBlock(text="老年高血压患者的降压目标是多少？最新指南怎么推荐？")],
        ),
    ]

    print("\n[Round 1] 发送问题给模型，等待工具调用决策...")
    response = await model(msgs, tools=tools)
    assistant_content = response.content if response else []

    tool_calls = [b for b in assistant_content if isinstance(b, ToolCallBlock)]
    text_blocks = [b for b in assistant_content if isinstance(b, TextBlock)]

    for tb in text_blocks:
        print(f"模型思考: {tb.text[:200]}")

    if not tool_calls:
        print("模型未选择调用工具，直接回答：")
        for tb in text_blocks:
            print(tb.text)
        return

    # 执行工具调用
    state = AgentState()
    tool_result_blocks = []
    for tc in tool_calls:
        print(f"\n模型决定调用工具: {tc.name}, 参数: {tc.input[:200]}")
        args = json.loads(tc.input)
        async for result in toolkit.call_tool(tc, state):
            if hasattr(result, "content"):
                result_text = ""
                for block in result.content:
                    if hasattr(block, "text"):
                        result_text += block.text
                tool_result_blocks.append(
                    ToolResultBlock(
                        id=tc.id,
                        name=tc.name,
                        output=result_text,
                        state=ToolResultState.SUCCESS,
                    )
                )

    # 组装第二轮消息
    assistant_msg = Msg(
        name="doctor_agent",
        role="assistant",
        content=assistant_content,
    )
    tool_msg = Msg(
        name="tool",
        role="assistant",
        content=tool_result_blocks,
    )
    msgs = msgs + [assistant_msg, tool_msg]

    print("\n[Round 2] 将工具结果发送给模型，生成最终回答...")
    response2 = await model(msgs, tools=tools)
    final_text = ""
    for block in (response2.content if response2 else []):
        if isinstance(block, TextBlock):
            final_text += block.text

    print(f"\n最终回答:\n{final_text}")
    print("\n示例运行完成。")


async def main() -> None:
    """主入口：注册工具 → 直接调用演示 → Agent推理演示。"""
    print("GerClaw 老年医疗AI平台 — 医学搜索工具演示")
    print("AgentScope ToolBase / FunctionTool 双模式示例\n")

    toolkit = await demo_tool_registration()
    await demo_direct_tool_call(toolkit)
    await demo_agent_with_model(toolkit)


if __name__ == "__main__":
    asyncio.run(main())
