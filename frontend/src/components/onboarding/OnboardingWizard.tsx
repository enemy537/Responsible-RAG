'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useConsentStore } from '@/stores/consentStore';
import { useProfileStore } from '@/stores/profileStore';
import { useAuthStore } from '@/hooks/useAuth';
import { ConsentStep } from './ConsentStep';
import { ProfileModeSelector } from './ProfileModeSelector';
import { ProfileProcessingStep } from './ProfileProcessingStep';
import { ProfileReviewStep } from './ProfileReviewStep';
import type { GenerateProfileResponseDTO } from '@/lib/api';

type WizardStep = 'welcome' | 'consent' | 'profile' | 'processing' | 'review';

const STEPS: { key: WizardStep; label: string }[] = [
  { key: 'welcome', label: 'Welcome' },
  { key: 'consent', label: 'Privacy' },
  { key: 'profile', label: 'Profile' },
  { key: 'processing', label: 'Generating' },
  { key: 'review', label: 'Review' },
];

const STEP_ORDER: WizardStep[] = ['welcome', 'consent', 'profile', 'processing', 'review'];

const STORAGE_KEY = 'onboarding-step';

const slideVariants = {
  enter: (direction: number) => ({
    x: direction > 0 ? 300 : -300,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (direction: number) => ({
    x: direction < 0 ? 300 : -300,
    opacity: 0,
  }),
};

function getInitialStep(): WizardStep {
  if (typeof window !== 'undefined') {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved && STEP_ORDER.includes(saved as WizardStep)) {
        return saved as WizardStep;
      }
    } catch {
      // sessionStorage not available
    }
  }
  return 'welcome';
}

