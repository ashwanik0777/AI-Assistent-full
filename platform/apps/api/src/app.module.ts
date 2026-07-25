import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ThrottlerModule } from '@nestjs/throttler';
import { APP_GUARD } from '@nestjs/core';
import { ThrottlerGuard } from '@nestjs/throttler';

import { HealthModule } from './modules/health/health.module';
import { AuthModule } from './modules/auth/auth.module';

@Module({
  imports: [
    // ── Configuration (global) ──────────────────────────────
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env.local', '.env'],
      cache: true,
      expandVariables: true,
    }),

    // ── Rate Limiting ───────────────────────────────────────
    ThrottlerModule.forRoot([
      {
        name: 'short',
        ttl: 1_000,   // 1 second
        limit: 10,
      },
      {
        name: 'long',
        ttl: 60_000,  // 1 minute
        limit: 100,
      },
    ]),

    // ── Feature Modules ─────────────────────────────────────
    HealthModule,
    AuthModule,
  ],
  providers: [
    {
      provide: APP_GUARD,
      useClass: ThrottlerGuard,
    },
  ],
})
export class AppModule {}
