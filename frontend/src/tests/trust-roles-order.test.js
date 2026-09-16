/**
 * Trust Roles page (SettingsPage rendered at /trust-roles) — regression test.
 *
 * Jeff directive 2026-09-16: the People tab ran Successor Trustee → Secondary →
 * Trust Protector → Grantor → Key Contacts → Successor Instructions, which
 * split the successor-trustee story in half. Canonical order is now:
 *   Grantor → Successor Trustee → Secondary Successor Trustee
 *   → Successor Instructions → Trust Protector → Key Contacts
 * The Trust Roles surface must also stay discoverable (desktop sidebar entry)
 * and cross-linked with the Legal Powers page (/authority).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import SettingsPage from '@/pages/SettingsPage';
import { Sidebar } from '@/components/Sidebar';
import { ThemeProvider } from '@/context/ThemeContext';
import { useAuth } from '@/context/AuthContext';
import { fetchWithAuth } from '@/utils/api';

jest.mock('@/context/AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn() }));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => <nav data-testid="mobile-nav" /> }));
jest.mock('@/components/PageHelpButton', () => () => <div data-testid="page-help" />);
jest.mock('@/components/EmailArchiveCard', () => () => <div data-testid="email-archive" />);
jest.mock('@/components/DevicesSessionsCard', () => () => <div data-testid="devices" />);
jest.mock('@/components/TwoFactorCard', () => () => <div data-testid="twofa" />);
jest.mock('@/components/KeyCustodySuggestionCard', () => () => <div data-testid="key-custody" />);
jest.mock('@/components/ui/button', () => {
  const Btn = ({ children, ...rest }) => <button {...rest}>{children}</button>;
  return { Button: Btn, __esModule: true };
});
jest.mock('@/components/ui/input', () => {
  const Inp = (props) => <input {...props} />;
  return { Input: Inp, __esModule: true };
});
jest.mock('@/components/ui/label', () => {
  const Lbl = ({ children, ...rest }) => <label {...rest}>{children}</label>;
  return { Label: Lbl, __esModule: true };
});
jest.mock('@/components/ui/textarea', () => {
  const Ta = (props) => <textarea {...props} />;
  return { Textarea: Ta, __esModule: true };
});
jest.mock('@/components/ui/switch', () => {
  const Sw = (props) => <input type="checkbox" {...props} />;
  return { Switch: Sw, __esModule: true };
});
jest.mock('@/components/ui/tabs', () => {
  const Tabs = ({ children }) => <div data-testid="tabs">{children}</div>;
  const TabsList = ({ children }) => <div>{children}</div>;
  const TabsTrigger = (props) => <div {...props} />;
  const TabsContent = ({ value, children }) => <div data-testid={`tab-${value}`}>{children}</div>;
  return { Tabs, TabsList, TabsTrigger, TabsContent, __esModule: true };
});
jest.mock('@/components/ui/select', () => {
  const Select = ({ children }) => <div>{children}</div>;
  const SelectContent = ({ children }) => <div>{children}</div>;
  const SelectItem = (props) => <div {...props} />;
  const SelectTrigger = ({ children, ...rest }) => <div {...rest}>{children}</div>;
  const SelectValue = () => null;
  return { Select, SelectContent, SelectItem, SelectTrigger, SelectValue, __esModule: true };
});
jest.mock('@/components/ui/dialog', () => {
  const Dialog = ({ children }) => <div>{children}</div>;
  const DialogContent = ({ children }) => <div>{children}</div>;
  const DialogHeader = ({ children }) => <div>{children}</div>;
  const DialogTitle = ({ children }) => <div>{children}</div>;
  const DialogTrigger = ({ children }) => <div>{children}</div>;
  const DialogFooter = ({ children }) => <div>{children}</div>;
  const DialogDescription = ({ children }) => <div>{children}</div>;
  return { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter, DialogDescription, __esModule: true };
});
jest.mock('@/utils/errors', () => ({ showError: jest.fn() }));

const mockLocation = { pathname: '/trust-roles', hash: '', search: '' };
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useNavigate: () => jest.fn(),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
  useLocation: () => mockLocation,
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
  default: {},
}));


// jsdom lacks matchMedia; ThemeProvider reads prefers-color-scheme at init.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  });
}

const TRUST = {
  trust_id: 't1',
  name: 'Family Trust',
  grantor_name: '',
  successor_trustee_name: '',
  successor_trustee_email: '',
  successor_trustee_phone: '',
  successor_trustee_relationship: '',
  secondary_successor_name: '',
  secondary_successor_email: '',
  secondary_successor_phone: '',
  secondary_successor_relationship: '',
  trust_protector_name: '',
  trust_protector_email: '',
  trust_protector_phone: '',
  trust_protector_powers: [],
  trust_protector_enabled: false,
  successor_instructions: '',
  document_location: '',
  attorney_name: '', attorney_phone: '', attorney_email: '',
  cpa_name: '', cpa_phone: '', cpa_email: '',
  financial_advisor_name: '', financial_advisor_phone: '', financial_advisor_email: '',
};

function renderTrustRoles() {
  useAuth.mockReturnValue({
    user: { id: 'u1', email: 'jeff@example.com' },
    selectedTrust: TRUST,
    trusts: [TRUST],
    setSelectedTrust: jest.fn(),
    loadTrusts: jest.fn().mockResolvedValue([TRUST]),
    isReadOnly: false,
  });
  fetchWithAuth.mockResolvedValue({ ok: true, json: async () => ({}) });
  return render(
    <ThemeProvider>
      <SettingsPage />
    </ThemeProvider>
  );
}

describe('Trust Roles page — section order (Jeff directive 2026-09-16)', () => {
  test('renders the Trust Roles header, not Settings', async () => {
    renderTrustRoles();
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Trust Roles');
  });

  test('People sections render in canonical role order', async () => {
    renderTrustRoles();
    const body = document.body.innerHTML;
    const order = [
      'Grantor',
      'Successor Trustee Name',
      'Secondary Successor Trustee Name',
      'Successor Instructions',
      'Trust Protector',
      'Key Contacts',
    ];
    const positions = order.map((label) => {
      const idx = body.indexOf(`>${label}<`);
      expect(idx).toBeGreaterThanOrEqual(0); // every section present
      return idx;
    });
    const sorted = [...positions].sort((a, b) => a - b);
    expect(positions).toEqual(sorted); // and in this exact order
  });

  test('successor-trustee content is not interrupted by protector/grantor content', async () => {
    renderTrustRoles();
    const body = document.body.innerHTML;
    const st = body.indexOf('Successor Trustee Name');
    const si = body.indexOf('Successor Instructions');
    const between = body.slice(st, si);
    expect(between).not.toContain('Grantor Name');
    expect(between).not.toContain('Trust Protector Name');
    expect(between).not.toContain('Trust Attorney');
  });

  test('links to the Legal Powers page and the Successor Packet', async () => {
    renderTrustRoles();
    const legal = screen.getByText('View recorded trustee powers (Legal Powers page)');
    expect(legal.closest('a,button')).toBeTruthy();
    expect(screen.getByText('View Successor Packet')).toBeTruthy();
  });
});

describe('Trust Roles discoverability (Jeff: "not in the main menu")', () => {
  test('desktop sidebar carries a Trust Roles entry in Trust Structure', () => {
    useAuth.mockReturnValue({
      user: { id: 'u1' }, selectedTrust: null, trusts: [], setSelectedTrust: jest.fn(),
      loadTrusts: jest.fn(), isReadOnly: false,
    });
    render(
      <ThemeProvider>
        <Sidebar />
      </ThemeProvider>
    );
    const link = screen.getByTestId('nav-trust-roles');
    expect(link).toHaveAttribute('href', '/trust-roles');
    // Lives inside the Trust Structure group's accordion
    const group = link.closest('.sidebar-accordion');
    expect(group).toBeTruthy();
    expect(group.textContent).toContain('Trust & Entities');
  });
});