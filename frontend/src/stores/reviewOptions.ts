import { create } from 'zustand'

export interface ReviewOptions {
  includeStyle: boolean
  contextLines: number
}

interface ReviewOptionsStore {
  options: ReviewOptions
  setIncludeStyle: (value: boolean) => void
  setContextLines: (value: number) => void
  reset: () => void
}

const DEFAULT_OPTIONS: ReviewOptions = {
  includeStyle: false,
  contextLines: 3,
}

export const useReviewOptions = create<ReviewOptionsStore>((set) => ({
  options: { ...DEFAULT_OPTIONS },
  setIncludeStyle: (includeStyle) => set((s) => ({ options: { ...s.options, includeStyle } })),
  setContextLines: (contextLines) => set((s) => ({ options: { ...s.options, contextLines } })),
  reset: () => set({ options: { ...DEFAULT_OPTIONS } }),
}))
