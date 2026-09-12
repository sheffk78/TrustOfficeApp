/**
 * 2026-09-11 demo-remnant fix — stale active-trust selection contract.
 *
 * Bug: after demo data was deleted (or cleaned server-side on first real
 * trust), the sidebar trust dropdown kept showing "Smith Family Trust" as
 * the ACTIVE trust because AuthContext never validated selectedTrust against
 * the fresh GET /trusts response.
 *
 * Contract being tested (AuthContext.useTrustsLoader):
 *  1. A selection not present in the fresh list is cleared, never rendered.
 *  2. Fallback order: stored trust_id (still valid) → first real trust →
 *     first trust (demo-only accounts still need a selection).
 *  3. A demo trust is never chosen while a real trust exists in the list.
 *
 * The selection logic lives in an inline block of loadTrustsInternal; we
 * verify the contract via source assertions (same pattern as
 * test_demo_leak_and_multi_property_minutes.py) plus a pure-function
 * extraction that mirrors the production code path.
 */

import fs from 'fs';
import path from 'path';

const __dirname = path.join(process.cwd(), 'src', 'tests');
const authCtxPath = path.join(__dirname, '..', 'context', 'AuthContext.js');
const authCtxSource = fs.readFileSync(authCtxPath, 'utf8');

describe('stale trust selection reconciliation (demo-remnant fix)', () => {
  const logicStart = authCtxSource.indexOf('Reconcile selection against the fresh list');
  const logicEnd = authCtxSource.indexOf("} else {", logicStart);
  const logicSrc = logicStart !== -1 && logicEnd > logicStart
    ? authCtxSource.slice(logicStart, logicEnd)
    : '';

  it('contains the reconciliation block in useTrustsLoader', () => {
    expect(logicStart).toBeGreaterThan(-1);
    expect(logicEnd).toBeGreaterThan(logicStart);
  });

  it('validates the current selection against the fresh trust list', () => {
    expect(logicSrc).toContain('isSelectedValid');
    expect(logicSrc).toContain("data.some(t => t.trust_id === selectedTrust.trust_id)");
  });

  it('clears stale selections that no longer exist in the list', () => {
    expect(logicSrc).toContain("setSelectedTrust(null)");
    expect(logicSrc).toContain("localStorage.removeItem('selected_trust_id')");
  });

  it('prefers the first REAL trust over the first trust in the fallback', () => {
    // The fallback must skip demo trusts when any real trust exists.
    expect(logicSrc).toContain("data.find(t => t.is_demo !== true");
    expect(logicSrc).toContain("storedTrust || firstReal || data[0]");
  });

  it('still honors forceSelectNew (trust creation flows)', () => {
    expect(logicSrc).toContain('forceSelectNew');
  });

  // Pure extraction of the decision the loader must make — the production
  // code path reduced to a function so we can assert actual behavior.
  describe('decision behavior', () => {
    const reconcile = (freshList, currentSelection, storedId) => {
      let selected = currentSelection;
      let removedStored = false;
      const data = freshList;
      const isSelectedValid = selected && data.some(t => t.trust_id === selected.trust_id);
      if (!isSelectedValid) {
        if (selected) {
          selected = null;
          removedStored = true;
        }
        if (data.length > 0) {
          const storedTrust = data.find(t => t.trust_id === storedId);
          const firstReal = data.find(t => t.is_demo !== true && t.isDemo !== true);
          selected = storedTrust || firstReal || data[0];
          removedStored = removedStored && false;
        }
      }
      return { selected, removedStored };
    };

    it('drops a demo trust selection after demo data was deleted (real trust present)', () => {
      const smith = { trust_id: 'demo_smith', name: 'Smith Family Trust', is_demo: true };
      const kratt = { trust_id: 'real_kratt', name: 'Kratt Family Estate' };
      const result = reconcile([kratt], smith, 'demo_smith');
      expect(result.selected.trust_id).toBe('real_kratt');
      expect(result.selected.name).toBe('Kratt Family Estate');
    });

    it('never defaults to a demo trust when a real trust exists', () => {
      const smith = { trust_id: 'demo_smith', name: 'Smith Family Trust', is_demo: true };
      const holdings = { trust_id: 'real_holdings', name: 'Renovated Earth Holdings' };
      const result = reconcile([holdings, smith], null, null);
      expect(result.selected.trust_id).toBe('real_holdings');
    });

    it('keeps a valid real selection untouched', () => {
      const kratt = { trust_id: 'real_kratt', name: 'Kratt Family Estate' };
      const result = reconcile([kratt], kratt, 'real_kratt');
      expect(result.selected).toBe(kratt);
    });

    it('demo-only accounts still get a selection (demo experience)', () => {
      const smith = { trust_id: 'demo_smith', name: 'Smith Family Trust', is_demo: true };
      const result = reconcile([smith], null, null);
      expect(result.selected.trust_id).toBe('demo_smith');
    });
  });
});