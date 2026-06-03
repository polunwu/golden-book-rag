import type { NextConfig } from "next";

// Dev origin (D8/G1-A): the browser only ever talks to the Next origin; Next
// rewrites /api/* to the backend, stripping the /api prefix (backend routes are
// /books, not /api/books). No CORS, backend untouched. The same rewrite runs on
// the Next server in prod (single origin). The backend target is env-overridable
// for non-local deploys; defaults to the dev backend.
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
};

export default nextConfig;
