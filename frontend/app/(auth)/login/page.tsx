"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { isAxiosError } from "axios";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { login as loginRequest, fetchMe } from "@/lib/api/auth";
import { landingPathForRole } from "@/lib/navigation";
import { useAuthStore } from "@/lib/stores/authStore";

export default function LoginPage() {
  const router = useRouter();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // No <form> element — submit via a React handler (best practice here).
  const handleSubmit = async () => {
    if (loading) return;
    setError(null);
    if (!username || !password) {
      setError("Введите логин и пароль.");
      return;
    }
    setLoading(true);
    try {
      const { access, refresh } = await loginRequest(username, password);
      // Set tokens first so the /me request is authenticated.
      setTokens(access, refresh);
      const me = await fetchMe();
      setUser(me);
      router.replace(landingPathForRole(me.role));
    } catch (err) {
      // Do not reveal which field was wrong — standard security practice.
      if (isAxiosError(err) && err.response?.status === 401) {
        setError("Неверный логин или пароль.");
      } else {
        setError("Не удалось войти. Попробуйте позже.");
      }
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSubmit();
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>AI Media Watch</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="username" className="text-sm font-medium">
              Логин
            </label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium">
              Пароль
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
          </div>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <Button
            type="button"
            className="w-full"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? "Вход…" : "Войти"}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
