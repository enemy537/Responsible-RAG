'use client';

import { useState, useEffect } from 'react';
import { UserCheck, Lock, ChevronDown } from 'lucide-react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import { useConsentStore } from '@/stores/consentStore';
import type { ProfileMode } from '@/types/profile';

interface ConsentStepProps {
  onComplete: (complete: boolean) => void;
}

export function ConsentStep({ onComplete }: ConsentStepProps) {
  const profileMode = useConsentStore((s) => s.profileMode);
  const setProfileMode = useConsentStore((s) => s.setProfileMode);
  const researchDataConsent = useConsentStore((s) => s.researchDataConsent);
  const setResearchDataConsent = useConsentStore((s) => s.setResearchDataConsent);
  const chatHistoryConsent = useConsentStore((s) => s.chatHistoryConsent);
  const setChatHistoryConsent = useConsentStore((s) => s.setChatHistoryConsent);
  const [selectedMode, setSelectedMode] = useState<ProfileMode | null>(
    profileMode
  );
  const [researchConsent, setResearchConsent] = useState(
    researchDataConsent
  );
  const [saveHistory, setSaveHistory] = useState(chatHistoryConsent);
  const [fullLearnOpen, setFullLearnOpen] = useState(false);
  const [generalLearnOpen, setGeneralLearnOpen] = useState(false);

  // Update parent when selection changes
  useEffect(() => {
    const isComplete = selectedMode !== null;
    onComplete(isComplete);

    if (selectedMode) {
      setProfileMode(selectedMode);
    }
    setResearchDataConsent(researchConsent);
    setChatHistoryConsent(saveHistory);
  }, [
    selectedMode,
    researchConsent,
    saveHistory,
    setProfileMode,
    setResearchDataConsent,
    setChatHistoryConsent,
    onComplete,
  ]);

  const handleSelectMode = (mode: ProfileMode) => {
    setSelectedMode(mode);
  };

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="font-display text-2xl sm:text-3xl font-semibold tracking-tight text-foreground">
          Your privacy matters
        </h2>
        <p className="text-muted-foreground text-base max-w-md mx-auto">
          Choose how the system interacts with you. Both options give you access
          to the same AI assistant.
        </p>
      </div>

      {/* Two equally prominent cards */}
      <div className="grid sm:grid-cols-2 gap-4">
        {/* Option A — Full Profile Mode */}
        <Card
          role="radio"
          aria-checked={selectedMode === 'full'}
          tabIndex={0}
          onClick={() => handleSelectMode('full')}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleSelectMode('full');
            }
          }}
          className={cn(
            'cursor-pointer transition-all duration-200 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            selectedMode === 'full'
              ? 'ring-2 ring-primary shadow-md'
              : 'hover:border-primary/30'
          )}
        >
          <CardHeader className="pb-0">
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-colors',
                  selectedMode === 'full'
                    ? 'bg-primary/15 text-primary'
                    : 'bg-muted text-primary'
                )}
              >
                <UserCheck className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <CardTitle className="text-base">Personalize my experience</CardTitle>
                <CardDescription className="mt-1">
                  I allow the system to store my profile and use it to adapt
                  answers. I understand my communications may be recorded for
                  research.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <Collapsible open={fullLearnOpen} onOpenChange={setFullLearnOpen}>
              <CollapsibleTrigger asChild>
                <button
                  className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 font-medium mt-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-expanded={fullLearnOpen}
                >
                  Learn more
                  <ChevronDown
                    className={cn(
                      'w-4 h-4 transition-transform duration-200',
                      fullLearnOpen && 'rotate-180'
                    )}
                  />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground leading-relaxed">
                Your profile data (age range, language preferences, accessibility
                needs) is stored securely and used solely to tailor AI responses.
                Conversation history may be accessed by the research team in
                anonymized form. You can delete your data at any time from
                Settings.
              </CollapsibleContent>
            </Collapsible>
          </CardContent>
        </Card>

        {/* Option B — General Mode */}
        <Card
          role="radio"
          aria-checked={selectedMode === 'general'}
          tabIndex={0}
          onClick={() => handleSelectMode('general')}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleSelectMode('general');
            }
          }}
          className={cn(
            'cursor-pointer transition-all duration-200 hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            selectedMode === 'general'
              ? 'ring-2 ring-primary shadow-md'
              : 'hover:border-primary/30'
          )}
        >
          <CardHeader className="pb-0">
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-colors',
                  selectedMode === 'general'
                    ? 'bg-primary/15 text-primary'
                    : 'bg-muted text-muted-foreground'
                )}
              >
                <Lock className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <CardTitle className="text-base">I prefer privacy</CardTitle>
                <CardDescription className="mt-1">
                  The system will not store personal information about me or adapt
                  to my profile. I will be asked a few questions after each
                  conversation instead.
                </CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <Collapsible open={generalLearnOpen} onOpenChange={setGeneralLearnOpen}>
              <CollapsibleTrigger asChild>
                <button
                  className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 font-medium mt-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                  aria-expanded={generalLearnOpen}
                >
                  Learn more
                  <ChevronDown
                    className={cn(
                      'w-4 h-4 transition-transform duration-200',
                      generalLearnOpen && 'rotate-180'
                    )}
                  />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 text-sm text-muted-foreground leading-relaxed">
                No personal data is collected or stored. Instead, you may be asked
                optional feedback after each conversation. This helps improve the
                system without compromising your privacy.
              </CollapsibleContent>
            </Collapsible>
          </CardContent>
        </Card>
      </div>

      {/* Research data consent checkbox */}
      <div className="flex items-start gap-3 pt-2">
        <Checkbox
          id="research-consent"
          checked={researchConsent}
          onCheckedChange={(checked) => setResearchConsent(checked === true)}
          aria-describedby="research-consent-desc"
        />
        <div className="grid gap-1 leading-none">
          <Label
            htmlFor="research-consent"
            className="text-sm font-medium leading-relaxed cursor-pointer"
          >
            I allow my anonymized conversation data to be used for research
            improvement
          </Label>
          <p id="research-consent-desc" className="text-xs text-muted-foreground">
            This data is always anonymized and never linked to your identity.
          </p>
        </div>
      </div>

      {/* Chat history consent checkbox */}
      <div className="flex items-start gap-3 pt-2">
        <Checkbox
          id="chat-history-consent"
          checked={saveHistory}
          onCheckedChange={(checked) => setSaveHistory(checked === true)}
          aria-describedby="chat-history-consent-desc"
        />
        <div className="grid gap-1 leading-none">
          <Label
            htmlFor="chat-history-consent"
            className="text-sm font-medium leading-relaxed cursor-pointer"
          >
            I allow my conversations to be saved so I can revisit them
          </Label>
          <p id="chat-history-consent-desc" className="text-xs text-muted-foreground">
            If you turn this off, conversations are kept only for the current
            session and then discarded.
          </p>
        </div>
      </div>

      {/* Selection confirmation message */}
      {selectedMode && (
        <p className="text-sm text-center text-muted-foreground" role="status">
          {selectedMode === 'full'
            ? 'You selected personalized experience. Press Continue to set up your profile.'
            : 'You selected privacy mode. Press Continue to proceed.'}
        </p>
      )}
    </div>
  );
}
