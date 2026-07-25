import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';
import { randomUUID } from 'node:crypto';

/**
 * Ensures every request carries unique `X-Request-ID` and `X-Correlation-ID`
 * headers. If the client provides them they are preserved; otherwise new UUIDs
 * are generated.
 */
@Injectable()
export class RequestIdMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction): void {
    const requestId =
      (req.headers['x-request-id'] as string) ?? randomUUID();
    const correlationId =
      (req.headers['x-correlation-id'] as string) ?? randomUUID();

    // Attach to request headers so downstream consumers can read them.
    req.headers['x-request-id'] = requestId;
    req.headers['x-correlation-id'] = correlationId;

    // Echo back in response headers for client-side tracing.
    res.setHeader('X-Request-ID', requestId);
    res.setHeader('X-Correlation-ID', correlationId);

    next();
  }
}
