import {
  ExceptionFilter,
  Catch,
  ArgumentsHost,
  HttpStatus,
  Logger,
} from '@nestjs/common';
import { Request, Response } from 'express';

/**
 * Catches any non-HTTP exception (unexpected errors) and returns a
 * generic 500 Internal Server Error with a standardised body.
 */
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  private readonly logger = new Logger(AllExceptionsFilter.name);

  catch(exception: unknown, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const request = ctx.getRequest<Request>();
    const response = ctx.getResponse<Response>();

    const status = HttpStatus.INTERNAL_SERVER_ERROR;

    const errorMessage =
      exception instanceof Error ? exception.message : 'Internal server error';

    const stack =
      exception instanceof Error ? exception.stack : undefined;

    this.logger.error(
      `Unhandled exception: ${errorMessage}`,
      stack,
    );

    const errorBody = {
      success: false,
      error: {
        statusCode: status,
        message: 'Internal server error',
        error: 'InternalServerError',
        timestamp: new Date().toISOString(),
        path: request.url,
        method: request.method,
        requestId: (request.headers['x-request-id'] as string) ?? null,
      },
    };

    response.status(status).json(errorBody);
  }
}
