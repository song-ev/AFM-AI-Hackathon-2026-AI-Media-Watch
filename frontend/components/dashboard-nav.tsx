"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { navItemsForRole } from "@/lib/navigation";
import { logout as logoutRequest } from "@/lib/api/auth";
import { useAuthStore } from "@/lib/stores/authStore";

/**
 * Role-aware sidebar navigation. Items shown depend on the current user's role
 * from the auth store; includes a logout action.
 */
export function DashboardNav() {
  const pathname = usePathname();
  const router = useRouter();
  const role = useAuthStore((s) => s.user?.role);
  const username = useAuthStore((s) => s.user?.username);
  const items = navItemsForRole(role);

  const handleLogout = async () => {
    const { refreshToken, clearAuth } = useAuthStore.getState();
    await logoutRequest(refreshToken); // blacklist on the backend (best effort)
    clearAuth();
    router.replace("/login");
  };

  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-card p-4">
      <div className="mb-6 px-2">
        <p className="text-lg font-semibold">AI Media Watch</p>
        <p className="text-xs text-muted-foreground">
          {username ? `${username} · ${role}` : "не выполнен вход"}
        </p>
      </div>

      <nav className="flex flex-col gap-1">
        {items.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {item.label}
            </Link>
          );
        })}
        {items.length === 0 && (
          <p className="px-3 py-2 text-sm text-muted-foreground">
            Нет доступных разделов.
          </p>
        )}
      </nav>

      <div className="mt-auto">
        <Button
          type="button"
          variant="outline"
          className="w-full"
          onClick={handleLogout}
        >
          Выход
        </Button>
      </div>
    </aside>
  );
}
