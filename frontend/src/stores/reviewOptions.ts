import { create } from 'zustand'

export type Perspective = 'default' | 'security' | 'performance' | 'maintainability'

export const PERSPECTIVE_LABELS: Record<Perspective, string> = {
  default: '默认',
  security: '安全工程师',
  performance: '性能工程师',
  maintainability: '可维护性',
}

export interface ReviewOptions {
  includeStyle: boolean
  contextLines: number
  perspective: Perspective
}

interface ReviewOptionsStore {
  options: ReviewOptions
  setIncludeStyle: (value: boolean) => void
  setContextLines: (value: number) => void
  setPerspective: (value: Perspective) => void
  reset: () => void
}

const DEFAULT_OPTIONS: ReviewOptions = {
  includeStyle: false,
  contextLines: 3,
  perspective: 'default',
}

export const useReviewOptions = create<ReviewOptionsStore>((set) => ({
  options: { ...DEFAULT_OPTIONS },
  setIncludeStyle: (includeStyle) => set((s) => ({ options: { ...s.options, includeStyle } })),
  setContextLines: (contextLines) => set((s) => ({ options: { ...s.options, contextLines } })),
  setPerspective: (perspective) => set((s) => ({ options: { ...s.options, perspective } })),
  reset: () => set({ options: { ...DEFAULT_OPTIONS } }),
}))
