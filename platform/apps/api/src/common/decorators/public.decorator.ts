import { SetMetadata } from '@nestjs/common';

/**
 * Metadata key used by the JwtAuthGuard to identify public routes that
 * should bypass authentication.
 */
export const IS_PUBLIC_KEY = 'isPublic';

/**
 * Marks a route handler or controller as publicly accessible — no
 * authentication required.
 *
 * @example
 * ```ts
 * @Public()
 * @Get('health')
 * health() { return 'ok'; }
 * ```
 */
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);
