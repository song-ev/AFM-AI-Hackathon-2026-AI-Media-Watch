"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { requiredRolesForPath } from "@/lib/navigation";
import { useAuthStore } from "@/lib/stores/authStore";

function FullScreenLoader({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-muted-foreground">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent" />
        <p className="text-sm">{label}</p>
      </div>
    </div>
  );
}

/**
 * Client-side route guard for the dashboard. (Client, not middleware, because
 * tokens live in memory — middleware on the server can't read them.)
 *
 * - not ready          -> loading
 * - not authenticated  -> /login
 * - bank_admin         -> /bank (no dashboard access)
 * - role not permitted -> toast + /queue
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const authReady = useAuthStore((s) => s.authReady);
  const user = useAuthStore((s) => s.user);

  const allowed = user ? requiredRolesForPath(pathname).includes(user.role) : false;
  const isBank = user?.role === "bank_admin";

  useEffect(() => {
    if (!authReady) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (isBank) {
      router.replace("/bank");
      return;
    }
    if (!allowed) {
      toast.error("Недостаточно прав для этого раздела");
      router.replace("/queue");
    }
  }, [authReady, user, isBank, allowed, router]);

  if (!authReady) return <FullScreenLoader label="Проверка сессии…" />;
  if (!user || isBank || !allowed) {
    return <FullScreenLoader label="Перенаправление…" />;
  }
  return <>{children}</>;
}
