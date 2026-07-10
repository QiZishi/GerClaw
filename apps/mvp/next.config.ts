import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
