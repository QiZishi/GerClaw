import assert from "node:assert/strict";
import test from "node:test";

import {
  projectPublicAnalysis,
  projectPublicTool,
} from "./public-execution-projection.ts";

test("完成态分析不公开内部机制说明或可展开详情", () => {
  const projection = projectPublicAnalysis({
    content: "模型内部推理、检查点和安全策略",
    status: "done",
  });

  assert.deepEqual(projection, {
    label: "分析已完成",
    detail: null,
    expandable: false,
  });
});

test("运行态分析只投影服务端提供的公开阶段摘要", () => {
  const projection = projectPublicAnalysis({
    content: "正在整理与跌倒风险相关的信息",
    status: "thinking",
  });

  assert.equal(projection.detail, "正在整理与跌倒风险相关的信息");
  assert.equal(projection.expandable, true);
});

test("通用工具不公开内部名称、参数、结果或错误载荷", () => {
  const projection = projectPublicTool({
    id: "tool-1",
    toolName: "internal_provider_adapter",
    status: "failed",
    startedAt: 1,
    params: { apiKey: "secret", prompt: "private" },
    result: { raw: "provider payload" },
    errorMessage: "stack trace",
  });

  assert.deepEqual(projection, {
    label: "辅助处理",
    statusLabel: "暂时不可用",
    expandable: false,
  });
  assert.doesNotMatch(JSON.stringify(projection), /secret|private|provider|stack|internal_provider_adapter/);
});
