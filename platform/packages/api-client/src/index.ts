// ─────────────────────────────────────────────────────────────
// @aira/api-client — Typed HTTP client for the AIRA API
// ─────────────────────────────────────────────────────────────

import type { ApiResponse, ApiError } from '@aira/types';

// ── Types ────────────────────────────────────────────────────

export interface ApiClientConfig {
  /** Base URL of the API (e.g. http://localhost:3001). */
  baseUrl: string;
  /** Default request timeout in milliseconds. */
  timeout?: number;
  /** Default headers to include on every request. */
  headers?: Record<string, string>;
  /** Called when a 401 response is received (e.g. to trigger logout). */
  onUnauthorized?: () => void;
}

export interface RequestOptions {
  headers?: Record<string, string>;
  params?: Record<string, string>;
  timeout?: number;
  signal?: AbortSignal;
}

// ── Client Class ─────────────────────────────────────────────

export class ApiClient {
  private readonly baseUrl: string;
  private readonly defaultTimeout: number;
  private readonly defaultHeaders: Record<string, string>;
  private readonly onUnauthorized?: () => void;
  private authToken: string | null = null;

  constructor(config: ApiClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, ''); // strip trailing slash
    this.defaultTimeout = config.timeout ?? 30_000;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(config.headers ?? {}),
    };
    this.onUnauthorized = config.onUnauthorized;
  }

  // ── Auth Token Management ────────────────────────────────

  /** Set the bearer token for authenticated requests. */
  setAuthToken(token: string): void {
    this.authToken = token;
  }

  /** Clear the current auth token. */
  clearAuthToken(): void {
    this.authToken = null;
  }

  // ── Public HTTP Methods ──────────────────────────────────

  async get<T>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>('GET', path, undefined, options);
  }

  async post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>('POST', path, body, options);
  }

  async put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>('PUT', path, body, options);
  }

  async patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>('PATCH', path, body, options);
  }

  async delete<T>(path: string, options?: RequestOptions): Promise<ApiResponse<T>> {
    return this.request<T>('DELETE', path, undefined, options);
  }

  // ── Private Request Handler ──────────────────────────────

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options?: RequestOptions,
  ): Promise<ApiResponse<T>> {
    const url = this.buildUrl(path, options?.params);
    const timeout = options?.timeout ?? this.defaultTimeout;

    // Timeout via AbortController
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    const signal = options?.signal
      ? AbortSignal.any([options.signal, controller.signal])
      : controller.signal;

    const headers: Record<string, string> = {
      ...this.defaultHeaders,
      ...(options?.headers ?? {}),
    };

    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }

    try {
      const response = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal,
      });

      clearTimeout(timeoutId);

      if (response.status === 401) {
        this.onUnauthorized?.();
      }

      if (!response.ok) {
        const errorBody = await response.json().catch(() => ({})) as Record<string, unknown>;
        const apiError: ApiError = {
          success: false,
          error: {
            code: (errorBody['code'] as string) ?? `HTTP_${response.status}`,
            message: (errorBody['message'] as string) ?? response.statusText,
            details: errorBody['details'] as Record<string, unknown> | undefined,
          },
          timestamp: new Date().toISOString(),
        };
        throw apiError;
      }

      // 204 No Content
      if (response.status === 204) {
        return {
          success: true,
          data: undefined as T,
          timestamp: new Date().toISOString(),
        };
      }

      const data = (await response.json()) as ApiResponse<T>;
      return data;
    } catch (error) {
      clearTimeout(timeoutId);

      // Re-throw ApiError as-is
      if (typeof error === 'object' && error !== null && 'success' in error) {
        throw error;
      }

      // AbortError → timeout
      if (error instanceof DOMException && error.name === 'AbortError') {
        const apiError: ApiError = {
          success: false,
          error: { code: 'TIMEOUT', message: `Request timed out after ${timeout}ms` },
          timestamp: new Date().toISOString(),
        };
        throw apiError;
      }

      // Network or unknown error
      const apiError: ApiError = {
        success: false,
        error: {
          code: 'NETWORK_ERROR',
          message: error instanceof Error ? error.message : 'Unknown network error',
        },
        timestamp: new Date().toISOString(),
      };
      throw apiError;
    }
  }

  private buildUrl(path: string, params?: Record<string, string>): string {
    const url = new URL(path, this.baseUrl);
    if (params) {
      for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
      }
    }
    return url.toString();
  }
}

// ── Factory ──────────────────────────────────────────────────

/** Create a configured ApiClient instance. */
export function createApiClient(config: ApiClientConfig): ApiClient {
  return new ApiClient(config);
}
