import type { MetadataRoute } from "next";

// D10 — keep the app out of search indexes. Polite-crawler deterrent only; the
// real privacy gate is auth (D1). Pairs with the root metadata.robots noindex.
export default function robots(): MetadataRoute.Robots {
  return { rules: { userAgent: "*", disallow: "/" } };
}
