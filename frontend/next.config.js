/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Phase 8: SWC 编译器优化
  swcMinify: true,

  // Phase 8: 生产环境移除 console（保留 error）
  compiler: {
    removeConsole: process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false,
  },

  // Phase 8: 优化大型包导入
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts", "react-hot-toast"],
  },

  // Phase 8: 图片优化
  images: {
    formats: ["image/avif", "image/webp"],
  },

  // Phase 8: 静态资源缓存头
  async headers() {
    return [
      {
        source: "/_next/static/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
      {
        source: "/favicon.ico",
        headers: [
          { key: "Cache-Control", value: "public, max-age=86400" },
        ],
      },
    ];
  },

  // Phase 8: 压缩
  compress: true,

  // Phase 8: powered by header 移除（安全）
  poweredByHeader: false,
};

module.exports = nextConfig;
