import type { BookOut } from "@/api/schemas/book";

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

export function pageRange(
  start: number | null,
  end: number | null,
): string | null {
  if (start == null && end == null) return null;
  if (start != null && end != null && start !== end) return `pp. ${start}–${end}`;
  return `p. ${start ?? end}`;
}

export function breadcrumb(section_path: string[] | null): string | null {
  return section_path?.length ? section_path.join(" › ") : null;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${Math.round(kb)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}
