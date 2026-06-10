"use client";

import { useState } from "react";
import { z } from "zod";
import { Button, Input } from "@/components/ui";

// Client-side form contract (distinct from the API-mirror schemas in
// src/api/schemas/). V1 gates on a present file + non-empty title; the
// type/size guards (V2) extend this with `.refine`.
const uploadFormSchema = z.object({
  file: z.instanceof(File),
  title: z.string().trim().min(1),
});

const stripPdf = (name: string) => name.replace(/\.pdf$/i, "");

export function BookUploadForm({
  onSubmit,
}: {
  onSubmit: (file: File, title: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");

  const onFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null;
    setFile(f);
    if (f) setTitle(stripPdf(f.name));
  };

  const parsed = uploadFormSchema.safeParse({ file, title });

  return (
    <form
      className="mt-5 flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (parsed.success) onSubmit(parsed.data.file, parsed.data.title);
      }}
    >
      <label className="flex flex-col gap-1.5">
        <span className="font-sans text-sm text-ink-muted">PDF file</span>
        <input
          type="file"
          accept="application/pdf"
          onChange={onFilePick}
          className="font-sans text-sm text-ink"
        />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="font-sans text-sm text-ink-muted">Title</span>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Book title"
        />
      </label>

      <div className="mt-2 flex justify-end">
        <Button type="submit" disabled={!parsed.success}>
          Upload
        </Button>
      </div>
    </form>
  );
}
