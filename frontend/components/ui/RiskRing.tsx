"use client";

import { useEffect, useState } from "react";

import { riskLevel } from "@/lib/utils/riskColor";
import { cn } from "@/lib/utils";

const STROKE: Record<string, string> = {
  low: "#10b981",
  medium: "#f59e0b",
  high: "#ef4444",
};

interface RiskRingProps {
  /** Risk score 0-100. */
  score: number;
  size?: number;
  stroke?: number;
  /** Animate the arc sweeping in (the "wow" reveal). */
  animate?: boolean;
  /** Show the number in the middle. */
  showValue?: boolean;
  label?: string;
  className?: string;
}

/**
 * Animated radial risk gauge — the shared "wow" element across the app
 * (parsing cards, live console, incident verdict-hero). The arc sweeps from 0
 * to the score on mount and the colour follows the risk scale.
 */
export function RiskRing({
  score,
  size = 64,
  stroke = 6,
  animate = true,
  showValue = true,
  label,
  className,
}: RiskRingProps) {
  const clamped = Math.max(0, Math.min(100, score || 0));
  const [shown, setShown] = useState(animate ? 0 : clamped);

  useEffect(() => {
    if (!animate) {
      return;
    }
    let raf = 0;
    const start = performance.now();
    const dur = 900;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(clamped * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [clamped, animate]);

  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const displayed = animate ? shown : clamped;
  const offset = circ * (1 - displayed / 100);
  const color = STROKE[riskLevel(clamped)];

  return (
    <div
      className={cn("relative inline-flex items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-muted/40"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          style={{
            transition: "stroke 0.4s ease",
            filter: clamped >= 60 ? `drop-shadow(0 0 4px ${color}99)` : undefined,
          }}
        />
      </svg>
      {showValue && (
        <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
          <span
            className="font-semibold tabular-nums"
            style={{ color, fontSize: size * 0.28 }}
          >
            {Math.round(displayed)}
          </span>
          {label && (
            <span className="text-muted-foreground" style={{ fontSize: size * 0.13 }}>
              {label}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
