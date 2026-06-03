import { request } from "./client";
import { BookList, type BookOut } from "./schemas/book";

// N7 — the only endpoint wired this step (R2.3). Adding more (getBook, ask, …)
// is a one-liner against `request` + the matching resource schema.
export async function listBooks(): Promise<BookOut[]> {
  const data = await request("/books", BookList);
  return data.items;
}

export type { BookOut };
