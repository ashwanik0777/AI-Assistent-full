import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
  Logger,
} from '@nestjs/common';
import { Observable, tap } from 'rxjs';
import { Request } from 'express';

/**
 * Logs incoming HTTP requests and their response duration.
 */
@Injectable()
export class LoggingInterceptor implements NestInterceptor {
  private readonly logger = new Logger(LoggingInterceptor.name);

  intercept(context: ExecutionContext, next: CallHandler): Observable<unknown> {
    const request = context.switchToHttp().getRequest<Request>();
    const { method, url } = request;
    const requestId = (request.headers['x-request-id'] as string) ?? '-';
    const startTime = Date.now();

    this.logger.log(`→  ${method} ${url}  [${requestId}]`);

    return next.handle().pipe(
      tap({
        next: () => {
          const duration = Date.now() - startTime;
          this.logger.log(`←  ${method} ${url}  ${duration}ms  [${requestId}]`);
        },
        error: (error: Error) => {
          const duration = Date.now() - startTime;
          this.logger.warn(
            `←  ${method} ${url}  ${duration}ms  ERROR: ${error.message}  [${requestId}]`,
          );
        },
      }),
    );
  }
}
