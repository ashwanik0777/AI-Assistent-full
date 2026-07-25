// ─────────────────────────────────────────────────────────────
// @aira/utils — Common utility functions
// ─────────────────────────────────────────────────────────────

import { randomUUID } from 'node:crypto';
import { nanoid } from 'nanoid';

// ── ID Generation ────────────────────────────────────────────

/** Generate a short, URL-safe unique ID (nanoid). */
export function generateId(size = 21): string {
  return nanoid(size);
}

/** Generate a standard UUID v4. */
export function generateUUID(): string {
  return randomUUID();
}

// ── Async Helpers ────────────────────────────────────────────

/** Sleep for the specified number of milliseconds. */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface RetryOptions {
  maxRetries: number;
  delay: number;
  backoff?: number;
  onRetry?: (error: unknown, attempt: number) => void;
}

/**
 * Retry an async function with exponential backoff.
 *
 * @example
 * const data = await retry(() => fetchData(), { maxRetries: 3, delay: 1000, backoff: 2 });
 */
export async function retry<T>(
  fn: () => Promise<T>,
  options: RetryOptions,
): Promise<T> {
  const { maxRetries, delay, backoff = 2, onRetry } = options;
  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < maxRetries) {
        onRetry?.(error, attempt + 1);
        await sleep(delay * Math.pow(backoff, attempt));
      }
    }
  }

  throw lastError;
}

// ── Object Utilities ─────────────────────────────────────────

/** Deep merge two objects. Source properties override target. */
export function deepMerge<T extends Record<string, unknown>>(
  target: T,
  source: Partial<T>,
): T {
  const result = { ...target };

  for (const key of Object.keys(source) as Array<keyof T>) {
    const sourceVal = source[key];
    const targetVal = result[key];

    if (
      sourceVal !== null &&
      typeof sourceVal === 'object' &&
      !Array.isArray(sourceVal) &&
      targetVal !== null &&
      typeof targetVal === 'object' &&
      !Array.isArray(targetVal)
    ) {
      result[key] = deepMerge(
        targetVal as Record<string, unknown>,
        sourceVal as Record<string, unknown>,
      ) as T[keyof T];
    } else {
      result[key] = sourceVal as T[keyof T];
    }
  }

  return result;
}

/** Deep clone an object using structuredClone. */
export function deepClone<T>(obj: T): T {
  return structuredClone(obj);
}

/** Pick specified keys from an object. */
export function pick<T extends Record<string, unknown>, K extends keyof T>(
  obj: T,
  keys: K[],
): Pick<T, K> {
  const result = {} as Pick<T, K>;
  for (const key of keys) {
    if (key in obj) {
      result[key] = obj[key];
    }
  }
  return result;
}

/** Omit specified keys from an object. */
export function omit<T extends Record<string, unknown>, K extends keyof T>(
  obj: T,
  keys: K[],
): Omit<T, K> {
  const result = { ...obj };
  for (const key of keys) {
    delete result[key];
  }
  return result as Omit<T, K>;
}

/** Group an array by a key function. */
export function groupBy<T>(
  array: T[],
  keyFn: (item: T) => string,
): Record<string, T[]> {
  const result: Record<string, T[]> = {};
  for (const item of array) {
    const key = keyFn(item);
    if (!result[key]) {
      result[key] = [];
    }
    result[key].push(item);
  }
  return result;
}

// ── String Utilities ─────────────────────────────────────────

/** Convert a string to a URL-friendly slug. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

/** Truncate a string to the specified length with an optional suffix. */
export function truncate(text: string, maxLength: number, suffix = '...'): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - suffix.length) + suffix;
}

/** Capitalize the first letter of a string. */
export function capitalize(text: string): string {
  if (text.length === 0) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// ── Type Guards ──────────────────────────────────────────────

/** Check if a value is not null and not undefined. */
export function isDefined<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

/** Check if a value is null or undefined. */
export function isNil(value: unknown): value is null | undefined {
  return value === null || value === undefined;
}

/** Check if a value is empty (null, undefined, empty string, empty array, empty object). */
export function isEmpty(value: unknown): boolean {
  if (isNil(value)) return true;
  if (typeof value === 'string') return value.trim().length === 0;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
}

// ── Hashing ──────────────────────────────────────────────────

/** Simple non-cryptographic string hash (FNV-1a). Useful for cache keys. */
export function hashString(str: string): string {
  let hash = 0x811c9dc5; // FNV offset basis
  for (let i = 0; i < str.length; i++) {
    hash ^= str.charCodeAt(i);
    hash = (hash * 0x01000193) >>> 0; // FNV prime, unsigned
  }
  return hash.toString(36);
}

// ── Timing ───────────────────────────────────────────────────

export interface Timer {
  /** Get elapsed time in milliseconds since the timer was created. */
  elapsed: () => number;
}

/** Create a high-resolution timer. */
export function createTimer(): Timer {
  const start = performance.now();
  return {
    elapsed: () => Math.round(performance.now() - start),
  };
}
