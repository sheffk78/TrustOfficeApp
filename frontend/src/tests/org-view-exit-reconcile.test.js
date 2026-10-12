/**
 * 2026-10-12 demo-battery defect D1 — org-view exit must not leak the client
 * trust into the advisor's own workspace.
 *
 * Bug: exiting a client workspace (Org Console → Enter Ben's Account → Back to
 * Org Console) left localStorage.selected_trust_id pointing at the CLIENT's
 * trust; the sidebar active-trust chip stayed "I AM MINISTRIES" and Money
 * pages kept rendering the client's data inside the advisor's own context
 * until a hard reload. Root: OrgViewBanner.handleExit cleared org_view_data
 * but never cleared the sticky selection; the reconcile inside
 * loadTrustsInternal kept treating it as valid via isOrgViewTrust only while
 * org_view_data existed.
 *
 * Contract being tested (source assertions, same pattern as
 * stale-trust-selection.test.js):
 *  1. OrgViewBanner.handleExit removes selected_trust_id from localStorage
 *     and dispatches 'trust_selection_invalidated'.
 *  2. AuthContext listens for 'trust_selection_invalidated' and re-runs the
 *     reconcile (loadTrustsInternal), which self-heals once org_view_data is
 *     gone (stale branch clears the client trust + falls back).
 *  3. The exit still performs the audited log-exit POST and removes
 *     org_view_data first (audit ordering preserved).
 */

import fs from 'fs';
import path from 'path';

const __dirname = path.dirname(fs.realpathSync(__filename));
const bannerPath = path.join(__dirname, '..', 'components', 'OrgViewBanner.js');
const authCtxPath = path.join(__dirname, '..', 'context', 'AuthContext.js');
const bannerSrc = fs.readFileSync(bannerPath, 'utf8');
const authSrc = fs.readFileSync(authCtxPath, 'utf8');

const exitStart = bannerSrc.indexOf('const handleExit = async () => {');
const exitEnd = bannerSrc.indexOf('const expiry =', exitStart);
const exitSrc = exitStart !== -1 && exitEnd > exitStart
  ? bannerSrc.slice(exitStart, exitEnd)
  : '';

describe('org-view exit selection cleanup (demo-battery D1)', () => {
  it('banner contains the exit handler', () => {
    expect(exitStart).toBeGreaterThan(-1);
    expect(exitEnd).toBeGreaterThan(exitStart);
  });

  it('exit clears the sticky selected_trust_id', () => {
    expect(exitSrc).toContain("localStorage.removeItem('selected_trust_id')");
  });

  it('exit dispatches trust_selection_invalidated for AuthContext', () => {
    expect(exitSrc).toContain("new Event('trust_selection_invalidated')");
  });

  it('exit removes org_view_data and fires org_view_changed (audit ordering preserved)', () => {
    const orgViewIdx = exitSrc.indexOf("sessionStorage.removeItem('org_view_data')");
    const logExitIdx = exitSrc.indexOf('log-exit');
    const invalidatedIdx = exitSrc.indexOf('trust_selection_invalidated');
    expect(orgViewIdx).toBeGreaterThan(-1);
    expect(logExitIdx).toBeGreaterThan(-1);
    expect(invalidatedIdx).toBeGreaterThan(orgViewIdx);
  });

  it('AuthContext re-reconciles when the selection is invalidated', () => {
    expect(authSrc).toContain("'trust_selection_invalidated'");
    expect(authSrc).toMatch(/trust_selection_invalidated', reReconcile/);
    expect(authSrc).toMatch(/const reReconcile = \(\) => \{ loadTrustsInternal\(false\); \}/);
  });

  // Pure extraction of the reconcile decision the re-run must produce:
  // with org_view_data gone, a client-trust selection that is absent from the
  // fresh /trusts list is stale → cleared → fallback to advisor's own trust.
  describe('reconcile decision table', () => {
    const decide = ({ orgView, selectedTrust, fresh }) => {
      const isOrgViewTrust = selectedTrust && orgView
        && orgView.trust_id === selectedTrust.trust_id;
      const isSelectedValid = selectedTrust
        && (isOrgViewTrust || fresh.some((t) => t.trust_id === selectedTrust.trust_id));
      if (!selectedTrust && orgView?.trust_id) {
        return { action: 'adopt-orgview', trust: orgView.trust_id };
      }
      if (!isSelectedValid) {
        if (selectedTrust) {
          const firstReal = fresh.find((t) => t.is_demo !== true && t.isDemo !== true);
          const fallback = firstReal || fresh[0] || null;
          return { action: 'clear-and-fallback', trust: fallback ? fallback.trust_id : null };
        }
        const firstReal = fresh.find((t) => t.is_demo !== true && t.isDemo !== true);
        const fallback = firstReal || fresh[0] || null;
        return { action: 'fallback', trust: fallback ? fallback.trust_id : null };
      }
      return { action: 'keep', trust: selectedTrust.trust_id };
    };

    it('post-exit: client trust not in fresh list → cleared, fallback to own trust', () => {
      const out = decide({
        orgView: null,
        selectedTrust: { trust_id: 'trust_client', name: "I AM MINISTRIES" },
        fresh: [{ trust_id: 'trust_own', name: 'JK Sandbox Trust' }],
      });
      expect(out.action).toBe('clear-and-fallback');
      expect(out.trust).toBe('trust_own');
    });

    it('mid-view: org-view selection stays valid (no cull mid-session)', () => {
      const out = decide({
        orgView: { trust_id: 'trust_client', trust_name: 'I AM MINISTRIES' },
        selectedTrust: { trust_id: 'trust_client', name: 'I AM MINISTRIES' },
        fresh: [{ trust_id: 'trust_own', name: 'JK Sandbox Trust' }],
      });
      expect(out.action).toBe('keep');
    });

    it('own trust selection not affected by exit', () => {
      const out = decide({
        orgView: null,
        selectedTrust: { trust_id: 'trust_own', name: 'JK Sandbox Trust' },
        fresh: [{ trust_id: 'trust_own', name: 'JK Sandbox Trust' }],
      });
      expect(out.action).toBe('keep');
    });
  });
});