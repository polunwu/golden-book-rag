// Placeholder route — registered so the shell + routing are real.
// Server component; params is a Promise in the App Router.
export default async function BookDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <p className="font-sans text-sm text-ink-muted">
      Book {id} (coming soon).
    </p>
  );
}
