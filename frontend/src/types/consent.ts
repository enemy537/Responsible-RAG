import { ProfileMode } from './profile';

export interface ConsentRecord {
  id: string;
  userId: string;
  profileMode: ProfileMode;
  researchDataConsent: boolean; // anonymized conversation data for research
  chatHistoryConsent: boolean; // store conversations so they can be revisited
  consentedAt: string;
  updatedAt: string;
}

export interface ConsentState {
  profileMode: ProfileMode | null;
  researchDataConsent: boolean;
  chatHistoryConsent: boolean;
  hasConsented: boolean;
}
