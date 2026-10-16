// Regression: org invite guards — TICKET-20261001-CLIENT-GUARDS item 2.
// (1) A malformed email must stop at the dialog: no network call, inline
//     invite-error shown. (2) An email already on the roster must stop too
//     (the backend rejects it as invite_already_exists / member_already_active
//     — those were landing in the error log as 422 noise).
// jest.mock hoisting note: factories must not reference out-of-scope vars
// unless `mock`-prefixed, or the mock silently never applies (real fetch runs).
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: { user_id: 'u1', email: 'owner@example.com', role: 'admin' } }),
}));
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <aside data-testid="side" /> }));

const mockCalls = [];
const mockMembers = [{ member_id: 'm1', role: 'owner', name: 'Jeff', email: 'owner@example.com', status: 'active' }];
jest.mock('@/utils/api', () => ({
  fetchWithAuth: async (path, opts) => {
    mockCalls.push({ path, opts });
    if (path === '/orgs') {
      return { ok: true, json: async () => ([{ org_id: 'org_test123', name: 'WingPoint Trust Group' }]) };
    }
    if (path.includes('/members')) {
      return { ok: true, json: async () => (mockMembers) };
    }
    if (path.includes('/trusts')) {
      return { ok: true, json: async () => ({ trusts: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  },
}));

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/utils/errors', () => ({ showError: jest.fn(), humanizeErrorCode: (c) => c || null }));

import OrgConsolePage from '../OrgConsolePage';

describe('OrgConsolePage invite guards', () => {
  beforeEach(() => { mockCalls.length = 0; });

  async function openInvite() {
    render(<OrgConsolePage />);
    const btn = await screen.findByTestId('invite-org_test123', undefined, { timeout: 3000 });
    fireEvent.click(btn);
    await screen.findByTestId('invite-email-input');
  }

  test('invalid email format stops at the dialog — no invite POST fired', async () => {
    await openInvite();
    fireEvent.change(screen.getByTestId('invite-email-input'), { target: { value: 'not-an-email' } });
    fireEvent.click(screen.getByTestId('send-invite-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('invite-error').textContent).toMatch(/valid email/i);
    });
    expect(mockCalls.filter(c => c.path.includes('/invites'))).toHaveLength(0);
  });

  test('email already on the roster stops at the dialog — no invite POST fired', async () => {
    await openInvite();
    fireEvent.change(screen.getByTestId('invite-email-input'), { target: { value: 'OWNER@example.com' } });
    fireEvent.click(screen.getByTestId('send-invite-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('invite-error').textContent).toMatch(/already on this org/i);
    });
    expect(mockCalls.filter(c => c.path.includes('/invites'))).toHaveLength(0);
  });

  test('valid fresh email still fires the invite POST with the org_id path', async () => {
    await openInvite();
    fireEvent.change(screen.getByTestId('invite-email-input'), { target: { value: 'newperson@example.com' } });
    fireEvent.click(screen.getByTestId('send-invite-btn'));
    await waitFor(() => {
      const inviteCall = mockCalls.find(c => c.path.includes('/invites'));
      expect(inviteCall).toBeTruthy();
      expect(inviteCall.path).toBe('/orgs/org_test123/invites');
    });
  });
});