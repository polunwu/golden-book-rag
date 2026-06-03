export function ErrorState({ detail }: { detail: string }) {
  return (
    <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      {detail}
    </p>
  );
}
