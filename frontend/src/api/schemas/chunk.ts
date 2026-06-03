import { z } from "zod";

// Shared base for every chunk-derived shape, mirroring services/types.py
// ChunkBase. SearchHit (search.ts) and Citation (ask.ts) extend it, matching the
// backend's inheritance so the field set stays defined in one place.
export const ChunkBase = z.object({
  chunk_index: z.number().int(),
  text: z.string(),
  page_start: z.number().int().nullable(),
  page_end: z.number().int().nullable(),
  section_path: z.array(z.string()).nullable(),
  section_title: z.string().nullable(),
  section_level: z.number().int().nullable(),
});
export type ChunkBase = z.infer<typeof ChunkBase>;

// ChunkOut adds nothing over ChunkBase (api/schemas.py: `class ChunkOut(ChunkBase)`).
export const ChunkOut = ChunkBase;
export type ChunkOut = z.infer<typeof ChunkOut>;

export const ChunkPage = z.object({
  items: z.array(ChunkOut),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type ChunkPage = z.infer<typeof ChunkPage>;
