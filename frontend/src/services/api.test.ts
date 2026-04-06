import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildApiUrl } from './api';

describe('buildApiUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('keeps proxied production paths from duplicating the /api prefix', () => {
    vi.stubEnv('VITE_API_URL', '/api');
    expect(buildApiUrl('/api/v1/signals/latest')).toBe('/api/v1/signals/latest');
  });

  it('appends normal relative paths to the configured base URL', () => {
    vi.stubEnv('VITE_API_URL', '/api');
    expect(buildApiUrl('/health')).toBe('/api/health');
  });

  it('uses the dev host when VITE_API_URL points at localhost', () => {
    vi.stubEnv('VITE_API_URL', 'http://localhost:8000');
    expect(buildApiUrl('/api/v1/signals/latest')).toBe('http://localhost:8000/api/v1/signals/latest');
  });
});
