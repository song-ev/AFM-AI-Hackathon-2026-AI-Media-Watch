import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 p-6">
      <h1 className="text-2xl font-semibold">404 — страница не найдена</h1>
      <Link href="/login" className="text-sm text-muted-foreground underline">
        На страницу входа
      </Link>
    </main>
  );
}