export function OnboardingWizard() {
  const navigate = useNavigate();

  const [currentStep, setCurrentStep] = useState<WizardStep>(getInitialStep);
  const [direction, setDirection] = useState(1);
  const [consentComplete, setConsentComplete] = useState(false);
  const [profileComplete, setProfileComplete] = useState(false);
  const [generationResult, setGenerationResult] = useState<GenerateProfileResponseDTO | null>(null);
  // Collect profile data for the processing step
  const [profileDataForGen, setProfileDataForGen] = useState<Record<string, string> | null>(null);
  // Track which mode was chosen for the complete flow
  const profileModeRef = useRef<'full' | 'general' | null>(null);

  // Persist step to sessionStorage when it changes
  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, currentStep);
    } catch {
      // sessionStorage not available
    }
  }, [currentStep]);

  const stepIndex = STEP_ORDER.indexOf(currentStep);

  const canGoBack = stepIndex > 0 && currentStep !== 'processing';
  const canGoForward = useCallback(() => {
    if (currentStep === 'welcome') return true;
    if (currentStep === 'consent') return consentComplete;
    if (currentStep === 'profile') return profileComplete;
    return false;
  }, [currentStep, consentComplete, profileComplete]);

  const goNext = () => {
    if (!canGoForward()) return;
    const nextIndex = stepIndex + 1;
    if (nextIndex < STEP_ORDER.length) {
      setDirection(1);
      setCurrentStep(STEP_ORDER[nextIndex]);
    }
  };

  const goBack = () => {
    if (!canGoBack) return;
    setDirection(-1);
    setCurrentStep(STEP_ORDER[stepIndex - 1]);
  };

  // ── Complete onboarding: save data to backend, then navigate to /chat ──
  const handleComplete = useCallback(async () => {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      // sessionStorage not available
    }
    try {
      const { api } = await import('@/lib/api');
      const { useProfileStore } = await import('@/stores/profileStore');
      const { useConsentStore: store } = await import('@/stores/consentStore');

      // Save profile to backend if full profile was collected
      const profile = useProfileStore.getState().profile;
      if (profile) {
        await api.profile.upsert({
          preferred_name: profile.preferredName,
          age_range: profile.ageRange,
          gender_identity: profile.genderIdentity,
          pronouns: profile.pronouns,
          primary_language: profile.primaryLanguage,
          disability: profile.disability,
          immigration_status: profile.immigrationStatus,
          indigenous_identity: profile.indigenousIdentity,
          education_level: profile.educationLevel,
          literacy_comfort_ai: profile.literacyComfortAI,
          profile_mode: profile.profileMode,
        });
      }

      // Save consent to backend
      const consent = store.getState();
      await api.profile.updateConsent({
        profile_mode: consent.profileMode ?? undefined,
        research_data_consent: consent.researchDataConsent,
        chat_history_consent: consent.chatHistoryConsent,
      });

      // Mark onboarding complete
      await api.auth.completeOnboarding();
    } catch {
      // best-effort
    }
    useAuthStore.getState().completeOnboarding();
    useConsentStore.getState().setHasConsented(true);
    navigate('/chat');
  }, [navigate]);

  // ── Consent step complete ──────────────────────────────────────────────
  const handleConsentComplete = useCallback((complete: boolean) => {
    setConsentComplete(complete);
  }, []);

  // ── Profile step complete (FullProfileForm) ────────────────────────────
  const handleProfileComplete = useCallback((complete: boolean) => {
    setProfileComplete(complete);
    if (complete) {
      profileModeRef.current = 'full';
      // Build profile data for the generation step from the store
      const stored = useProfileStore.getState().profile;
      if (stored) {
        setProfileDataForGen({
          sex_at_birth: stored.genderIdentity?.includes('man') ? 'male' : stored.genderIdentity?.includes('woman') ? 'female' : 'Prefer not to say',
          gender: stored.genderIdentity?.join(', ') || 'Not specified',
          age_group: stored.ageRange ? stored.ageRange.replace(/_/g, '–') : 'Adult (18–64 years)',
          primary_language: stored.primaryLanguage || 'English',
          education_level: stored.educationLevel ? stored.educationLevel.replace(/_/g, ' ') : 'Some post-secondary education',
          citizen_status: stored.immigrationStatus ? stored.immigrationStatus.replace(/_/g, ' ') : 'Canadian citizen / Permanent resident',
          indigenous_status: stored.indigenousIdentity ? stored.indigenousIdentity.replace(/_/g, ' ') : 'Non-Indigenous',
          disability_status: stored.disability?.join(', ') || 'No disclosed disability',
        });
      }
      // Navigate to processing step
      setDirection(1);
      setCurrentStep('processing');
    }
  }, []);

  // ── Generation complete (processing → review) ──────────────────────────
  const handleGenerationComplete = useCallback((result: GenerateProfileResponseDTO) => {
    setGenerationResult(result);
    setDirection(1);
    setCurrentStep('review');
  }, []);

  // ── Review complete → finish onboarding ────────────────────────────────
  const handleReviewComplete = useCallback(() => {
    handleComplete();
  }, [handleComplete]);

  return (
    <div className="min-h-screen flex flex-col bg-background" suppressHydrationWarning>
      {/* Header with branding */}
      <header className="border-b bg-card">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
            <Shield className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="font-display font-semibold text-lg">Responsible AI</span>
        </div>
      </header>

      {/* Step indicator - breadcrumb style */}
      <nav
        aria-label="Onboarding progress"
        className="border-b bg-card"
      >
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-2">
          {STEPS.map((step, idx) => {
            const isActive = step.key === currentStep;
            const isPast = STEP_ORDER.indexOf(step.key) < stepIndex;
            return (
              <div key={step.key} className="flex items-center gap-2">
                {idx > 0 && (
                  <span className="text-muted-foreground/40 text-sm" aria-hidden="true">
                    /
                  </span>
                )}
                <span
                  className={cn(
                    'text-sm font-medium transition-colors',
                    isActive && 'text-primary',
                    isPast && 'text-muted-foreground',
                    !isActive && !isPast && 'text-muted-foreground/50'
                  )}
                  aria-current={isActive ? 'step' : undefined}
                >
                  {step.label}
                </span>
              </div>
            );
          })}
        </div>
      </nav>

      {/* Main content area */}
      <main className="flex-1 flex items-start justify-center py-8 px-4">
        <div className="w-full max-w-2xl">
          <AnimatePresence mode="wait" custom={direction}>
            {currentStep === 'welcome' && (
              <motion.div
                key="welcome"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                <WelcomeContent />
              </motion.div>
            )}
            {currentStep === 'consent' && (
              <motion.div
                key="consent"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                <ConsentStep onComplete={handleConsentComplete} />
              </motion.div>
            )}
            {currentStep === 'profile' && (
              <motion.div
                key="profile"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                <ProfileModeSelector
                  onComplete={(complete) => {
                    // Check which mode was chosen
                    const consent = useConsentStore.getState();
                    if (complete && consent.profileMode === 'general') {
                      // General mode: skip processing/review, go straight to complete
                      profileModeRef.current = 'general';
                      handleComplete();
                    } else if (complete) {
                      // Full profile mode: trigger the profile handler
                      handleProfileComplete(complete);
                    }
                  }}
                />
              </motion.div>
            )}
            {currentStep === 'processing' && profileDataForGen && (
              <motion.div
                key="processing"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                <ProfileProcessingStep
                  userProfile={profileDataForGen}
                  onComplete={handleGenerationComplete}
                />
              </motion.div>
            )}
            {currentStep === 'review' && generationResult && (
              <motion.div
                key="review"
                custom={direction}
                variants={slideVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{ duration: 0.3, ease: 'easeInOut' }}
              >
                <ProfileReviewStep
                  result={generationResult}
                  onComplete={handleReviewComplete}
                />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Navigation footer — hidden during processing and review */}
      {currentStep !== 'processing' && currentStep !== 'review' && (
        <footer className="border-t bg-card mt-auto">
          <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
            <Button
              variant="ghost"
              onClick={goBack}
              disabled={!canGoBack}
              className="gap-1"
              aria-label="Go back"
            >
              <ChevronLeft className="w-4 h-4" />
              Back
            </Button>

            {currentStep === 'profile' ? null : (
              <Button
                onClick={goNext}
                disabled={!canGoForward()}
                className="gap-1"
                aria-label={
                  currentStep === 'welcome'
                    ? 'Continue to privacy settings'
                    : 'Continue to profile'
                }
              >
                Continue
                <ChevronRight className="w-4 h-4" />
              </Button>
            )}
          </div>
        </footer>
      )}
    </div>
  );
}

/* ── Welcome step content ─────────────────────────────────────────── */

function WelcomeContent() {
  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight text-foreground">
          Welcome to Responsible AI
        </h1>
      </div>

      <div className="space-y-4 text-muted-foreground text-base leading-relaxed max-w-lg mx-auto text-center">
        <p>
          This system connects you with an AI assistant trained on curated,
          reliable sources. It&apos;s designed to provide thoughtful, accurate
          answers to your questions.
        </p>
        <p>
          Before we begin, we&apos;ll ask about your privacy preferences. You&apos;re
          in control of what information is stored.
        </p>
        <p>
          You can update your privacy settings at any time from the Settings
          page.
        </p>
      </div>
    </div>
  );
}
