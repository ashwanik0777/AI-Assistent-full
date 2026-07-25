// ─────────────────────────────────────────────────────────────
// @aira/logger — Structured logging with pino
// ─────────────────────────────────────────────────────────────

import pino from 'pino';
import type { Logger } from 'pino';

// ── Types ────────────────────────────────────────────────────

export interface LogContext {
  requestId?: string;
  correlationId?: string;
  userId?: string;
  service?: string;
  [key: string]: unknown;
}

export interface LoggerOptions {
  /** Logger name (usually service or package name). */
  name: string;
  /** Minimum log level. Defaults to 'info'. */
  level?: string;
  /** Enable pretty printing (development mode). Defaults to false. */
  pretty?: boolean;
}

// ── Sensitive Field Redaction ────────────────────────────────

const REDACTED_PATHS = [
  'password',
  'passwordHash',
  'token',
  'accessToken',
  'refreshToken',
  'secret',
  'authorization',
  'cookie',
  'jwtSecret',
  'apiKey',
];

// ── Logger Factory ───────────────────────────────────────────

/**
 * Create a configured pino logger instance.
 *
 * @example
 * const logger = createLogger({ name: 'api', level: 'debug', pretty: true });
 * logger.info({ userId: '123' }, 'User logged in');
 */
export function createLogger(options: LoggerOptions): Logger {
  const { name, level = 'info', pretty = false } = options;

  const pinoOptions: pino.LoggerOptions = {
    name,
    level,
    redact: {
      paths: REDACTED_PATHS,
      censor: '[REDACTED]',
    },
    serializers: {
      err: pino.stdSerializers.err,
      req: pino.stdSerializers.req,
      res: pino.stdSerializers.res,
    },
    timestamp: pino.stdTimeFunctions.isoTime,
  };

  if (pretty) {
    return pino(pinoOptions, pino.transport({
      target: 'pino-pretty',
      options: {
        colorize: true,
        translateTime: 'SYS:standard',
        ignore: 'pid,hostname',
      },
    }));
  }

  return pino(pinoOptions);
}

// ── Child Logger ─────────────────────────────────────────────

/**
 * Create a child logger with additional context bindings.
 *
 * @example
 * const reqLogger = createChildLogger(logger, { requestId: 'abc-123', userId: 'u1' });
 */
export function createChildLogger(parent: Logger, context: LogContext): Logger {
  return parent.child(context);
}

// ── Request Logger Middleware Helper ─────────────────────────

export interface RequestLogInfo {
  method: string;
  url: string;
  statusCode: number;
  duration: number;
  requestId?: string;
}

/**
 * Create a request logging function that can be called from Express-style middleware.
 *
 * @example
 * const logRequest = createRequestLogger(logger);
 * logRequest({ method: 'GET', url: '/health', statusCode: 200, duration: 12 });
 */
export function createRequestLogger(logger: Logger): (info: RequestLogInfo) => void {
  return (info: RequestLogInfo) => {
    const { method, url, statusCode, duration, requestId } = info;

    const logData = {
      method,
      url,
      statusCode,
      duration: `${duration}ms`,
      ...(requestId ? { requestId } : {}),
    };

    if (statusCode >= 500) {
      logger.error(logData, `${method} ${url} ${statusCode} ${duration}ms`);
    } else if (statusCode >= 400) {
      logger.warn(logData, `${method} ${url} ${statusCode} ${duration}ms`);
    } else {
      logger.info(logData, `${method} ${url} ${statusCode} ${duration}ms`);
    }
  };
}

// Re-export pino types for convenience
export type { Logger } from 'pino';
