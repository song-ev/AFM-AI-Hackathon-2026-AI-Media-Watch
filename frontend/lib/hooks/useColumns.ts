"use client";

import { useEffect, useState } from "react";

/**
 * Responsive column count for the virtualized incident grid. Mirrors the
 * Tailwind breakpoints the queue used before virtualization
 * (`sm:grid-cols-2 lg:grid-cols-3`) so the layout is unchanged visually.
 */
export function useColumns(): number {
  const [cols, setCols] = useState(3);

  useEffect(() => {
    const compute = () => {
      const w = window.innerWidth;
      setCols(w >= 1024 ? 3 : w >= 640 ? 2 : 1);
    };
    compute();
    window.addEventListener("resize", compute);
    return () => window.removeEventListener("resize", compute);
  }, []);

  return cols;
}
