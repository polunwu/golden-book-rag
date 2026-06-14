import type { Metadata } from "next";
import Link from "next/link";
import { AuthIndicator } from "@/components/ui";
import { Providers } from "./providers";
import "./globals.css";

// Non-indexed app-wide: robots noindex/nofollow propagates to every route
// from the root layout. Cheap crawler deterrent, NOT access control (auth is the
// real gate). Paired with app/robots.ts.
export const metadata: Metadata = {
  title: "Ask your book",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen overflow-x-clip">
        <Providers>
          <header className="border-b border-rule">
            <nav className="mx-auto flex max-w-3xl flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-5">
              <Link
                href="/"
                className="rounded-sm text-lg tracking-tight text-ink transition-colors hover:text-ink-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-status-processing focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
              >
                Ask your book
              </Link>
              <span className="font-sans text-xs text-ink-muted">
                grounded answers from your own books
              </span>
              <span className="ml-auto">
                <AuthIndicator />
              </span>
            </nav>
          </header>
          <main className="mx-auto max-w-3xl px-5 py-12">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
