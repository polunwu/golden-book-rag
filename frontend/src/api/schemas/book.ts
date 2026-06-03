import { z } from "zod";

// Hand-written mirror of the backend book shapes (api/schemas.py). The boundary
// parse validates structure (fields + types); unknown keys are stripped by zod's
// default object behaviour, so additive backend fields don't break the FE.
// `id` / `created_at` are opaque backend-owned strings — no uuid/datetime format
// policing here (the backend owns those formats).

export const BookStatus = z.enum(["pending", "processing", "ready", "failed"]);
export type BookStatus = z.infer<typeof BookStatus>;

export const BookOut = z.object({
  id: z.string(),
  title: z.string().nullable(),
  file_path: z.string().nullable(),
  created_at: z.string(),
  status: BookStatus,
  error_message: z.string().nullable().optional(),
});
export type BookOut = z.infer<typeof BookOut>;

export const BookList = z.object({
  items: z.array(BookOut),
});
export type BookList = z.infer<typeof BookList>;

export const UploadResponse = z.object({
  book_id: z.string(),
  status: BookStatus,
});
export type UploadResponse = z.infer<typeof UploadResponse>;
