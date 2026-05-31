import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  model: string
  setModel: (model: string) => void
}

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      model: 'deepseek-v4-flash',
      setModel: (model) => set({ model }),
    }),
    { name: 'prism-settings' }
  )
)
