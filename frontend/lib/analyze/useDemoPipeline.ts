"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { VideoStatus } from "@/lib/api/ingestion";

/**
 * Offline demo of the analysis pipeline.
 *
 * Hackathon networks routinely block YouTube/TikTok/Instagram, so a real
 * download can fail mid-presentation. This hook replays a scripted, realistic
 * `VideoStatus` progression on a timer with no backend, Celery or network —
 * the exact same shape the live run produces, so the UI is identical.
 */

const DEMO_VIDEO_ID = 9001;

// Each frame is the full status at that point in time; the hook advances one
// frame per tick so the console/cards/graph animate just like a real run.
const SCRIPT: Omit<VideoStatus, "processing_time_ms">[] = [
  {
    video_id: DEMO_VIDEO_ID,
    download_status: "downloading",
    screening_status: null,
    stage2_status: null,
    overall: "downloading",
    incident_id: null,
    risk_score: null,
    summary: { frames_extracted: 0, ocr_keywords: [], audio_triggered: false, signals: [] },
  },
  {
    video_id: DEMO_VIDEO_ID,
    download_status: "downloaded",
    screening_status: "running",
    stage2_status: null,
    overall: "screening",
    incident_id: null,
    risk_score: null,
    summary: { frames_extracted: 18, ocr_keywords: [], audio_triggered: false, signals: [] },
  },
  {
    video_id: DEMO_VIDEO_ID,
    download_status: "downloaded",
    screening_status: "triggered",
    stage2_status: "running",
    overall: "deep_analysis",
    incident_id: null,
    risk_score: null,
    summary: {
      frames_extracted: 48,
      ocr_keywords: ["casino", "промокод", "x100"],
      audio_triggered: true,
      signals: [],
    },
  },
  {
    video_id: DEMO_VIDEO_ID,
    download_status: "downloaded",
    screening_status: "triggered",
    stage2_status: "running",
    overall: "deep_analysis",
    incident_id: null,
    risk_score: null,
    summary: {
      frames_extracted: 48,
      ocr_keywords: ["casino", "промокод", "x100"],
      audio_triggered: true,
      signals: [
        { module: "Транскрипт (NLP)", is_triggered: true, confidence: 0.92 },
        { module: "Фейковый скриншот банка", is_triggered: true, confidence: 0.81 },
      ],
    },
  },
  {
    video_id: DEMO_VIDEO_ID,
    download_status: "downloaded",
    screening_status: "triggered",
    stage2_status: "done",
    overall: "completed",
    incident_id: null,
    risk_score: 87,
    geo: {
      lat: 43.2389,
      lon: 76.8897,
      label: "Алматы",
      region: "Алматы",
      country: "Казахстан",
      source: "ai_inference",
      confidence: 0.72,
      reasoning: "Упоминание Kaspi и города в речи; код телефона +7 707.",
    },
    categories: {
      payment: {
        is_triggered: true,
        confidence: 0.8,
        error: "",
        detail: {
          identifiers: {
            phones: ["+77071234567"],
            cards: [],
            ibans: [],
            crypto: [],
            cues: ["kaspi", "перевод"],
          },
          primary_identifier: "+77071234567",
          count: 1,
        },
      },
      brand_link: {
        is_triggered: true,
        confidence: 0.9,
        error: "",
        detail: {
          brands: ["1xbet", "aviator"],
          suspicious_links: [
            { domain: "1xbet-mirror.win", score: 1.0, reasons: ["бренд", ".win"] },
          ],
          qr_codes: [{ timestamp_sec: 12.4 }],
        },
      },
      audio_forensics: {
        is_triggered: true,
        confidence: 0.83,
        error: "",
        detail: {
          pressure_score: 0.78,
          synthetic_voice_indicator: 0.71,
          languages: ["ru", "kk"],
          flags: [
            "Высокое давление в подаче (громко/быстро/без пауз)",
            "Возможен синтезированный/клонированный голос (монотонность)",
          ],
        },
      },
    },
    summary: {
      frames_extracted: 48,
      ocr_keywords: ["casino", "промокод", "x100"],
      audio_triggered: true,
      signals: [
        { module: "Транскрипт (NLP)", is_triggered: true, confidence: 0.92 },
        { module: "Фейковый скриншот банка", is_triggered: true, confidence: 0.81 },
        { module: "Сопоставление голоса", is_triggered: true, confidence: 0.74 },
        { module: "Сопоставление лица", is_triggered: false, confidence: 0.12 },
      ],
    },
  },
];

const TICK_MS = 1400;

export interface DemoPipeline {
  status: VideoStatus | null;
  running: boolean;
  done: boolean;
  start: () => void;
  reset: () => void;
}

export function useDemoPipeline(): DemoPipeline {
  const [step, setStep] = useState(-1); // -1 = not started
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const start = useCallback(() => {
    stop();
    setStep(0);
    timer.current = setInterval(() => {
      setStep((s) => {
        if (s >= SCRIPT.length - 1) {
          stop();
          return s;
        }
        return s + 1;
      });
    }, TICK_MS);
  }, [stop]);

  const reset = useCallback(() => {
    stop();
    setStep(-1);
  }, [stop]);

  useEffect(() => stop, [stop]);

  const frame = step >= 0 ? SCRIPT[Math.min(step, SCRIPT.length - 1)] : null;
  const status: VideoStatus | null = frame
    ? { ...frame, processing_time_ms: step * TICK_MS }
    : null;

  return {
    status,
    running: step >= 0 && step < SCRIPT.length - 1,
    done: step >= SCRIPT.length - 1,
    start,
    reset,
  };
}
