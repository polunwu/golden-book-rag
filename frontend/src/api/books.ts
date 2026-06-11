import { z } from "zod";
import { request } from "./client";
import { BookList, BookOut, UploadResponse } from "./schemas/book";
import { AskResponse, type AskRequest } from "./schemas/ask";

export async function listBooks(): Promise<BookOut[]> {
  const data = await request("/books", BookList);
  return data.items;
}

export async function getBook(id: string): Promise<BookOut> {
  return request(`/books/${id}`, BookOut);
}

// `id` is a route uuid, not user input, so it goes straight into the path.
export async function ask(
  id: string,
  body: AskRequest,
  retrieve: boolean,
): Promise<AskResponse> {
  const path = `/books/${id}/ask${retrieve ? "" : "?retrieve=false"}`;
  return request(path, AskResponse, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// `bookId` present ⇒ re-upload: the backend upserts that row to `pending` and
// clears `error_message`. Omitted ⇒ a fresh upload. The browser sets the
// multipart content-type (with boundary) for a FormData body; `request` leaves
// it alone.
export async function uploadBook(
  file: File,
  title: string,
  bookId?: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  if (bookId) form.append("book_id", bookId);
  return request("/books/upload", UploadResponse, {
    method: "POST",
    body: form,
  });
}

// `204 No Content` — the wrapper's 204 path validates against `z.void()`
// (no body to parse). Backend cascades chunks/embeddings and unlinks the PDF.
export async function deleteBook(id: string): Promise<void> {
  await request(`/books/${id}`, z.void(), { method: "DELETE" });
}

export type { BookOut };
export type { UploadResponse } from "./schemas/book";
export type { AskResponse, Citation } from "./schemas/ask";
