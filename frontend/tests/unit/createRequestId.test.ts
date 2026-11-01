import { afterEach, describe, expect, it, vi } from 'vitest';
import { createRequestId } from '@/shared/requests/createRequestId';

describe('request IDs', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('uses the native UUID generator when available', () => {
    const id = '7ec48cf0-1632-4f3d-9ed3-68dc71af4429';
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(id);
    expect(createRequestId()).toBe(id);
  });

  it('generates distinct UUIDv4 IDs with secure random bytes on HTTP', () => {
    let sequence = 0;
    vi.stubGlobal('crypto', {
      getRandomValues: vi.fn((bytes: Uint8Array) => {
        bytes.fill(++sequence);
        return bytes;
      }),
    });
    const first = createRequestId();
    const second = createRequestId();
    expect(first).toBe('01010101-0101-4101-8101-010101010101');
    expect(second).toBe('02020202-0202-4202-8202-020202020202');
    expect(first).not.toBe(second);
  });

  it('replaces the random version and variant bits', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => bytes.fill(0xff),
    });

    expect(createRequestId()).toBe('ffffffff-ffff-4fff-bfff-ffffffffffff');
  });
});
