import assert from "node:assert/strict";
import test from "node:test";

import {
  projectPublicAnalysis,
  projectPublicTool,
} from "./public-execution-projection.ts";

test("完成态保留服务端公开摘要但不添加内部机制", () => {
  const projection = projectPublicAnalysis({
    id: "analysis-1",
    content: "已整理与跌倒风险相关的信息",
    status: "done",
    startedAt: 1,
  });

  assert.deepEqual(projection, {
    label: "公开执行摘要",
    detail: "已整理与跌倒风险相关的信息",
    expandable: true,
  });
});

test("运行态分析只投影服务端提供的公开阶段摘要", () => {
  const projection = projectPublicAnalysis({
    id: "analysis-2",
    content: "正在整理与跌倒风险相关的信息",
    status: "thinking",
    startedAt: 1,
  });

  assert.equal(projection.detail, "正在整理与跌倒风险相关的信息");
  assert.equal(projection.expandable, true);
});

test("通用工具只公开服务端结果摘要，不公开内部参数或错误载荷", () => {
  const projection = projectPublicTool({
    id: "tool-1",
    toolName: "internal_provider_adapter",
    status: "failed",
    startedAt: 1,
    params: { apiKey: "secret", prompt: "private" },
    result: { raw: "provider payload" },
    errorMessage: "stack trace",
    resultSummary: "本步骤未完成，已继续使用其他可用信息",
  });

  assert.deepEqual(projection, {
    label: "辅助处理",
    statusLabel: "暂时不可用",
    resultSummary: "本步骤未完成，已继续使用其他可用信息",
    expandable: true,
  });
  assert.doesNotMatch(JSON.stringify(projection), /secret|private|provider|stack|internal_provider_adapter/);
});
