"use client";

import { useForm } from "react-hook-form";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import { z } from "zod";
import { MAX_UPLOAD_MB } from "@/lib/config";
import { Button, ErrorState, FieldError, Input } from "@/components/ui";

const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

// Client-side form contract (distinct from the API-mirror schemas in
// src/api/schemas/). The file guards reject before the POST; accept= only
// filters the OS picker, so type/size validation here is the real gate.
const uploadFormSchema = z.object({
  file: z
    .instanceof(File, { message: "Please choose a PDF file." })
    .refine((f) => f.type === "application/pdf", "Please choose a PDF file.")
    .refine(
      (f) => f.size <= MAX_BYTES,
      `That file is too large (max ${MAX_UPLOAD_MB} MB).`,
    ),
  title: z.string().trim().min(1, "Title is required."),
});

type UploadFormValues = z.infer<typeof uploadFormSchema>;

const stripPdf = (name: string) => name.replace(/\.pdf$/i, "");

export function BookUploadForm({
  onSubmit,
  pending,
  serverError,
  onDirty,
}: {
  onSubmit: (file: File, title: string) => void;
  pending: boolean;
  serverError: string | null;
  onDirty: () => void;
}) {
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors, isValid },
  } = useForm<UploadFormValues>({
    resolver: standardSchemaResolver(uploadFormSchema),
    mode: "onChange",
  });

  // `file` is value-typed (a File, not the input's FileList), so set it
  // imperatively rather than via register's ref; shouldValidate runs the
  // resolver and the title autofills from the filename.
  const onFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    onDirty();
    const f = e.target.files?.[0];
    setValue("file", f as File, { shouldValidate: true });
    if (f) setValue("title", stripPdf(f.name), { shouldValidate: true });
  };

  return (
    <form
      className="mt-5 flex flex-col gap-4"
      onSubmit={handleSubmit((v) => onSubmit(v.file, v.title))}
    >
      <label className="flex flex-col gap-1.5">
        <span className="font-sans text-sm text-ink-muted">PDF file</span>
        <input
          type="file"
          accept="application/pdf"
          onChange={onFilePick}
          aria-invalid={errors.file ? true : undefined}
          className="font-sans text-sm text-ink"
        />
        <FieldError message={errors.file?.message} />
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="font-sans text-sm text-ink-muted">Title</span>
        <Input
          placeholder="Book title"
          aria-invalid={errors.title ? true : undefined}
          {...register("title", { onChange: () => onDirty() })}
        />
        <FieldError message={errors.title?.message} />
      </label>

      {/* Server error is form-level (not field-scoped); onDirty resets the
          mutation on edit so it never lingers over changed inputs. */}
      {serverError && <ErrorState detail={serverError} />}

      <div className="mt-2 flex justify-end">
        <Button type="submit" disabled={!isValid || pending}>
          {pending ? "Uploading…" : "Upload"}
        </Button>
      </div>
    </form>
  );
}
