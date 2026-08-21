/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL || "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Server-side proxy so browser code only ever talks to same-origin /api/*.
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
