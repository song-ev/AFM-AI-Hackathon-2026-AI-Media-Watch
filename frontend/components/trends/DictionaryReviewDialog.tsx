"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  useDictionaryReviewMutation,
  useDictionaryRollbackMutation,
  useDictionaryVersionsQuery,
  usePendingDictionaryQuery,
  type DictionaryVersion,
} from "@/lib/api/dashboard";
import { useAuthStore } from "@/lib/stores/authStore";

function PendingList() {
  const { data, isLoading } = usePendingDictionaryQuery();
  const review = useDictionaryReviewMutation();

  const act = (id: number, decision: "approve" | "reject") =>
    review.mutate(
      { id, decision },
      {
        onSuccess: () => toast.success(decision === "approve" ? "Одобрено" : "Отклонено"),
        onError: () => toast.error("Ошибка"),
      }
    );

  if (isLoading) return <p className="text-sm text-muted-foreground">Загрузка…</p>;
  if (!data || data.length === 0)
    return <p className="text-sm text-muted-foreground">Нет записей на review.</p>;

  return (
    <ul className="space-y-2">
      {data.map((e) => (
        <li
          key={e.id}
          className="flex items-center justify-between gap-2 rounded-md border p-2"
        >
          <div className="text-sm">
            <span className="font-medium">{e.term}</span>{" "}
            <span className="text-muted-foreground">
              · {e.category}
              {e.added_automatically ? " · авто" : ""} · подтв. {e.confirmation_count}
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              className="bg-green-600 hover:bg-green-700 text-white"
              disabled={review.isPending}
              onClick={() => act(e.id, "approve")}
            >
              Одобрить
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={review.isPending}
              onClick={() => act(e.id, "reject")}
            >
              Отклонить
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function VersionRow({ version }: { version: DictionaryVersion }) {
  const [open, setOpen] = useState(false);
  const role = useAuthStore((s) => s.user?.role);
  const rollback = useDictionaryRollbackMutation();

  return (
    <li className="rounded-md border p-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span>
          v{version.id} · {version.term_count} терминов{" "}
          <span className="text-muted-foreground">
            · {new Date(version.created_at).toLocaleString("ru-RU")}
          </span>
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setOpen((v) => !v)}>
            Снапшот
          </Button>
          {role === "analyst" && (
            <Button
              size="sm"
              variant="outline"
              disabled={rollback.isPending}
              onClick={() =>
                rollback.mutate(version.id, {
                  onSuccess: () => toast.success("Откат выполнен"),
                  onError: () => toast.error("Не удалось откатиться"),
                })
              }
            >
              Откатиться
            </Button>
          )}
        </div>
      </div>
      {version.note && <p className="mt-1 text-muted-foreground">{version.note}</p>}
      {open && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
          {JSON.stringify(version.snapshot, null, 2)}
        </pre>
      )}
    </li>
  );
}

function VersionsList() {
  const { data, isLoading } = useDictionaryVersionsQuery();
  if (isLoading) return <p className="text-sm text-muted-foreground">Загрузка…</p>;
  if (!data || data.length === 0)
    return <p className="text-sm text-muted-foreground">Версий пока нет.</p>;
  return (
    <ul className="space-y-2">
      {data.map((v) => (
        <VersionRow key={v.id} version={v} />
      ))}
    </ul>
  );
}

export function DictionaryReviewDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">Ревью словаря кодовых слов</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] w-[92vw] max-w-2xl overflow-auto">
        <DialogHeader>
          <DialogTitle>Словарь кодовых слов</DialogTitle>
        </DialogHeader>
        <div className="space-y-5">
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">На review</h3>
            <PendingList />
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-semibold">История версий</h3>
            <VersionsList />
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}
