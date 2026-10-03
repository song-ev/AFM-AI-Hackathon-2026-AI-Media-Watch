// OPTIONAL bank web UI.
//
// Banks integrate via the REST API only (see backend C6: POST /api/bank/v1/
// risk-check/ with an API key). This route group exists as a placeholder in
// case a thin web UI is ever wanted for bank staff; it can be deleted if banks
// stay API-only. It deliberately does NOT reuse the analyst dashboard shell.
export default function BankLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <div className="min-h-screen bg-background p-8">{children}</div>;
}
