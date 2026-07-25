// ─────────────────────────────────────────────────────────────
// @aira/constants — Application-wide constants and enums
// ─────────────────────────────────────────────────────────────

/** Standard HTTP status codes used across the platform. */
export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  NO_CONTENT: 204,
  MOVED_PERMANENTLY: 301,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  CONFLICT: 409,
  UNPROCESSABLE_ENTITY: 422,
  TOO_MANY_REQUESTS: 429,
  INTERNAL_SERVER_ERROR: 500,
  BAD_GATEWAY: 502,
  SERVICE_UNAVAILABLE: 503,
} as const;

/** Environment name constants. */
export const ENVIRONMENT = {
  DEVELOPMENT: 'development',
  TEST: 'test',
  STAGING: 'staging',
  PRODUCTION: 'production',
} as const;

/** Authentication-related constants. */
export const AUTH = {
  ACCESS_TOKEN_EXPIRY: '15m',
  REFRESH_TOKEN_EXPIRY: '7d',
  COOKIE_NAME: 'aira_refresh_token',
  HEADER_NAME: 'Authorization',
  BEARER_PREFIX: 'Bearer ',
  REFRESH_COOKIE_MAX_AGE: 7 * 24 * 60 * 60 * 1000, // 7 days in ms
  BCRYPT_ROUNDS: 12,
} as const;

/** Standardised error codes for the API error envelope. */
export const ERROR_CODES = {
  // Authentication errors
  AUTH_INVALID_CREDENTIALS: 'AUTH_INVALID_CREDENTIALS',
  AUTH_TOKEN_EXPIRED: 'AUTH_TOKEN_EXPIRED',
  AUTH_TOKEN_INVALID: 'AUTH_TOKEN_INVALID',
  AUTH_UNAUTHORIZED: 'AUTH_UNAUTHORIZED',
  AUTH_REFRESH_FAILED: 'AUTH_REFRESH_FAILED',

  // Authorisation errors
  FORBIDDEN: 'FORBIDDEN',

  // Validation errors
  VALIDATION_FAILED: 'VALIDATION_FAILED',

  // Resource errors
  NOT_FOUND: 'NOT_FOUND',
  CONFLICT: 'CONFLICT',
  ALREADY_EXISTS: 'ALREADY_EXISTS',

  // Rate limiting
  RATE_LIMITED: 'RATE_LIMITED',

  // Server errors
  INTERNAL_ERROR: 'INTERNAL_ERROR',
  SERVICE_UNAVAILABLE: 'SERVICE_UNAVAILABLE',
  BAD_GATEWAY: 'BAD_GATEWAY',
} as const;

/** API route path constants. */
export const API_ROUTES = {
  AUTH: {
    LOGIN: '/auth/login',
    REGISTER: '/auth/register',
    REFRESH: '/auth/refresh',
    LOGOUT: '/auth/logout',
    ME: '/auth/me',
  },
  HEALTH: {
    BASE: '/health',
    READY: '/health/ready',
    LIVE: '/health/live',
  },
  USERS: {
    BASE: '/users',
    BY_ID: '/users/:id',
  },
} as const;

/** Cache configuration constants. */
export const CACHE = {
  DEFAULT_TTL: 300,       // 5 minutes
  USER_TTL: 600,          // 10 minutes
  SESSION_TTL: 1800,      // 30 minutes
  CONFIG_TTL: 3600,       // 1 hour
  PREFIX: {
    USER: 'user:',
    SESSION: 'session:',
    CONFIG: 'config:',
    RATE_LIMIT: 'rate:',
  },
} as const;

/** Pagination defaults and limits. */
export const PAGINATION = {
  DEFAULT_PAGE: 1,
  DEFAULT_PAGE_SIZE: 20,
  MAX_PAGE_SIZE: 100,
  MIN_PAGE_SIZE: 1,
} as const;

/** Request header names used by the platform. */
export const HEADERS = {
  REQUEST_ID: 'x-request-id',
  CORRELATION_ID: 'x-correlation-id',
  API_VERSION: 'x-api-version',
  RATE_LIMIT_REMAINING: 'x-ratelimit-remaining',
  RATE_LIMIT_RESET: 'x-ratelimit-reset',
} as const;
