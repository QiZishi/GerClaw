import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const appDirectory = dirname(scriptDirectory);
const publicDirectory = join(appDirectory, "public");
const manifestPath = join(publicDirectory, "audio", "cga", "manifest.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

if (manifest.schema_version !== 1 || !Array.isArray(manifest.scales)) {
  throw new Error("CGA 音频清单格式无效。");
}

const assets = new Map();
for (const question of manifest.scales) {
  if (!question.scale_id || !question.definition_version || !question.question_id) {
    throw new Error("CGA 音频清单缺少版本绑定字段。");
  }
  assets.set(question.question.path, question.question);
  for (const option of question.options) assets.set(option.audio.path, option.audio);
}

const expectedQuestionCounts = new Map([
  ["phq9", 9],
  ["sas", 20],
  ["psqi", 19],
  ["minicog", 3],
  ["mmse", 31],
]);
const actualQuestionCounts = new Map();
for (const question of manifest.scales) {
  actualQuestionCounts.set(question.scale_id, (actualQuestionCounts.get(question.scale_id) ?? 0) + 1);
}
if (
  manifest.scales.length !== 82 ||
  assets.size !== 123 ||
  actualQuestionCounts.size !== expectedQuestionCounts.size ||
  [...expectedQuestionCounts].some(([scaleId, count]) => actualQuestionCounts.get(scaleId) !== count)
) {
  throw new Error(
    "CGA 音频资产数量或量表覆盖异常：题干 " + manifest.scales.length + "，唯一资源 " + assets.size + "。"
  );
}

for (const [url, asset] of assets) {
  if (typeof url !== "string" || !url.startsWith("/audio/cga/")) {
    throw new Error("CGA 音频路径不在受限静态目录内。");
  }
  const audio = readFileSync(join(publicDirectory, url.slice(1)));
  const sha256 = createHash("sha256").update(audio).digest("hex");
  if (
    audio.length < 44 ||
    audio.subarray(0, 4).toString() !== "RIFF" ||
    audio.subarray(8, 12).toString() !== "WAVE" ||
    audio.length !== asset.bytes ||
    sha256 !== asset.sha256
  ) {
    throw new Error("CGA 音频完整性校验失败：" + url);
  }
}

console.log("已校验 " + manifest.scales.length + " 个题干和 " + assets.size + " 个版本绑定 WAV 资源。");
