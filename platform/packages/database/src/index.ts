import { PrismaClient } from '@prisma/client';

// ── Singleton PrismaClient ──────────────────────────────────

let prismaInstance: PrismaClient | null = null;

/**
 * Returns a singleton PrismaClient instance.
 * Creates the client on first call and reuses it for subsequent calls.
 */
export function getPrismaClient(): PrismaClient {
  if (!prismaInstance) {
    prismaInstance = new PrismaClient({
      log:
        process.env.NODE_ENV === 'production'
          ? ['error']
          : ['query', 'info', 'warn', 'error'],
    });
  }
  return prismaInstance;
}

/**
 * Creates a new PrismaClient instance (useful for testing or
 * connecting to a different database).
 */
export function createPrismaClient(url?: string): PrismaClient {
  return new PrismaClient({
    datasourceUrl: url,
    log:
      process.env.NODE_ENV === 'production'
        ? ['error']
        : ['query', 'info', 'warn', 'error'],
  });
}

export { PrismaClient } from '@prisma/client';
export * from './repository.base.js';
