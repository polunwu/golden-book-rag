import { z } from "zod";
import { ChunkBase } from "./chunk";

// Mirrors api/schemas.py search shapes. SearchRequest's `k` carries the backend's
// 1..20 bound + default 5 so the FE can validate before sending.
export const SearchRequest = z.object({
  query: z.string().min(1),
  k: z.number().int().min(1).max(20).default(5),
});
export type SearchRequest = z.infer<typeof SearchRequest>;

export const SearchHit = ChunkBase.extend({
  score: z.number(),
});
export type SearchHit = z.infer<typeof SearchHit>;

export const SearchResponse = z.object({
  book_id: z.string(),
  query: z.string(),
  k: z.number().int(),
  hits: z.array(SearchHit),
});
export type SearchResponse = z.infer<typeof SearchResponse>;
