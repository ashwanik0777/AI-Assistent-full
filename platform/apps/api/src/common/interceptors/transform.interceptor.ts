import {
  Injectable,
  NestInterceptor,
  ExecutionContext,
  CallHandler,
} from '@nestjs/common';
import { Observable, map } from 'rxjs';

/**
 * Standardised API response envelope.
 */
export interface ApiResponse<T> {
  success: true;
  data: T;
  meta: {
    timestamp: string;
  };
}

/**
 * Wraps every successful response in the standard `ApiResponse` envelope.
 */
@Injectable()
export class TransformInterceptor<T>
  implements NestInterceptor<T, ApiResponse<T>>
{
  intercept(
    _context: ExecutionContext,
    next: CallHandler<T>,
  ): Observable<ApiResponse<T>> {
    return next.handle().pipe(
      map((data) => ({
        success: true as const,
        data,
        meta: {
          timestamp: new Date().toISOString(),
        },
      })),
    );
  }
}
