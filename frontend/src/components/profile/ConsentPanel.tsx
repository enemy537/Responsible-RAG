'use client';

import { useState } from 'react';
import { UserCheck, Lock, ArrowRightLeft } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useConsentStore } from '@/stores/consentStore';
import { useProfileStore } from '@/stores/profileStore';
import { api } from '@/lib/api';
import { getModeSwitchConfirmation } from '@/lib/utils/privacyHelpers';
import { cn } from '@/lib/utils';

export function ConsentPanel() {
  const consentStore = useConsentStore();
  const profileStore = useProfileStore();

  const [showModeDialog, setShowModeDialog] = useState(false);

  const currentMode = consentStore.profileMode ?? 'general';
  const isFull = currentMode === 'full';
  const targetMode = isFull ? 'general' : 'full';
  const confirmation = getModeSwitchConfirmation(currentMode, targetMode);

  const handleModeSwitch = () => {
    if (targetMode === 'general') {
      // Switching to General — delete profile
      profileStore.setProfile(null);
      consentStore.setProfileMode('general');
    } else {
      // Switching to Full — just set mode, profile form will be needed
      consentStore.setProfileMode('full');
    }
    setShowModeDialog(false);
  };

  const handleChatHistoryChange = async (enabled: boolean) => {
    consentStore.setChatHistoryConsent(enabled);
    try {
      await api.profile.updateConsent({ chat_history_consent: enabled });
    } catch (err) {
      console.error('Failed to save chat history preference', err);
    }
  };

  return (
    <>
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base font-display">Consent & Mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Current mode */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  'w-10 h-10 rounded-full flex items-center justify-center',
                  isFull ? 'bg-primary/10' : 'bg-muted'
                )}
              >
                {isFull ? (
                  <UserCheck className="w-5 h-5 text-primary" />
                ) : (
                  <Lock className="w-5 h-5 text-muted-foreground" />
                )}
              </div>
              <div>
                <p className="text-sm font-medium">
                  {isFull ? 'Full Profile' : 'General'} Mode
                </p>
                <p className="text-xs text-muted-foreground">
                  {isFull
                    ? 'Personalized responses based on your profile'
                    : 'No personal data is stored or used'}
                </p>
              </div>
            </div>
            <Badge
              variant="outline"
              className={cn(
                isFull
                  ? 'border-primary/30 text-primary'
                  : 'border-muted-foreground/30 text-muted-foreground'
              )}
            >
              {isFull ? 'Personalized' : 'Private'}
            </Badge>
          </div>

          {/* Research data consent toggle */}
          <div className="flex items-center justify-between gap-4 py-2">
            <div className="space-y-0.5">
              <Label
                htmlFor="research-consent"
                className="text-sm font-medium cursor-pointer"
              >
                Research data sharing
              </Label>
              <p className="text-xs text-muted-foreground">
                Allow anonymized conversation data to be used for research
              </p>
            </div>
            <Switch
              id="research-consent"
              checked={consentStore.researchDataConsent}
              onCheckedChange={consentStore.setResearchDataConsent}
            />
          </div>

          {/* Chat history storage toggle */}
          <div className="flex items-center justify-between gap-4 py-2">
            <div className="space-y-0.5">
              <Label
                htmlFor="chat-history-consent"
                className="text-sm font-medium cursor-pointer"
              >
                Save chat history
              </Label>
              <p className="text-xs text-muted-foreground">
                {consentStore.chatHistoryConsent
                  ? 'Conversations are stored so you can revisit them'
                  : 'Conversations are kept for this session only, then discarded'}
              </p>
            </div>
            <Switch
              id="chat-history-consent"
              checked={consentStore.chatHistoryConsent}
              onCheckedChange={handleChatHistoryChange}
            />
          </div>

          {/* Mode switch button */}
          <Button
            variant="outline"
            className="w-full gap-2"
            onClick={() => setShowModeDialog(true)}
          >
            <ArrowRightLeft className="w-4 h-4" />
            Switch to {isFull ? 'General' : 'Full Profile'} Mode
          </Button>
        </CardContent>
      </Card>

      {/* Mode switch confirmation dialog — NOT dismissible by clicking outside */}
      <AlertDialog
        open={showModeDialog}
        onOpenChange={(open) => {
          // Intentional friction: prevent closing by clicking outside
          if (!open) return;
          setShowModeDialog(true);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmation.title}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmation.description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setShowModeDialog(false)}
              className="cursor-pointer"
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleModeSwitch}
              className={cn(
                confirmation.isDestructive &&
                  'bg-destructive text-destructive-foreground hover:bg-destructive/90'
              )}
            >
              {confirmation.isDestructive
                ? 'Yes, switch to General'
                : 'Yes, switch to Full Profile'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
