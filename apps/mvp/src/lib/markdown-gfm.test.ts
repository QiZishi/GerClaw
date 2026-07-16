import assert from "node:assert/strict";
import test from "node:test";

import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";

import { MARKDOWN_GFM_OPTIONS } from "./markdown-gfm.ts";

function parsedTree(markdown: string): string {
  const processor = unified().use(remarkParse).use(remarkGfm, MARKDOWN_GFM_OPTIONS);
  return JSON.stringify(processor.runSync(processor.parse(markdown)));
}

test("keeps single-tilde numeric ranges as literal clinical text", () => {
  const tree = parsedTree("每天早晚各测2~3次，连续5~7天");

  assert.doesNotMatch(tree, /"type":"delete"/);
  assert.match(tree, /2~3次/);
  assert.match(tree, /5~7天/);
});

test("preserves explicit double-tilde deletion support", () => {
  assert.match(parsedTree("~~已撤销~~"), /"type":"delete"/);
});
