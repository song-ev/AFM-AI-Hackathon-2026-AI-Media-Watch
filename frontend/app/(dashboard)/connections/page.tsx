"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConnectionGraph } from "@/components/connections/ConnectionGraph";
import {
  useConnectionSearchQuery,
  type ConnectionFilters,
  type SearchResult,
} from "@/lib/api/connections";

const FILTER_LABEL: Record<string, string> = {
  account: "Аккаунт",
  promo_code: "Промокод",
  telegram_link: "Telegram",
};

function ConnectionsInner() {
  const searchParams = useSearchParams();
  const initialAccount = searchParams.get("account") ?? undefined;

  const [filters, setFilters] = useState<ConnectionFilters>(
    initialAccount ? { account: initialAccount } : {}
  );

  const [query, setQuery] = useState(initialAccount ?? "");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  const { data: results } = useConnectionSearchQuery(debounced);

  const select = (r: SearchResult) => {
    setFilters({ [r.type]: r.value });
    setQuery(r.label);
    setOpen(false);
  };

  const reset = () => {
    setFilters({});
    setQuery("");
    setOpen(false);
  };

  const activeKey = Object.keys(filters)[0];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Граф связей</h1>
        <p className="text-sm text-muted-foreground">
          Поиск общих личностей, промокодов и Telegram-ссылок между аккаунтами.
        </p>
      </div>

      <div className="flex flex-wrap items-start gap-2">
        <div className="relative w-full max-w-md">
          <Input
            placeholder="Поиск по аккаунту / промокоду / Telegram…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onFocus={() => setOpen(true)}
          />
          {open && results && results.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border bg-popover shadow-md">
              {results.map((r) => (
                <li key={`${r.type}:${r.value}`}>
                  <button
                    className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                    onClick={() => select(r)}
                  >
                    <span className="truncate">{r.label}</span>
                    <span className="ml-2 shrink-0 text-xs text-muted-foreground">
                      {FILTER_LABEL[r.type]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Button variant="outline" onClick={reset}>
          Сбросить фильтр / показать общий граф
        </Button>
      </div>

      {activeKey && (
        <p className="text-sm text-muted-foreground">
          Фильтр: {FILTER_LABEL[activeKey]} ={" "}
          <span className="font-medium">
            {(filters as Record<string, string>)[activeKey]}
          </span>
        </p>
      )}

      <ConnectionGraph filters={filters} />
    </div>
  );
}

export default function ConnectionsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-10 text-sm text-muted-foreground">Загрузка…</div>
      }
    >
      <ConnectionsInner />
    </Suspense>
  );
}
