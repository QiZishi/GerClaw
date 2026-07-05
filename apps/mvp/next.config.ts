import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 静态导出，适配 IGA Pages 部署（ADR-001）
  output: "export",
  // 静态导出时关闭图片优化（需要服务端）
  images: {
    unoptimized: true,
  },
  // 开发期允许任意源（生产环境部署在 IGA Pages，无服务端）
  // 注意：turbopack 在 Next.js 16 中是默认的，无需 --turbopack 标志
};

export default nextConfig;
