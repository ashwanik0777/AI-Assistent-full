import type { AuthUser, ApiResponse, PaginatedResponse } from '@aira/types';

/**
 * Creates a mock AuthUser with sensible defaults.
 * Any field can be overridden via the `overrides` parameter.
 */
export function createMockUser(overrides?: Partial<AuthUser>): AuthUser {
  return {
    id: 'usr_test_00000000-0000-0000-0000-000000000001',
    email: 'test@aira.dev',
    role: 'USER',
    firstName: 'Test',
    lastName: 'User',
    ...overrides,
  };
}

/**
 * Wraps data in a standard ApiResponse envelope.
 */
export function createMockApiResponse<T>(data: T): ApiResponse<T> {
  return {
    success: true,
    data,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Wraps an array of items in a PaginatedResponse envelope.
 */
export function createMockPaginatedResponse<T>(
  data: T[],
  total?: number,
): PaginatedResponse<T> {
  const resolvedTotal = total ?? data.length;

  return {
    success: true,
    data,
    pagination: {
      page: 1,
      pageSize: data.length,
      total: resolvedTotal,
      totalPages: Math.ceil(resolvedTotal / Math.max(data.length, 1)),
      hasNext: false,
      hasPrevious: false,
    },
    timestamp: new Date().toISOString(),
  };
}
