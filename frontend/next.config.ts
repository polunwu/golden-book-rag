import type { NextConfig } from "next";

// Dev origin: the browser only ever talks to the Next origin; Next
// rewrites /api/* to the backend, stripping the /api prefix (backend routes are
// /books, not /api/books). No CORS, backend untouched. The same rewrite runs on
// the Next server in prod (single origin). The backend target is env-overridable
// for non-local deploys; defaults to the dev backend.
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Next buffers the proxied request body with a 10MB default cap; a larger PDF gets
  // truncated mid-stream, so the rewrite to the backend dies with ECONNRESET (a 500
  // the backend never even sees). Lift it to match the app's upload ceiling.
  experimental: {
    proxyClientMaxBodySize: "110mb",
  },
  // The app never uses next/image, so turn the optimizer off: `/_next/image` is
  // otherwise served by default and is a recurring source of RCE/SSRF advisories.
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
};

export default nextConfig;
