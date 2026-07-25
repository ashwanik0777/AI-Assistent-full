// ─────────────────────────────────────────────────────────────
// @aira/config — Environment management & feature flags
// ─────────────────────────────────────────────────────────────

import { config as loadDotenv } from 'dotenv';
import { z } from 'zod';

// Load .env on import (idempotent)
loadDotenv();

// ── Configuration Schemas ────────────────────────────────────

export const AppConfigSchema = z.object({
  name: z.string().default('aira-platform'),
  version: z.string().default('1.5.0'),
  port: z.coerce.number().int().min(1).max(65535).default(3001),
  env: z.enum(['development', 'test', 'staging', 'production']).default('development'),
  url: z.string().url().default('http://localhost:3001'),
});

export const DatabaseConfigSchema = z.object({
  url: z.string().min(1, 'DATABASE_URL is required'),
  poolMin: z.coerce.number().int().min(0).default(2),
  poolMax: z.coerce.number().int().min(1).default(10),
});

export const RedisConfigSchema = z.object({
  url: z.string().default('redis://localhost:6379'),
});

export const AuthConfigSchema = z.object({
  jwtSecret: z.string().min(16, 'JWT_SECRET must be at least 16 characters'),
  accessExpiry: z.string().default('15m'),
  refreshExpiry: z.string().default('7d'),
});

export const LogConfigSchema = z.object({
  level: z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal']).default('info'),
  format: z.enum(['json', 'pretty']).default('pretty'),
});

export const PlatformConfigSchema = z.object({
  app: AppConfigSchema,
  database: DatabaseConfigSchema,
  redis: RedisConfigSchema,
  auth: AuthConfigSchema,
  log: LogConfigSchema,
});

// ── Inferred Types ───────────────────────────────────────────

export type AppConfig = z.infer<typeof AppConfigSchema>;
export type DatabaseConfig = z.infer<typeof DatabaseConfigSchema>;
export type RedisConfig = z.infer<typeof RedisConfigSchema>;
export type AuthConfig = z.infer<typeof AuthConfigSchema>;
export type LogConfig = z.infer<typeof LogConfigSchema>;
export type PlatformConfig = z.infer<typeof PlatformConfigSchema>;

// ── Config Loader ────────────────────────────────────────────

/**
 * Load and validate the full platform configuration from environment variables.
 *
 * @throws {ZodError} if required environment variables are missing or invalid
 */
export function loadConfig(): PlatformConfig {
  const env = process.env;

  return PlatformConfigSchema.parse({
    app: {
      name: env['APP_NAME'],
      version: env['APP_VERSION'],
      port: env['APP_PORT'],
      env: env['NODE_ENV'],
      url: env['APP_URL'],
    },
    database: {
      url: env['DATABASE_URL'],
      poolMin: env['DB_POOL_MIN'],
      poolMax: env['DB_POOL_MAX'],
    },
    redis: {
      url: env['REDIS_URL'],
    },
    auth: {
      jwtSecret: env['JWT_SECRET'],
      accessExpiry: env['JWT_ACCESS_EXPIRY'],
      refreshExpiry: env['JWT_REFRESH_EXPIRY'],
    },
    log: {
      level: env['LOG_LEVEL'],
      format: env['LOG_FORMAT'],
    },
  });
}

// ── Feature Flags ────────────────────────────────────────────

/**
 * Manages feature flags read from environment variables.
 * Any env var prefixed with `FEATURE_FLAG_` is treated as a boolean flag.
 *
 * @example
 * const flags = new FeatureFlagManager();
 * flags.isEnabled('DARK_MODE'); // reads FEATURE_FLAG_DARK_MODE
 */
export class FeatureFlagManager {
  private readonly flags: Map<string, boolean>;

  constructor() {
    this.flags = new Map();
    this.loadFromEnv();
  }

  /** Reload all feature flags from the current environment. */
  loadFromEnv(): void {
    this.flags.clear();
    for (const [key, value] of Object.entries(process.env)) {
      if (key.startsWith('FEATURE_FLAG_')) {
        const flagName = key.replace('FEATURE_FLAG_', '');
        this.flags.set(flagName, value === 'true' || value === '1');
      }
    }
  }

  /** Check if a feature flag is enabled. */
  isEnabled(flag: string): boolean {
    return this.flags.get(flag) ?? false;
  }

  /** Get all registered feature flags. */
  getAll(): Record<string, boolean> {
    return Object.fromEntries(this.flags);
  }
}

// ── Factory ──────────────────────────────────────────────────

let cachedConfig: PlatformConfig | null = null;
let cachedFlags: FeatureFlagManager | null = null;

/** Create or return the cached platform configuration. */
export function createConfig(): PlatformConfig {
  if (!cachedConfig) {
    cachedConfig = loadConfig();
  }
  return cachedConfig;
}

/** Create or return the cached feature flag manager. */
export function createFeatureFlags(): FeatureFlagManager {
  if (!cachedFlags) {
    cachedFlags = new FeatureFlagManager();
  }
  return cachedFlags;
}

/** Reset cached config (useful in tests). */
export function resetConfig(): void {
  cachedConfig = null;
  cachedFlags = null;
}
