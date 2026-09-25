/** Admin alert and embedding-cooldown endpoints. */

import { apiRequest } from '../client';
import type {
  AdminAlertListResponseDTO,
  CooldownStatusDTO,
} from '../types/alert';

export const alertEndpoints = {
  /** List all system alerts, newest first. */
  list: () => apiRequest<AdminAlertListResponseDTO>('GET', '/admin/alerts'),

  /** Mark an alert as resolved. */
  resolve: (alertId: string) =>
    apiRequest<{ status: string; alert_id: string }>(
      'POST',
      `/admin/alerts/resolve?alert_id=${encodeURIComponent(alertId)}`,
    ),

  /** Get the current embedding cooldown status. */
  cooldown: () => apiRequest<CooldownStatusDTO>('GET', '/admin/alerts/cooldown'),
};
