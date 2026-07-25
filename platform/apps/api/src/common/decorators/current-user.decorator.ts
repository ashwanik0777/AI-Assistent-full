import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { Request } from 'express';

/**
 * Represents the authenticated user object attached to the request.
 * Extend this interface as the auth system matures.
 */
export interface RequestUser {
  id: string;
  email: string;
  role: string;
}

/**
 * Parameter decorator that extracts the authenticated user from the
 * request object. Optionally accepts a property key to return a single
 * field.
 *
 * @example
 * ```ts
 * @Get('me')
 * getProfile(@CurrentUser() user: RequestUser) { ... }
 *
 * @Get('me/id')
 * getId(@CurrentUser('id') userId: string) { ... }
 * ```
 */
export const CurrentUser = createParamDecorator(
  (data: keyof RequestUser | undefined, ctx: ExecutionContext) => {
    const request = ctx.switchToHttp().getRequest<Request>();
    const user = (request as Request & { user?: RequestUser }).user;

    if (!user) {
      return undefined;
    }

    return data ? user[data] : user;
  },
);
