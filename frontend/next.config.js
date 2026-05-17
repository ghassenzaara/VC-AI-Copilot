/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Clerk middleware uses Node APIs (crypto, etc.) that aren't available on the
  // Edge runtime. Opt the middleware into the Node.js runtime so Vercel can
  // bundle it without "unsupported modules" errors.
  experimental: {
    nodeMiddleware: true,
  },
};

module.exports = nextConfig;
