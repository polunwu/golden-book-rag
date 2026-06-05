import { request } from "./client";
import { BookList, BookOut } from "./schemas/book";
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

export type { BookOut };
export type { AskResponse, Citation } from "./schemas/ask";
