// ─────────────────────────────────────────────────────────────
// @aira/types — Shared TypeScript types for the AIRA platform
// ─────────────────────────────────────────────────────────────

// ── Base Entity ──────────────────────────────────────────────

/** Base entity with audit fields shared by all database models. */
export interface BaseEntity {
  id: string;
  createdAt: Date;
  updatedAt: Date;
  deletedAt: Date | null;
}

// ── API Response ─────────────────────────────────────────────

/** Standard API success envelope. */
export interface ApiResponse<T> {
  success: true;
  data: T;
  meta?: Record<string, unknown>;
  timestamp: string;
  requestId?: string;
}

/** Paginated API response. */
export interface PaginatedResponse<T> {
  success: true;
  data: T[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrevious: boolean;
  };
  timestamp: string;
  requestId?: string;
}

/** Standard API error envelope. */
export interface ApiError {
  success: false;
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    stack?: string;
  };
  timestamp: string;
  requestId?: string;
}

// ── Auth ─────────────────────────────────────────────────────

/** JWT payload stored inside access tokens. */
export interface JwtPayload {
  sub: string;
  email: string;
  role: string;
  iat: number;
  exp: number;
}

/** Authenticated user object attached to requests. */
export interface AuthUser {
  id: string;
  email: string;
  role: string;
  firstName: string;
  lastName: string;
}

/** Pair of tokens returned after login / refresh. */
export interface TokenPair {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

// ── Utility Types ────────────────────────────────────────────

export type Nullable<T> = T | null;
export type Optional<T> = T | undefined;
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

// ── Environment ──────────────────────────────────────────────

export enum Environment {
  Development = 'development',
  Test = 'test',
  Staging = 'staging',
  Production = 'production',
}

export interface AppConfig {
  name: string;
  version: string;
  port: number;
  env: Environment;
  url: string;
}

// ── Events ───────────────────────────────────────────────────

export interface EventMetadata {
  eventId: string;
  timestamp: string;
  source: string;
  correlationId?: string;
  userId?: string;
}

export interface DomainEvent<T = unknown> {
  type: string;
  payload: T;
  metadata: EventMetadata;
}

// ── Health ───────────────────────────────────────────────────

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy';

export interface HealthCheckResult {
  status: HealthStatus;
  timestamp: string;
  version: string;
  uptime: number;
  checks: Record<string, { status: HealthStatus; message?: string; latency?: number }>;
}

// ── Pagination ───────────────────────────────────────────────

export interface PaginationParams {
  page: number;
  pageSize: number;
}

export type SortDirection = 'asc' | 'desc';

export interface SortParams {
  field: string;
  direction: SortDirection;
}

// ── Result Type ──────────────────────────────────────────────

export type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

export function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

export function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

export function isOk<T, E>(result: Result<T, E>): result is { ok: true; value: T } {
  return result.ok;
}

export function isErr<T, E>(result: Result<T, E>): result is { ok: false; error: E } {
  return !result.ok;
}
