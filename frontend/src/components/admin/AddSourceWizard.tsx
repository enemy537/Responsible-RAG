'use client';

import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SourceTypeSelector } from '@/components/admin/SourceTypeSelector';
import { FileUploadZone } from '@/components/admin/FileUploadZone';
import { UrlInputCard } from '@/components/admin/UrlInputCard';
import { MetadataForm } from '@/components/admin/MetadataForm';
import { api } from '@/lib/api';
import type { SourceType } from '@/types/source';
import type { SourceMetadataFormData } from '@/lib/schemas/source.schema';
import type { ExtractedMetadata } from '@/lib/utils/metadataExtractor';
import type { UploadedFile as UploadedFileData } from '@/components/admin/FileUploadZone';
import { cn } from '@/lib/utils';

type WizardStep = 'type' | 'upload' | 'metadata';

interface StepConfig {
  key: WizardStep;
  label: string;
  number: number;
}

const steps: StepConfig[] = [
  { key: 'type', label: 'Source Type', number: 1 },
  { key: 'upload', label: 'Upload Content', number: 2 },
  { key: 'metadata', label: 'Metadata', number: 3 },
];

const fileTypes: SourceType[] = ['pdf', 'text', 'audio'];
const urlTypes: SourceType[] = ['webpage', 'youtube'];

export function AddSourceWizard() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState<WizardStep>('type');
  const [selectedType, setSelectedType] = useState<SourceType | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFileData[]>([]);
  const [urlValue, setUrlValue] = useState('');
  const [fetchedMetadata, setFetchedMetadata] = useState<ExtractedMetadata | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const stepIndex = steps.findIndex((s) => s.key === currentStep);

  const goToStep = (step: WizardStep) => setCurrentStep(step);

  const handleTypeSelect = (type: SourceType) => {
    setSelectedType(type);
    goToStep('upload');
  };

  const handleUploadComplete = (files: UploadedFileData[]) => {
    setUploadedFiles(files);
    goToStep('metadata');
  };

  const handleMetadataFetched = (url: string, metadata: ExtractedMetadata) => {
    setUrlValue(url);
    setFetchedMetadata(metadata);
  };

  const handleUrlContinue = useCallback(async () => {
    if (!urlValue) return;
    setSubmitting(true);
    try {
      if (selectedType === 'youtube') {
        // YouTube: submit for background transcription & ingestion
        const payload = {
          url: urlValue,
          title: fetchedMetadata?.title || urlValue,
          authors: fetchedMetadata?.authors || [],
          publication_date: fetchedMetadata?.publicationDate || null,
          publisher: fetchedMetadata?.publisher || 'YouTube',
          description: fetchedMetadata?.description || null,
          language: fetchedMetadata?.language || null,
        };
        await api.sources.uploadYouTube(payload);
        toast.success('YouTube source submitted for processing');
      } else {
        // Webpage: submit for background scraping & ingestion
        const payload = {
          url: urlValue,
          title: fetchedMetadata?.title || urlValue,
          source_type: 'webpage',
          authors: fetchedMetadata?.authors || [],
          publication_date: fetchedMetadata?.publicationDate || null,
          publisher: fetchedMetadata?.publisher || null,
          description: fetchedMetadata?.description || null,
          language: fetchedMetadata?.language || null,
        };
        await api.sources.uploadWebpage(payload);
        toast.success('Webpage source submitted for processing');
      }
      navigate('/admin/sources');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to create source from URL';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }, [urlValue, fetchedMetadata, selectedType, navigate]);

  const handleMetadataSubmit = async (data: SourceMetadataFormData) => {
    setSubmitting(true);
    try {
      const metadataPayload = {
        title: data.title,
        source_type: selectedType!,
        authors: data.authors,
        publication_date: data.publicationDate ?? null,
        publisher: data.publisher ?? null,
        url: data.url,
        doi: data.doi ?? null,
        language: data.language ?? null,
        description: data.description ?? null,
        tags: data.tags,
        content_sensitivity: data.contentSensitivity,
        internal_notes: data.internalNotes ?? null,
      };

      if (uploadedFiles.length > 0) {
        // Files are already uploaded (POST /upload). Now update metadata.
        for (const f of uploadedFiles) {
          if (f.sourceId) {
            await api.sources.update(f.sourceId, metadataPayload);
          }
        }
        toast.success('SAVED, processing now — your file is being chunked and embedded in the background.');
      } else {
        // Metadata-only source
        await api.sources.create(metadataPayload);
        toast.success('Source created');
      }
      navigate('/admin/sources');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to save source';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleBack = () => {
    if (currentStep === 'upload') {
      setCurrentStep('type');
    } else if (currentStep === 'metadata') {
      setCurrentStep('upload');
    }
  };

  const metadataInitialData: Partial<SourceMetadataFormData> | undefined = fetchedMetadata
    ? {
        title: fetchedMetadata.title ?? undefined,
        authors: fetchedMetadata.authors,
        publicationDate: fetchedMetadata.publicationDate ?? undefined,
        publisher: fetchedMetadata.publisher ?? undefined,
        description: fetchedMetadata.description ?? undefined,
        language: fetchedMetadata.language ?? undefined,
      }
    : undefined;

  return (
    <div className="space-y-8">
      {/* Step indicator */}
      <div className="flex items-center justify-center gap-2">
        {steps.map((step, i) => {
          const isActive = step.key === currentStep;
          const isComplete = i < stepIndex;
          return (
            <div key={step.key} className="flex items-center">
              {i > 0 && (
                <div
                  className={cn(
                    'w-8 sm:w-16 h-0.5 mx-1',
                    isComplete ? 'bg-primary' : 'bg-muted-foreground/20'
                  )}
                />
              )}
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold border-2 transition-colors',
                    isActive
                      ? 'border-primary bg-primary text-primary-foreground'
                      : isComplete
                        ? 'border-primary bg-primary text-primary-foreground'
                        : 'border-muted-foreground/30 text-muted-foreground bg-background'
                  )}
                >
                  {isComplete ? <Check className="w-4 h-4" /> : step.number}
                </div>
                <span
                  className={cn(
                    'text-sm font-medium hidden sm:inline',
                    isActive ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  {step.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <div>
        {currentStep === 'type' && (
          <SourceTypeSelector value={selectedType} onChange={handleTypeSelect} />
        )}

        {currentStep === 'upload' && selectedType && (
          <div className="space-y-6">
            {fileTypes.includes(selectedType) && (
              <FileUploadZone
                sourceType={selectedType}
                onUploadComplete={handleUploadComplete}
              />
            )}
            {urlTypes.includes(selectedType) && (
              <div className="space-y-4">
                <UrlInputCard
                  sourceType={selectedType}
                  onMetadataFetched={handleMetadataFetched}
                />
                {fetchedMetadata && (
                  <div className="flex justify-end">
                    <Button onClick={handleUrlContinue} disabled={submitting}>
                      {submitting ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating source…</>
                      ) : (
                        'Continue to metadata →'
                      )}
                    </Button>
                  </div>
                )}
              </div>
            )}
            <div className="flex justify-start">
              <Button variant="outline" onClick={handleBack}>
                ← Back
              </Button>
            </div>
          </div>
        )}

        {currentStep === 'metadata' && selectedType && (
          <div className="space-y-6">
            <MetadataForm
              sourceType={selectedType}
              initialData={metadataInitialData}
              onSubmit={handleMetadataSubmit}
              disabled={submitting}
            />
            <div className="flex justify-start">
              <Button variant="outline" onClick={handleBack}>
                ← Back
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
