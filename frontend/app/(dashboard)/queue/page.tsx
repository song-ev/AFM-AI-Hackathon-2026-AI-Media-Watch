"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { Loader2 } from "lucide-react";

import { Input } from "@/components/ui/input";
import { IncidentCard, IncidentCardSkeleton } from "@/components/incident-card";
import { QueueFilters } from "@/components/queue-filters";
import { QueueStats } from "@/components/queue-stats";
import {
  useInfiniteIncidentsQuery,
  type IncidentFilters,
} from "@/lib/api/incidents";
import { useColumns } from "@/lib/hooks/useColumns";
import { useQueueFiltersStore } from "@/lib/stores/queueFiltersStore";

const ROW_GAP = 16; // matches gap-4

export default function QueuePage() {
  const store = useQueueFiltersStore();
  const filters: IncidentFilters = useMemo(
    () => ({
      platform: store.platform,
      status: store.status,
      riskMin: store.riskMin,
      riskMax: store.riskMax,
      dateFrom: store.dateFrom,
      dateTo: store.dateTo,
      search: store.search,
    }),
    [
      store.platform,
      store.status,
      store.riskMin,
      store.riskMax,
      store.dateFrom,
      store.dateTo,
      store.search,
    ]
  );

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteIncidentsQuery(filters);

  // Debounced search: type into local state, push to the store after 400ms.
  const [searchInput, setSearchInput] = useState(store.search);
  const [previousSearch, setPreviousSearch] = useState(store.search);
  if (previousSearch !== store.search) {
    setPreviousSearch(store.search);
    setSearchInput(store.search);
  }
  useEffect(() => {
    const t = setTimeout(() => {
      if (searchInput !== store.search) store.setSearch(searchInput);
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  const items = useMemo(
    () => data?.pages.flatMap((p) => p.results) ?? [],
    [data]
  );
  const total = data?.pages[0]?.count ?? 0;

  // --- Virtualization (window scroll, dynamic row heights) -----------------
  const columns = useColumns();
  const rowCount = Math.ceil(items.length / columns);
  const listRef = useRef<HTMLDivElement>(null);
  const [listOffset, setListOffset] = useState(0);

  useLayoutEffect(() => {
    if (listRef.current) setListOffset(listRef.current.offsetTop);
  }, [items.length, columns]);

  const virtualizer = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => 360,
    overscan: 4,
    scrollMargin: listOffset,
    gap: ROW_GAP,
  });
  const virtualRows = virtualizer.getVirtualItems();

  // Fetch the next page when the last virtual row is reached.
  useEffect(() => {
    const last = virtualRows[virtualRows.length - 1];
    if (!last) return;
    if (last.index >= rowCount - 1 && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [virtualRows, rowCount, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Очередь аналитика</h1>
        <p className="text-sm text-muted-foreground">
          Инциденты отсортированы по приоритету. Обновляется автоматически.
        </p>
      </div>

      <QueueStats />

      <Input
        placeholder="Поиск по аккаунту или подписи…"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
      />

      <QueueFilters />

      {isError ? (
        <div className="rounded-lg border bg-card p-10 text-center text-sm text-destructive">
          Не удалось загрузить очередь. Повторите попытку.
        </div>
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <IncidentCardSkeleton key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border bg-card p-10 text-center text-muted-foreground">
          Очередь пуста
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>
              {total.toLocaleString("ru-RU")} инцидентов · показано{" "}
              {items.length}
            </span>
          </div>

          {/* Virtualized rows of `columns` cards each */}
          <div ref={listRef}>
            <div
              style={{ height: virtualizer.getTotalSize(), position: "relative" }}
            >
              {virtualRows.map((row) => {
                const start = row.index * columns;
                const rowItems = items.slice(start, start + columns);
                return (
                  <div
                    key={row.key}
                    data-index={row.index}
                    ref={virtualizer.measureElement}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${row.start - listOffset}px)`,
                    }}
                  >
                    <div
                      className="grid gap-4"
                      style={{
                        gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
                      }}
                    >
                      {rowItems.map((incident) => (
                        <IncidentCard key={incident.id} incident={incident} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {isFetchingNextPage && (
            <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Загрузка ещё…
            </div>
          )}
          {!hasNextPage && (
            <p className="py-4 text-center text-xs text-muted-foreground">
              Конец списка
            </p>
          )}
        </>
      )}
    </div>
  );
}
