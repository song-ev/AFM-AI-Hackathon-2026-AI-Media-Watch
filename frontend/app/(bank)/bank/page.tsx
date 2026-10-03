// Landing for bank_admin users. Banks integrate via the REST API (C6), not
// this UI — so we show a message rather than a dashboard.
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function BankHomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Доступ через REST API</CardTitle>
          <CardDescription>Банковская интеграция</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Для банков предусмотрен только программный доступ. Используйте REST API
          (<code>POST /api/bank/v1/risk-check/</code> с заголовком{" "}
          <code>Authorization: ApiKey &lt;ключ&gt;</code>) — см. документацию.
          Веб-интерфейс для этой роли не предусмотрен.
        </CardContent>
      </Card>
    </main>
  );
}
