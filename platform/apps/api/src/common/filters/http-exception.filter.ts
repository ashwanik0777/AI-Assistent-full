import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpException,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';

/**
 * Catches all HttpException instances and returns a standardised ApiError
 * response body.
 */
@Catch(HttpException)
export class HttpExceptionFilter implements ExceptionFilter {
  private readonly logger = new Logger(HttpExceptionFilter.name);

  catch(exception: HttpException, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const request = ctx.getRequest<Request>();
    const response = ctx.getResponse<Response>();
    const status = exception.getStatus();
    const exceptionResponse = exception.getResponse();

    const message =
      typeof exceptionResponse === 'string'
        ? exceptionResponse
        : (exceptionResponse as Record<string, unknown>).message ?? exception.message;

    const errorBody = {
      success: false,
      error: {
        statusCode: status,
        message,
        error: exception.name,
        timestamp: new Date().toISOString(),
        path: request.url,
        method: request.method,
        requestId: (request.headers['x-request-id'] as string) ?? null,
      },
    };

    this.logger.warn(
      `${request.method} ${request.url} → ${status} ${exception.message}`,
    );

    response.status(status).json(errorBody);
  }
}
