import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import nextEnv from "@next/env";

const { loadEnvConfig } = nextEnv;
const allowedPublicKeys = new Set([
  "NEXT_PUBLIC_APP_NAME",
  "NEXT_PUBLIC_APP_VERSION",
]);

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const appDirectory = path.resolve(scriptDirectory, "..");
const repositoryRoot = path.resolve(appDirectory, "../..");
const nextArguments = process.argv.slice(2);

if (nextArguments.length === 0) {
  throw new Error("需要提供 Next.js 命令，例如 dev、build 或 start");
}

// Next.js 只自动加载应用目录的 .env*。仓库将服务端配置统一放在根目录，
// 因此在启动子进程前显式加载。NEXT_PUBLIC_ 会进入浏览器包，故只允许显示文案。
loadEnvConfig(repositoryRoot, nextArguments[0] === "dev");

const unsafePublicKeys = Object.keys(process.env).filter(
  (key) =>
    key.startsWith("NEXT_PUBLIC_") &&
    !allowedPublicKeys.has(key) &&
    Boolean(process.env[key]?.trim()),
);

if (unsafePublicKeys.length > 0) {
  throw new Error(
    `只允许 NEXT_PUBLIC_APP_NAME 与 NEXT_PUBLIC_APP_VERSION：${unsafePublicKeys.join(", ")}`,
  );
}

const nextBin = path.join(appDirectory, "node_modules", "next", "dist", "bin", "next");
const child = spawn(process.execPath, [nextBin, ...nextArguments], {
  cwd: appDirectory,
  env: process.env,
  stdio: "inherit",
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}

child.on("error", (error) => {
  console.error("无法启动 Next.js：", error.message);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});
