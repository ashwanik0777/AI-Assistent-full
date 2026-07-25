// ─────────────────────────────────────────────────────────────
// @aira/security — JWT, hashing, and sanitisation helpers
// ─────────────────────────────────────────────────────────────

import { randomBytes, scrypt, timingSafeEqual } from 'node:crypto';
import { promisify } from 'node:util';

import * as jose from 'jose';

import type { JwtPayload } from '@aira/types';

const scryptAsync = promisify(scrypt);

// ── Password Hashing ─────────────────────────────────────────

const SALT_LENGTH = 32;
const KEY_LENGTH = 64;
const SEPARATOR = ':';

/**
 * Hash a password using Node.js crypto scrypt with a random salt.
 * Returns `salt:hash` as a hex-encoded string.
 */
export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(SALT_LENGTH).toString('hex');
  const derivedKey = (await scryptAsync(password, salt, KEY_LENGTH)) as Buffer;
  return `${salt}${SEPARATOR}${derivedKey.toString('hex')}`;
}

/**
 * Verify a password against a stored `salt:hash` string.
 * Uses timing-safe comparison to prevent timing attacks.
 */
export async function verifyPassword(password: string, storedHash: string): Promise<boolean> {
  const [salt, hash] = storedHash.split(SEPARATOR);
  if (!salt || !hash) return false;

  const derivedKey = (await scryptAsync(password, salt, KEY_LENGTH)) as Buffer;
  const storedKey = Buffer.from(hash, 'hex');

  if (derivedKey.length !== storedKey.length) return false;
  return timingSafeEqual(derivedKey, storedKey);
}

// ── JWT ──────────────────────────────────────────────────────

/**
 * Generate a signed JWT using the HS256 algorithm.
 *
 * @param payload - Claims to embed in the token
 * @param secret  - Signing secret (min 16 chars recommended)
 * @param expiresIn - Expiration string (e.g. '15m', '7d')
 */
export async function generateJwtToken(
  payload: Record<string, unknown>,
  secret: string,
  expiresIn: string,
): Promise<string> {
  const encodedSecret = new TextEncoder().encode(secret);

  return new jose.SignJWT(payload)
    .setProtectedHeader({ alg: 'HS256' })
    .setIssuedAt()
    .setExpirationTime(expiresIn)
    .sign(encodedSecret);
}

/**
 * Verify a JWT and return its payload.
 *
 * @throws {jose.errors.JWTExpired} if the token has expired
 * @throws {jose.errors.JWSSignatureVerificationFailed} if the signature is invalid
 */
export async function verifyJwtToken(token: string, secret: string): Promise<JwtPayload> {
  const encodedSecret = new TextEncoder().encode(secret);
  const { payload } = await jose.jwtVerify(token, encodedSecret);
  return payload as unknown as JwtPayload;
}

/**
 * Decode a JWT **without** verifying the signature.
 * Useful for reading claims from expired tokens during refresh flows.
 */
export function decodeJwtToken(token: string): JwtPayload {
  const payload = jose.decodeJwt(token);
  return payload as unknown as JwtPayload;
}

// ── HTML Sanitisation ────────────────────────────────────────

/**
 * Strip HTML tags from a string to prevent basic XSS.
 * For production use, consider a library like DOMPurify.
 */
export function sanitizeHtml(input: string): string {
  return input
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

// ── CSRF ─────────────────────────────────────────────────────

/** Generate a cryptographically secure CSRF token. */
export function generateCsrfToken(): string {
  return randomBytes(32).toString('hex');
}

// ── Security Headers ─────────────────────────────────────────

/** Recommended security response headers. */
export const SECURITY_HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '0', // Modern browsers handle this; header is deprecated
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
  'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'",
} as const;

// ── Rate Limiting Types ──────────────────────────────────────

export interface RateLimitConfig {
  windowMs: number;
  maxRequests: number;
  message?: string;
}

export const DEFAULT_RATE_LIMIT: RateLimitConfig = {
  windowMs: 15 * 60 * 1000, // 15 minutes
  maxRequests: 100,
  message: 'Too many requests, please try again later.',
};
