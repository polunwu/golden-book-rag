import type { Metadata } from "next";
import Link from "next/link";
import { Providers } from "./providers";
import "./globals.css";

// D10 — non-indexed app-wide: robots noindex/nofollow propagates to every route
// from the root layout. Cheap crawler deterrent, NOT access control (auth is the
// real gate). Paired with app/robots.ts.
export const metadata: Metadata = {
  title: "golden-book-rag",
  robots: { index: false, follow: false },
};

// N1 — root layout: chrome (header/nav) + the App Router <Outlet> equivalent
// ({children}), wrapped in the client Providers boundary. Every route nests here.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-50 text-zinc-900">
        <Providers>
          <header className="border-b border-zinc-200 bg-white">
            <nav className="mx-auto flex max-w-3xl items-center px-4 py-3">
              <Link href="/" className="font-semibold">
                Ask your book
              </Link>
            </nav>
          </header>
          <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
