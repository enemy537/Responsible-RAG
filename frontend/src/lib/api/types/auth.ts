/** Authentication DTOs. */

export interface LoginRequestDTO {
  email: string;
  password: string;
}

export interface RegisterRequestDTO {
  email: string;
  password: string;
  name: string;
}

export interface AuthUserDTO {
  id: string;
  email: string;
  name: string;
  provider: string;
  role: 'user' | 'admin';
  verified: boolean;
  created_at: string;
}

export interface LoginResponseDTO {
  access_token: string;
  token_type: string;
}
