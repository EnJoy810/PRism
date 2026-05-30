import { create } from 'zustand'

export interface ReviewOptions {
  // 已简化，所有选项已移除
}

interface ReviewOptionsStore {
  options: ReviewOptions
  reset: () => void
}

export const useReviewOptions = create<ReviewOptionsStore>((set) => ({
  options: {},
  reset: () => set({ options: {} }),
}))
