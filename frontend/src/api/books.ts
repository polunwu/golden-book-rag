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

// New uploads only — `book_id` (re-upload) is a later step. The browser sets
// the multipart content-type (with boundary) for a FormData body; `request`
// leaves it alone.
export async function uploadBook(
  file: File,
  title: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  return request("/books/upload", UploadResponse, {
    method: "POST",
    body: form,
  });
}

export type { BookOut };
export type { UploadResponse } from "./schemas/book";
export type { AskResponse, Citation } from "./schemas/ask";
