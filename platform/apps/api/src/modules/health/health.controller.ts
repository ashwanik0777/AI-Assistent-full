import { Controller, Get } from '@nestjs/common';
import { Public } from '../../common/decorators/public.decorator';

@Controller('health')
export class HealthController {
  /**
   * General health check — returns service status, version, and uptime.
   */
  @Public()
  @Get()
  health() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
      version: process.env.APP_VERSION || '1.5.0',
      uptime: process.uptime(),
    };
  }

  /**
   * Readiness probe — indicates whether the service is ready to accept traffic.
   */
  @Public()
  @Get('ready')
  readiness() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
    };
  }

  /**
   * Liveness probe — indicates whether the service process is alive.
   */
  @Public()
  @Get('live')
  liveness() {
    return {
      status: 'ok',
      timestamp: new Date().toISOString(),
    };
  }
}
