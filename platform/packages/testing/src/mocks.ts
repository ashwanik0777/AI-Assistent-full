/**
 * Creates a mock logger with no-op functions.
 * When vitest is available, methods are wrapped as vi.fn() stubs.
 */
export function mockLogger() {
  const noop = (): void => {};

  // Attempt to use vitest's vi.fn() for spying; fall back to no-ops
  let fn: () => (...args: unknown[]) => void;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { vi } = require('vitest') as typeof import('vitest');
    fn = () => vi.fn();
  } catch {
    fn = () => noop;
  }

  return {
    info: fn(),
    warn: fn(),
    error: fn(),
    debug: fn(),
  };
}

/**
 * Creates a basic mock configuration object for testing.
 */
export function mockConfig() {
  return {
    app: {
      name: 'aira-test',
      version: '1.5.0',
      port: 3000,
      env: 'test' as const,
      url: 'http://localhost:3000',
    },
    database: {
      url: 'postgresql://localhost:5432/aira_test',
    },
    auth: {
      jwtSecret: 'test-jwt-secret',
      jwtExpiresIn: '15m',
      refreshExpiresIn: '7d',
    },
  };
}
