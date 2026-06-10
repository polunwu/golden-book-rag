"use client";

import { useState } from "react";
import { Upload } from "lucide-react";
import { useForm, useWatch } from "react-hook-form";
import { standardSchemaResolver } from "@hookform/resolvers/standard-schema";
import { z } from "zod";
import { MAX_UPLOAD_MB } from "@/lib/config";
import { formatBytes } from "@/lib/format";
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

// Inline spinner for the in-flight submit; the global prefers-reduced-motion
// rule neutralizes the spin, leaving a static ring.
function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}

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
    control,
    formState: { errors, isValid },
  } = useForm<UploadFormValues>({
    resolver: standardSchemaResolver(uploadFormSchema),
    mode: "onChange",
  });

  const [dragActive, setDragActive] = useState(false);

  // `file` is value-typed (a File, not the input's FileList), so set it
  // imperatively rather than via register's ref; shouldValidate runs the
  // resolver and the title autofills from the filename. Shared by the picker,
  // drop, and Replace paths.
  const handleFile = (f: File | undefined) => {
    onDirty();
    setValue("file", f as File, { shouldValidate: true });
    if (f) setValue("title", stripPdf(f.name), { shouldValidate: true });
  };

  const file = useWatch({ control, name: "file" });
  const fileError = errors.file;

  const targetBorder = fileError
    ? "border-status-failed border-solid"
    : dragActive
      ? "border-status-processing border-solid bg-status-processing/5"
      : file
        ? "border-rule border-solid"
        : "border-rule border-dashed";

  return (
    <form
      className="mt-5 flex flex-col gap-4"
      onSubmit={handleSubmit((v) => onSubmit(v.file, v.title))}
    >
      <div className="flex flex-col gap-1.5">
        <span className="font-sans text-sm text-ink-muted">PDF file</span>
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            handleFile(e.dataTransfer.files?.[0]);
          }}
          className={`relative flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 px-4 py-5 text-center transition-colors focus-within:ring-2 focus-within:ring-status-processing focus-within:ring-offset-1 focus-within:ring-offset-paper ${targetBorder}`}
        >
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => handleFile(e.target.files?.[0])}
            aria-invalid={fileError ? true : undefined}
            className="sr-only"
          />
          {file ? (
            <>
              <span
                title={file.name}
                className="max-w-full truncate font-sans text-sm font-medium text-ink"
              >
                {file.name}
              </span>
              <span className="font-sans text-xs text-ink-muted">
                {formatBytes(file.size)} · Replace
              </span>
            </>
          ) : (
            <>
              <Upload aria-hidden className="h-6 w-6 text-ink-muted" />
              <span className="font-sans text-sm font-medium text-ink">
                Choose a PDF
              </span>
              <span className="font-sans text-xs text-ink-muted">
                or drag it here · up to {MAX_UPLOAD_MB} MB
              </span>
            </>
          )}
        </label>
        <FieldError message={fileError?.message} />
      </div>

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
        <Button
          type="submit"
          disabled={!isValid || pending}
          className="flex items-center gap-2"
        >
          {pending && <Spinner />}
          {pending ? "Uploading…" : "Upload"}
        </Button>
      </div>
    </form>
  );
}
