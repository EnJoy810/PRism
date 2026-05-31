import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SettingsStore {
  model: string
  baseUrl: string
  apiKey: string
  setModel: (v: string) => void
  setBaseUrl: (v: string) => void
  setApiKey: (v: string) => void
}

export const useSettings = create<SettingsStore>()(
  persist(
    (set) => ({
      model: 'deepseek-v4-flash',
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: '',
      setModel: (model) => set({ model }),
      setBaseUrl: (baseUrl) => set({ baseUrl }),
      setApiKey: (apiKey) => set({ apiKey }),
    }),
    { name: 'prism-settings' }
  )
)
