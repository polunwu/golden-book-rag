import { z } from "zod";
import { ChunkBase } from "./chunk";
import { SearchRequest } from "./search";

// Mirrors api/schemas.py ask shapes. AskRequest is SearchRequest verbatim
// (backend: `class AskRequest(SearchRequest)`); re-exported so the ask resource
// owns its own name.
export const AskRequest = SearchRequest;
export type AskRequest = z.infer<typeof AskRequest>;

export const Citation = ChunkBase.extend({
  marker: z.number().int(),
  score: z.number(),
});
export type Citation = z.infer<typeof Citation>;

export const AskResponse = z.object({
  book_id: z.string(),
  query: z.string(),
  k: z.number().int(),
  answer: z.string(),
  refused: z.boolean(),
  citations: z.array(Citation),
});
export type AskResponse = z.infer<typeof AskResponse>;
