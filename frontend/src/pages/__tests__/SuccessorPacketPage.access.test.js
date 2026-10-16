/**
 * Frontend smoke test for the Successor Access card (SuccessorPacketPage).
 *
 * Covers: method radio rendering (default access_code), generate-code flow shows the
 * copy-once panel, method switch to death_cert renders the review panel.
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ selectedTrust: { trust_id: 't1', name: 'Family Trust' } }),
}));

const mockFetch = jest.fn();
jest.mock('@/utils/api', () => ({
  fetchWithAuth: (...args) => mockFetch(...args),
}));

jest.mock('sonner', () => ({ toast: { success: jest.fn(), warning: jest.fn(), error: jest.fn() } }));
// Real runWithStepUp replays on 403; the hook mock drives the request like the real first attempt.
jest.mock('@/hooks/use2faStepUp', () => () => ({
  stepUpOpen: false,
  runWithStepUp: (doRequest) => doRequest(undefined),
  handleStepUpSubmit: jest.fn(),
  closeStepUp: jest.fn(),
  TwoFactorStepUpModal: () => null,
}));
jest.mock('@/components/Sidebar', () => ({ Sidebar: () => null }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => null }));
jest.mock('@/components/PageHeader', () => ({ __esModule: true, default: ({ title, actions }) => (
  <div><span>{title}</span><div>{actions}</div></div>
) }));

import SuccessorPacketPage from '@/pages/SuccessorPacketPage';

const okJson = (data) => ({ ok: true, json: async () => data });
const accessStatusJson = (status) => ({ ok: true, json: async () => status });

describe('Successor Access card (SuccessorPacketPage)', () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  test('method card shows Access code as default-selected', async () => {
    mockFetch.mockImplementation((ep) => {
      if (ep === '/trusts/t1') return Promise.resolve(okJson({ name: 'Family Trust', successor_trustee_email: 'sam@x.com' }));
      if (ep === '/trusts/t1/successor/access-status') {
        return Promise.resolve(accessStatusJson({ method: 'access_code', code_set: false, code_hint: null, code_use_count: 0, pending_claims: 0 }));
      }
      return Promise.resolve(okJson([]));
    });
    render(<SuccessorPacketPage />);
    expect(await screen.findByText('How your successor gets in')).toBeTruthy();
    expect(screen.getByText('Access code')).toBeTruthy();
    expect(screen.getByText(/Generate access code/)).toBeTruthy();
  });

  test('generate code shows the copy-once panel', async () => {
    mockFetch.mockImplementation((ep, opts) => {
      if (ep === '/trusts/t1') return Promise.resolve(okJson({ name: 'Family Trust', successor_trustee_email: 'sam@x.com' }));
      if (ep === '/trusts/t1/successor/code' && opts?.method === 'POST') {
        return Promise.resolve(okJson({ code: 'ABCD-EFGH-JKLM-NPQR', code_hint: 'ABCD-••••-••••-NPQR', method: 'access_code' }));
      }
      if (ep === '/trusts/t1/successor/access-status') {
        return Promise.resolve(accessStatusJson({ method: 'access_code', code_set: false, code_hint: null, code_use_count: 0, pending_claims: 0 }));
      }
      return Promise.resolve(okJson([]));
    });
    render(<SuccessorPacketPage />);
    await screen.findByText('How your successor gets in');
    fireEvent.click(screen.getByText(/Generate access code/));
    // Raw code is displayed in the copy-once panel
    await waitFor(() => expect(screen.getByText('ABCD-EFGH-JKLM-NPQR')).toBeTruthy());
  });

  test('switching to death_cert shows review queue copy', async () => {
    mockFetch.mockImplementation((ep, opts) => {
      if (ep === '/trusts/t1') return Promise.resolve(okJson({ name: 'Family Trust', successor_trustee_email: 'sam@x.com' }));
      if (ep === '/trusts/t1/successor/access-status') {
        if (opts && opts.method === 'POST') {
          return Promise.resolve(okJson({ method: 'death_cert', previous: 'access_code' }));
        }
        return Promise.resolve(accessStatusJson({ method: 'death_cert', code_set: false, code_use_count: 0, pending_claims: 2 }));
      }
      return Promise.resolve(okJson([]));
    });
    render(<SuccessorPacketPage />);
    await screen.findByText('How your successor gets in');
    fireEvent.click(screen.getByText(/Death-certificate verification/));
    await waitFor(() => expect(screen.getByText(/2 claims awaiting review/)).toBeTruthy());
  });
});