/** @type {import('next').NextConfig} */
const apiInternal = process.env.API_INTERNAL_URL || "http://127.0.0.1:8000";

const nextConfig = {
  // Docker 生产镜像用 standalone 输出
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiInternal}/api/:path*` }];
  },
};

module.exports = nextConfig;
