"use client";

import { Toaster as SonnerToaster } from "sonner";

/** App-wide toast surface (Sonner). Rendered once in Providers. */
export function Toaster() {
  return <SonnerToaster richColors position="top-right" />;
}
