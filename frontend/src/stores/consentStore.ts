import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { ProfileMode } from '@/types/profile';

interface ConsentStore {
  profileMode: ProfileMode | null;
  researchDataConsent: boolean;
  chatHistoryConsent: boolean;
  hasConsented: boolean;
  setProfileMode: (mode: ProfileMode) => void;
  setResearchDataConsent: (consent: boolean) => void;
  setChatHistoryConsent: (consent: boolean) => void;
  setHasConsented: (consented: boolean) => void;
  reset: () => void;
}

// Defaults mirror the backend (\`chat_history_default_consent\`).
export const useConsentStore = create<ConsentStore>()(
  persist(
    (set) => ({
      profileMode: null,
      researchDataConsent: false,
      chatHistoryConsent: true,
      hasConsented: false,
      setProfileMode: (mode) => set({ profileMode: mode }),
      setResearchDataConsent: (consent) => set({ researchDataConsent: consent }),
      setChatHistoryConsent: (consent) => set({ chatHistoryConsent: consent }),
      setHasConsented: (consented) => set({ hasConsented: consented }),
      reset: () =>
        set({
          profileMode: null,
          researchDataConsent: false,
          chatHistoryConsent: true,
          hasConsented: false,
        }),
    }),
    { name: 'consent-store' }
  )
);
