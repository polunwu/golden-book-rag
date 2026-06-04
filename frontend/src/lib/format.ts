import type { BookOut } from "../api/schemas/book";

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function bookTitle(book: Pick<BookOut, "title">): string {
  return book.title?.trim() || "Untitled";
}
