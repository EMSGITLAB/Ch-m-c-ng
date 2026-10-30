import assert from 'node:assert/strict';
import test from 'node:test';
import { localDateISO } from '../src/dates.ts';

test('Vietnam date follows local midnight rather than server UTC date', () => {
  assert.equal(localDateISO(new Date('2026-10-28T18:00:00Z')), '2026-10-29');
  assert.equal(localDateISO(new Date('2026-10-28T16:59:59Z')), '2026-10-28');
});
test('year boundary uses the selected business timezone', () => {
  assert.equal(localDateISO(new Date('2026-12-31T23:00:00Z')), '2027-01-01');
  assert.equal(localDateISO(new Date('2026-12-31T23:00:00Z'), 'UTC'), '2026-12-31');
});
