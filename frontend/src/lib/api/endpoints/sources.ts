/** Knowledge-base source and dashboard endpoints. */

import { apiRequest, apiUpload } from '../client';
import type {
  SourceCreateRequestDTO,
  SourceListResponseDTO,
  SourceResponseDTO,
  SourceUpdateRequestDTO,
  StatsResponseDTO,
  UploadResponseDTO,
  WebPageUploadRequestDTO,
  YouTubeUploadRequestDTO,
} from '../types/source';

export const sourceEndpoints = {
  /** List sources, optionally filtered by status. */
  list: (page = 1, limit = 20, status?: string) => {
    const params = new URLSearchParams({
      page: String(page),
      limit: String(limit),
    });
    if (status) params.set('status', status);
    return apiRequest<SourceListResponseDTO>('GET', `/admin/sources?${params}`);
  },

  /** Get a single source. */
  get: (id: string) =>
    apiRequest<SourceResponseDTO>('GET', `/admin/sources/${id}`),

  /** Create a source from metadata alone. */
  create: (body: SourceCreateRequestDTO) =>
    apiRequest<SourceResponseDTO>('POST', '/admin/sources', body),

  /** Update source metadata. */
  update: (id: string, body: SourceUpdateRequestDTO) =>
    apiRequest<SourceResponseDTO>('PUT', `/admin/sources/${id}`, body),

  /** Delete a source and all of its chunks. */
  delete: (id: string) =>
    apiRequest<{ status: string; source_id: string }>(
      'DELETE',
      `/admin/sources/${id}`,
    ),

  /** Upload a file for background ingestion. */
  upload: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiUpload<UploadResponseDTO>('/admin/sources/upload', formData);
  },

  /** Submit a YouTube URL for background transcription and ingestion. */
  uploadYouTube: (body: YouTubeUploadRequestDTO) =>
    apiRequest<UploadResponseDTO>('POST', '/admin/sources/youtube', body),

  /** Submit a webpage URL for background scraping and ingestion. */
  uploadWebpage: (body: WebPageUploadRequestDTO) =>
    apiRequest<UploadResponseDTO>('POST', '/admin/sources/webpage', body),
};

export const dashboardEndpoints = {
  /** Aggregate platform statistics for the admin dashboard. */
  stats: () => apiRequest<StatsResponseDTO>('GET', '/admin/dashboard/stats'),
};
