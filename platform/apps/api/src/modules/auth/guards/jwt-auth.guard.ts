import { Injectable, CanActivate, ExecutionContext } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { IS_PUBLIC_KEY } from '../../../common/decorators/public.decorator';

/**
 * JWT authentication guard.
 *
 * Checks the IS_PUBLIC_KEY metadata — if a route is marked @Public(),
 * the guard allows the request through without authentication.
 *
 * For non-public routes this is currently a placeholder that always
 * returns true; actual JWT verification will be added later.
 */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC_KEY, [
      context.getHandler(),
      context.getClass(),
    ]);

    if (isPublic) {
      return true;
    }

    // TODO: Implement actual JWT token verification
    return true;
  }
}
