/**
 * CGA 量表题目预录音频生成脚本
 *
 * 读取 src/data/scales.ts 中的题目文本，调用 MiMo TTS API 合成为 WAV 音频文件，
 * 保存到 public/audio/scales/{scaleId}_{questionId}.wav。
 *
 * 用法：node scripts/generate-cga-audio.mjs
 *
 * 配置来源：apps/mvp/.env.local
 *   - NEXT_PUBLIC_TTS_URL
 *   - NEXT_PUBLIC_TTS_API_KEY
 *   - NEXT_PUBLIC_TTS_MODEL（默认 mimo-v2.5-tts）
 *   - NEXT_PUBLIC_TTS_VOICE（默认 冰糖）
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ---------- .env.local 解析 ----------
function loadEnv(filePath) {
  const env = {};
  if (!fs.existsSync(filePath)) return env;
  const content = fs.readFileSync(filePath, "utf-8");
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eqIdx = trimmed.indexOf("=");
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const value = trimmed.slice(eqIdx + 1).trim();
    env[key] = value;
  }
  return env;
}

const env = loadEnv(path.join(__dirname, "..", ".env.local"));

const TTS_URL = (env.NEXT_PUBLIC_TTS_URL || "").replace(/\/+$/, "");
const TTS_API_KEY = env.NEXT_PUBLIC_TTS_API_KEY || "";
const TTS_MODEL = env.NEXT_PUBLIC_TTS_MODEL || "mimo-v2.5-tts";
const TTS_VOICE = env.NEXT_PUBLIC_TTS_VOICE || "冰糖";

if (!TTS_URL || !TTS_API_KEY) {
  console.error("❌ TTS_URL 或 TTS_API_KEY 未配置，请检查 .env.local");
  process.exit(1);
}

const ttsEndpoint = `${TTS_URL}/chat/completions`;

// ---------- 量表题目数据（镜像 src/data/scales.ts，不修改原文件） ----------
const scales = [
  {
    id: "scale_phq9",
    name: "PHQ-9",
    questions: [
      { id: "phq9_1", text: "过去两周内，做事时提不起兴趣或乐趣" },
      { id: "phq9_2", text: "感到心情低落、沮丧或绝望" },
      { id: "phq9_3", text: "入睡困难、睡不安稳或睡眠过多" },
      { id: "phq9_4", text: "感觉疲倦或没有活力" },
      { id: "phq9_5", text: "食欲不振或暴饮暴食" },
      { id: "phq9_6", text: "觉得自己很糟，或觉得自己很失败，或让家人失望" },
      { id: "phq9_7", text: "对事物专注有困难（如阅读报纸或看电视）" },
      { id: "phq9_8", text: "动作或说话缓慢到他人已察觉，或正好相反—烦躁或坐立不安" },
      { id: "phq9_9", text: "有不如死掉或用某种方式伤害自己的念头" },
    ],
  },
  {
    id: "scale_sas",
    name: "GAD-7",
    questions: [
      { id: "gad7_1", text: "感到紧张、焦虑或急躁" },
      { id: "gad7_2", text: "不能停止或控制担忧" },
      { id: "gad7_3", text: "对各种各样的事情担忧过多" },
      { id: "gad7_4", text: "很难放松下来" },
      { id: "gad7_5", text: "坐立不安，难以静下来" },
      { id: "gad7_6", text: "变得容易烦恼或急躁" },
      { id: "gad7_7", text: "感到似乎将有可怕的事情发生而害怕" },
    ],
  },
  {
    id: "scale_psqi",
    name: "PSQI",
    questions: [
      { id: "psqi_1", text: "近一个月，每晚实际睡眠时间" },
      { id: "psqi_2", text: "近一个月，入睡时间（上床到睡着）" },
      { id: "psqi_3", text: "近一个月，因夜间易醒或早醒影响睡眠" },
      { id: "psqi_4", text: "近一个月，整体睡眠质量" },
      { id: "psqi_5", text: "近一个月，是否使用催眠药物" },
      { id: "psqi_6", text: "近一个月，因呼吸不畅、咳嗽、打鼾等影响睡眠" },
      { id: "psqi_7", text: "近一个月，白天是否感到困倦、精力不足" },
    ],
  },
  {
    id: "scale_minicog",
    name: "Mini-Cog",
    questions: [
      { id: "mc_1", text: "请仔细听并记住：苹果、桌子、硬币（词 1）" },
      { id: "mc_2", text: "请在白纸上画一个时钟，标注所有数字，并指向 11:10" },
      { id: "mc_3", text: "回忆第一个词：苹果" },
      { id: "mc_4", text: "回忆第二个词：桌子" },
      { id: "mc_5", text: "回忆第三个词：硬币" },
    ],
  },
  {
    id: "scale_mmse",
    name: "MMSE",
    questions: [
      { id: "mmse_1", text: "今年的年份是多少？" },
      { id: "mmse_2", text: "现在是什么季节？" },
      { id: "mmse_3", text: "现在是几月份？" },
      { id: "mmse_4", text: "今天是几号？" },
      { id: "mmse_5", text: "今天是星期几？" },
      { id: "mmse_6", text: "我们现在在哪个国家？" },
      { id: "mmse_7", text: "我们现在在哪个城市？" },
      { id: "mmse_8", text: "我们现在在什么地方？（如医院、家里等）" },
      { id: "mmse_9", text: "我们现在在第几层楼/哪个房间？" },
      { id: "mmse_10", text: "我们现在在哪个省/市？" },
      { id: "mmse_11", text: "请复述：皮球" },
      { id: "mmse_12", text: "请复述：国旗" },
      { id: "mmse_13", text: "请复述：树木" },
      { id: "mmse_14", text: "100 减 7 等于多少？" },
      { id: "mmse_15", text: "再减 7 等于多少？" },
      { id: "mmse_16", text: "再减 7 等于多少？" },
      { id: "mmse_17", text: "再减 7 等于多少？" },
      { id: "mmse_18", text: "再减 7 等于多少？" },
      { id: "mmse_19", text: "回忆刚才说的第一个词：皮球" },
      { id: "mmse_20", text: "回忆刚才说的第二个词：国旗" },
      { id: "mmse_21", text: "回忆刚才说的第三个词：树木" },
      { id: "mmse_22", text: "（出示手表）这是什么？" },
      { id: "mmse_23", text: "（出示铅笔）这是什么？" },
      { id: "mmse_24", text: "请复述：'四十四只石狮子'" },
      { id: "mmse_25", text: "请按指令做：用右手拿这张纸" },
      { id: "mmse_26", text: "请按指令做：用两手把纸对折" },
      { id: "mmse_27", text: "请按指令做：将纸放在大腿上" },
      { id: "mmse_28", text: "请念这句话并做动作：'闭上您的眼睛'" },
      { id: "mmse_29", text: "请写一个完整的句子（有主语、谓语，有意义）" },
      { id: "mmse_30", text: "请照下图画两个相交的五边形" },
    ],
  },
];

// ---------- 输出目录 ----------
const outputDir = path.join(__dirname, "..", "public", "audio", "scales");
fs.mkdirSync(outputDir, { recursive: true });

// ---------- TTS 调用 ----------
async function tts(text) {
  const body = {
    model: TTS_MODEL,
    messages: [{ role: "assistant", content: text }],
    audio: { format: "wav", voice: TTS_VOICE },
    stream: false,
  };

  const res = await fetch(ttsEndpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TTS_API_KEY}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }

  const json = await res.json();
  const audioBase64 = json?.choices?.[0]?.message?.audio?.data;
  if (!audioBase64 || typeof audioBase64 !== "string") {
    throw new Error("响应中未找到音频数据 (choices[0].message.audio.data)");
  }
  return Buffer.from(audioBase64, "base64");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- 主流程 ----------
async function main() {
  const tasks = [];
  for (const scale of scales) {
    for (const q of scale.questions) {
      tasks.push({ scaleId: scale.id, questionId: q.id, text: q.text });
    }
  }

  console.log("=".repeat(60));
  console.log("📋 CGA 量表题目音频批量生成");
  console.log("=".repeat(60));
  console.log(`🔢 共 ${tasks.length} 个题目待合成`);
  console.log(`🎯 TTS Endpoint: ${ttsEndpoint}`);
  console.log(`🔊 Model: ${TTS_MODEL} | Voice: ${TTS_VOICE}`);
  console.log(`📁 输出目录: ${outputDir}`);
  console.log(`⏱️  每次调用间隔 500ms`);
  console.log("-".repeat(60));

  let success = 0;
  let failed = 0;
  const failures = [];

  for (let i = 0; i < tasks.length; i++) {
    const { scaleId, questionId, text } = tasks[i];
    const filename = `${scaleId}_${questionId}.wav`;
    const filepath = path.join(outputDir, filename);

    const tag = `[${String(i + 1).padStart(2, "0")}/${String(tasks.length).padStart(2, "0")}]`;
    process.stdout.write(`${tag} ${filename.padEnd(36)} `);

    try {
      const buf = await tts(text);
      if (buf.length === 0) {
        throw new Error("合成数据为空");
      }
      fs.writeFileSync(filepath, buf);
      console.log(`✅ ${buf.length.toLocaleString()} bytes`);
      success++;
    } catch (err) {
      console.log(`❌ ${err.message}`);
      failures.push({ filename, text, error: err.message });
      failed++;
    }

    if (i < tasks.length - 1) {
      await sleep(500);
    }
  }

  console.log("-".repeat(60));
  console.log(`✅ 成功: ${success}`);
  console.log(`❌ 失败: ${failed}`);
  console.log(`📊 总计: ${tasks.length}`);

  if (failures.length > 0) {
    console.log("\n失败明细:");
    for (const f of failures) {
      console.log(`  - ${f.filename}`);
      console.log(`      文本: ${f.text}`);
      console.log(`      错误: ${f.error}`);
    }
  }

  // 退出码：有失败时返回 1，便于 CI 检测
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error("脚本执行异常:", err);
  process.exit(1);
});
