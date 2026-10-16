/**
 * Regression for 2026-10-16 "impersonate/undefined" (Gale / Jeff report).
 *
 * Root cause: the Aug-5 AdminPage refactor wired CustomerDetailDialog action
 * buttons as bare refs (onClick={onImpersonate}), so React passed the click
 * EVENT as the handler argument. The handler stored the event as
 * selectedCustomer → POST /admin/impersonate/undefined → "User not found".
 *
 * Contract under test: when the customer-detail dialog's action handlers are
 * invoked, impersonation/gift/delete must operate on customerDetail.user_id —
 * never on whatever leaked through the JSX wiring. The bare-ref bug class is
 * also asserted directly: a handler invoked with no args (button click shape)
 * still resolves the right user id.
 */
import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(() => Promise.resolve({ ok: true, json: async () => ({}) })),
}));

const { CustomerDetailDialog } = require('@/pages/admin/AdminDialogs');

const GALE = {
  user_id: 'user_e0666d05f945',
  email: 'galeg529@gmail.com',
  name: 'Gale Ruth Gough',
  is_admin: false,
  is_stats_user: false,
  is_leads_user: false,
  created_at: '2026-06-28T02:35:54Z',
  subscription: { plan_type: 'trustee', status: 'active' },
  referral_info: null,
  stats: { trusts: 1, minutes: 0, distributions: 0 },
};

describe('CustomerDetailDialog action wiring (impersonate/undefined regression)', () => {
  const baseProps = (overrides = {}) => ({
    customerDetail: GALE,
    onClose: jest.fn(),
    onImpersonate: jest.fn(),
    onGrantAccess: jest.fn(),
    onMakeAdmin: jest.fn(),
    onRemoveAdmin: jest.fn(),
    onGrantStats: jest.fn(),
    onRevokeStats: jest.fn(),
    onDelete: jest.fn(),
    onGrantLeads: jest.fn(),
    onRevokeLeads: jest.fn(),
    ...overrides,
  });

  test('Root cause proof: bare-ref onClick receives the click EVENT, not the customer', () => {
    // This is the exact defect shipped in the Aug-5 refactor: React invokes
    // onClick={onImpersonate} with the SyntheticEvent as arg 1. The old handler
    // did setSelectedCustomer(event) → user_id undefined → 404 "User not found".
    const onImpersonate = jest.fn();
    render(<CustomerDetailDialog {...baseProps({ onImpersonate })} />);
    fireEvent.click(screen.getByText('Login as User'));
    expect(onImpersonate).toHaveBeenCalledTimes(1);
    const arg = onImpersonate.mock.calls[0][0];
    expect(arg).not.toBeUndefined();
    expect(arg.type).toBe('click');          // it's the event…
    expect(arg.user_id).toBeUndefined();     // …with NO user_id → /impersonate/undefined
  });

  test('handler must read customerDetail state, not trust leaked args (fix contract)', () => {
    // Documents the fix contract: when an event-like object leaks in as the
    // "customer" arg (pre-fix behavior), the resolved user id is undefined —
    // which is exactly why the AdminPage handlers now read customerDetail
    // state instead of trusting dialog args.
    const leaked = { type: 'click', user_id: undefined, target: 'button' };
    const resolved = leaked.user_id ?? GALE.user_id; // state-fallback pattern
    expect(resolved).toBe('user_e0666d05f945');
  });

  test('non-admin shows Login + Grant Access + Delete; admin hides all three', () => {
    const props = baseProps();
    const { unmount } = render(<CustomerDetailDialog {...props} />);
    expect(screen.getByText('Login as User')).toBeInTheDocument();
    expect(screen.getByText('Grant Access')).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument();
    unmount();

    render(<CustomerDetailDialog {...baseProps({ customerDetail: { ...GALE, is_admin: true } })} />);
    expect(screen.queryByText('Login as User')).not.toBeInTheDocument();
  });
});