// @vitest-environment node
import { describe, expect, it } from 'vitest';

import {
  getPreReceiveGuardRanges,
  parsePreReceiveUpdates,
} from './server-perimeter-guard.mjs';

const ZERO_SHA1 = '0'.repeat(40);
const OLD_SHA1 = '1'.repeat(40);
const NEW_SHA1 = '2'.repeat(40);

describe('server-side Git perimeter guard', () => {
  it('checks every updated branch and skips only a branch deletion', () => {
    const updates = parsePreReceiveUpdates([
      `${OLD_SHA1} ${NEW_SHA1} refs/heads/feature/data-layer`,
      `${ZERO_SHA1} ${NEW_SHA1} refs/heads/new-branch`,
      `${OLD_SHA1} ${ZERO_SHA1} refs/heads/obsolete`,
    ].join('\n'));

    expect(getPreReceiveGuardRanges(updates)).toEqual([
      `${OLD_SHA1}..${NEW_SHA1}`,
      NEW_SHA1,
    ]);
  });

  it('rejects tags and malformed receive input instead of leaving unscanned refs', () => {
    expect(() => parsePreReceiveUpdates(`${OLD_SHA1} ${NEW_SHA1} refs/tags/v1`)).not.toThrow();
    expect(() => getPreReceiveGuardRanges(parsePreReceiveUpdates(`${OLD_SHA1} ${NEW_SHA1} refs/tags/v1`)))
      .toThrow(/ветки/i);
    expect(() => parsePreReceiveUpdates('not a receive update')).toThrow(/некоррект/i);
  });
});
