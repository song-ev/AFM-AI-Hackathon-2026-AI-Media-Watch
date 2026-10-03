import { create } from "zustand";

export const RISK_MIN = 0;
export const RISK_MAX = 100;

interface QueueFiltersState {
  platform?: string;
  status?: string;
  riskMin: number;
  riskMax: number;
  dateFrom?: string;
  dateTo?: string;
  search: string;
  page: number;

  setPlatform: (v?: string) => void;
  setStatus: (v?: string) => void;
  setRiskRange: (min: number, max: number) => void;
  setDateFrom: (v?: string) => void;
  setDateTo: (v?: string) => void;
  setSearch: (v: string) => void;
  setPage: (page: number) => void;
  reset: () => void;
}

const INITIAL = {
  platform: undefined,
  status: undefined,
  riskMin: RISK_MIN,
  riskMax: RISK_MAX,
  dateFrom: undefined,
  dateTo: undefined,
  search: "",
  page: 1,
};

/**
 * Queue filters live in a store (not local state) so they survive navigating
 * to an incident card and back. Any filter change resets the page to 1.
 */
export const useQueueFiltersStore = create<QueueFiltersState>((set) => ({
  ...INITIAL,
  setPlatform: (v) => set({ platform: v, page: 1 }),
  setStatus: (v) => set({ status: v, page: 1 }),
  setRiskRange: (min, max) => set({ riskMin: min, riskMax: max, page: 1 }),
  setDateFrom: (v) => set({ dateFrom: v, page: 1 }),
  setDateTo: (v) => set({ dateTo: v, page: 1 }),
  setSearch: (v) => set({ search: v, page: 1 }),
  setPage: (page) => set({ page }),
  reset: () => set({ ...INITIAL }),
}));
