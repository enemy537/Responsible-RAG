/** Knowledge-base source DTOs. */

export interface SourceResponseDTO {
  id: string;
  title: string;
  source_type: string;
  authors: string[];
  publication_date: string | null;
  publisher: string | null;
  url: string;
  doi: string | null;
  language: string | null;
  description: string | null;
  tags: string[];
  content_sensitivity: string;
  internal_notes: string | null;
  status: 'processing' | 'indexed' | 'error';
  error_message: string | null;
  chunk_count: number;
}

export interface SourceListResponseDTO {
  sources: SourceResponseDTO[];
  total: number;
  page: number;
  limit: number;
}

export interface SourceCreateRequestDTO {
  title: string;
  source_type: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  url: string;
  doi?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface SourceUpdateRequestDTO {
  title?: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  url?: string | null;
  doi?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface WebPageUploadRequestDTO {
  url: string;
  title: string;
  source_type?: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface YouTubeUploadRequestDTO {
  url: string;
  title: string;
  authors?: string[];
  publication_date?: string | null;
  publisher?: string | null;
  language?: string | null;
  description?: string | null;
  tags?: string[];
  content_sensitivity?: string;
  internal_notes?: string | null;
}

export interface UploadResponseDTO {
  id: string;
  filename: string;
  source_type: string;
  status: 'processing' | 'indexed' | 'error';
  chunk_count: number;
}

export interface StatsResponseDTO {
  total_sources: number;
  indexed_sources: number;
  processing_sources: number;
  error_sources: number;
  incomplete_metadata: number;
  /** Whether the embedding API is in cooldown (quota exceeded). */
  embedding_cooldown_active: boolean;
  /** Seconds remaining in the current cooldown (0 if none). */
  embedding_cooldown_remaining_seconds: number;
  /** Number of unresolved system alerts. */
  unresolved_alerts: number;
}
