import { describe, it, expect } from 'vitest';
import { HealthController } from '../modules/health/health.controller';

describe('HealthController', () => {
  let controller: HealthController;

  beforeEach(() => {
    controller = new HealthController();
  });

  describe('health()', () => {
    it('should return status "ok"', () => {
      const result = controller.health();

      expect(result.status).toBe('ok');
    });

    it('should include a valid ISO timestamp', () => {
      const result = controller.health();

      expect(result.timestamp).toBeDefined();
      expect(() => new Date(result.timestamp)).not.toThrow();
    });

    it('should include version and uptime', () => {
      const result = controller.health();

      expect(result.version).toBeDefined();
      expect(typeof result.uptime).toBe('number');
    });
  });

  describe('readiness()', () => {
    it('should return status "ok"', () => {
      const result = controller.readiness();

      expect(result.status).toBe('ok');
      expect(result.timestamp).toBeDefined();
    });
  });

  describe('liveness()', () => {
    it('should return status "ok"', () => {
      const result = controller.liveness();

      expect(result.status).toBe('ok');
      expect(result.timestamp).toBeDefined();
    });
  });
});
