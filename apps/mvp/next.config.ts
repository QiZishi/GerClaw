import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "node:path";

// 全栈开发统一使用仓库根 .env。只有显式 NEXT_PUBLIC_ 变量会进入浏览器包；
// Provider key 仅供 Node.js API Route 使用。
loadEnvConfig(path.resolve(process.cwd(), "../.."));

const allowedPublicKeys = new Set([
  "NEXT_PUBLIC_APP_NAME",
  "NEXT_PUBLIC_APP_VERSION",
]);
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

const nextConfig: NextConfig = {
  // 生成可独立运行的最小 Node.js 产物，供生产 Docker 镜像使用。
  output: "standalone",
  // `app.py` 明确向用户展示 127.0.0.1 地址；允许它与 localhost 一样接入
  // 开发期 HMR，避免正常本地体验持续产生跨源 WebSocket 报错。
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // 使用服务端运行时以支持 API Routes（LLM/ASR/TTS/搜索代理）
  // 解决浏览器端直接调用外部 API 的 CORS 问题
  // 部署时需选择支持 Node.js 运行时的平台（如 Vercel / IGA Pages with Functions）
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "www.google.com",
        pathname: "/s2/favicons/**",
      },
      {
        protocol: "https",
        hostname: "**",
      },
    ],
  },
};

export default nextConfig;
