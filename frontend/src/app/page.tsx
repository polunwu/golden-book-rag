"use client";

import { useQuery } from "@tanstack/react-query";
import { listBooks } from "../api/books";
import { Loading } from "../components/Loading";
import { ErrorState } from "../components/ErrorState";

// A7 — the connectivity smoke. Proves env → client → generated-zod → render
// end-to-end against the live backend. (No Library grid — that's Step 9.)
export default function Home() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["books"],
    queryFn: listBooks,
  });

  if (isLoading) return <Loading label="Connecting to backend…" />;
  if (error) return <ErrorState detail={(error as Error).message} />;

  const n = data!.length;
  return (
    <div className="flex items-center gap-2">
      <span className="inline-block h-2.5 w-2.5 rounded-full bg-green-500" />
      <span>
        Connected · {n} book{n === 1 ? "" : "s"}
      </span>
    </div>
  );
}
