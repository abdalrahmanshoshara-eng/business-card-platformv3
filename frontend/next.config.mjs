/** @type {import('next').NextConfig} */
const rawBackendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';
const backendUrl = rawBackendUrl.replace(/\/$/, '');

const nextConfig = {
  trailingSlash: false,
  compress: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${backendUrl}/api/:path*` },
      { source: '/media/:path*', destination: `${backendUrl}/media/:path*` },
    ];
  },
  images: {
    remotePatterns: [
      { protocol: 'http', hostname: '127.0.0.1', port: '8000', pathname: '/media/**' },
      { protocol: 'http', hostname: 'localhost', port: '8000', pathname: '/media/**' },
      { protocol: 'http', hostname: '0.0.0.0', port: '8000', pathname: '/media/**' },
      { protocol: 'http', hostname: 'backend', port: '8000', pathname: '/media/**' },
    ],
  },
};

export default nextConfig;
