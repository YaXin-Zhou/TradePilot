/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // Docker: 静态导出 -> Nginx
  output: "export",

  // Phase 8: SWC 编译器优化
  swcMinify: true,

  // Phase 8: 生产环境移除 console（保留 error）
  compiler: {
    removeConsole: process.env.NODE_ENV === "production" ? { exclude: ["error"] } : false,
  },

  // Phase 8: 优化大型包导入
  experimental: {
    scrollRestoration: true,
    optimizePackageImports: ["lucide-react", "recharts", "react-hot-toast"],
  },

  // Docker 静态导出：禁用图片优化（Nginx 直接提供）
  images: {
    unoptimized: true,
  },

  // Phase 8: powered by header 移除（安全）
  poweredByHeader: false,
};

module.exports = nextConfig;
