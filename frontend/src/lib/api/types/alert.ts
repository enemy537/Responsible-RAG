/** Admin alert and embedding-cooldown DTOs. */

export interface AdminAlertDTO {
  id: string;
  type: string;
  severity: 'info' | 'warning' | 'critical';
  title: string;
  message: string;
  cooldown_until: string | null;
  timestamp: string;
  resolved: string;
}

export interface AdminAlertListResponseDTO {
  alerts: AdminAlertDTO[];
  total: number;
  unresolved_count: number;
}

export interface CooldownStatusDTO {
  in_cooldown: boolean;
  remaining_seconds: number;
  remaining_minutes: number;
  cooldown_duration_seconds: number;
}
