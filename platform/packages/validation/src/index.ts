// ─────────────────────────────────────────────────────────────
// @aira/validation — Zod-based validation schemas and helpers
// ─────────────────────────────────────────────────────────────

import { z } from 'zod';
import type { ZodSchema, ZodError } from 'zod';

// ── Common Field Validators ─────────────────────────────────

export const emailSchema = z
  .string()
  .email('Invalid email address')
  .min(5, 'Email too short')
  .max(255, 'Email too long')
  .toLowerCase()
  .trim();

export const uuidSchema = z.string().uuid('Invalid UUID format');

export const urlSchema = z.string().url('Invalid URL format');

export const passwordSchema = z
  .string()
  .min(8, 'Password must be at least 8 characters')
  .max(128, 'Password must be at most 128 characters')
  .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
  .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
  .regex(/[0-9]/, 'Password must contain at least one number');

export const nameSchema = z
  .string()
  .min(1, 'Name is required')
  .max(100, 'Name too long')
  .trim();

// ── Pagination ───────────────────────────────────────────────

export const paginationSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
});

export const sortSchema = z.object({
  field: z.string().min(1),
  direction: z.enum(['asc', 'desc']).default('asc'),
});

// ── Auth Schemas ─────────────────────────────────────────────

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Password is required'),
});

export const registerSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
  firstName: nameSchema,
  lastName: nameSchema,
});

export const tokenRefreshSchema = z.object({
  refreshToken: z.string().min(1, 'Refresh token is required'),
});

// ── Environment Schema ───────────────────────────────────────

export const envSchema = z.enum(['development', 'test', 'staging', 'production']);

// ── Inferred Types ───────────────────────────────────────────

export type LoginInput = z.infer<typeof loginSchema>;
export type RegisterInput = z.infer<typeof registerSchema>;
export type TokenRefreshInput = z.infer<typeof tokenRefreshSchema>;
export type PaginationInput = z.infer<typeof paginationSchema>;
export type SortInput = z.infer<typeof sortSchema>;

// ── Validator Factory ────────────────────────────────────────

export interface Validator<T> {
  parse: (data: unknown) => T;
  safeParse: (data: unknown) => { success: true; data: T } | { success: false; errors: Record<string, string[]> };
  isValid: (data: unknown) => boolean;
}

/**
 * Create a reusable validator wrapper around a Zod schema.
 *
 * @example
 * const validateLogin = createValidator(loginSchema);
 * const result = validateLogin.safeParse(body);
 */
export function createValidator<T>(schema: ZodSchema<T>): Validator<T> {
  return {
    parse(data: unknown): T {
      return schema.parse(data);
    },

    safeParse(data: unknown) {
      const result = schema.safeParse(data);
      if (result.success) {
        return { success: true as const, data: result.data };
      }
      return { success: false as const, errors: formatZodErrors(result.error) };
    },

    isValid(data: unknown): boolean {
      return schema.safeParse(data).success;
    },
  };
}

// ── Error Formatting ─────────────────────────────────────────

/**
 * Format a ZodError into a field-keyed record of error message arrays.
 *
 * @example
 * // { email: ['Invalid email address'], password: ['Password too short'] }
 */
export function formatZodErrors(error: ZodError): Record<string, string[]> {
  const formatted: Record<string, string[]> = {};

  for (const issue of error.issues) {
    const path = issue.path.join('.') || '_root';
    if (!formatted[path]) {
      formatted[path] = [];
    }
    formatted[path].push(issue.message);
  }

  return formatted;
}

// Re-export zod for convenience
export { z } from 'zod';
