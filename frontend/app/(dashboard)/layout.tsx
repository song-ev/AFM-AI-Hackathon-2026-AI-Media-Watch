import { AuthGuard } from "@/components/auth-guard";
import { DashboardNav } from "@/components/dashboard-nav";

// Shell for the internal analyst / AFM UI, protected by a client-side guard
// (redirects unauthenticated users to /login and enforces per-section roles).
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="flex min-h-screen">
        <DashboardNav />
        <main className="flex-1 p-8">{children}</main>
      </div>
    </AuthGuard>
  );
}
