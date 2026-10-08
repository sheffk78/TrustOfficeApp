// ClassBeneficiariesTab class-member card UI tests (session 3, council design).
//
// Contract under test (backend endpoints live on api.trustoffice.app):
//   GET  /beneficiaries/class-beneficiaries/{id}/members
//   POST /beneficiaries/class-beneficiaries/{id}/members               {name, date_of_birth?}
//   POST /beneficiaries/class-beneficiaries/{id}/members/{mid}/status  {status, reason REQUIRED}
//   PATCH /beneficiaries/class-beneficiaries/{id}/members/{mid}        {name}
// No member delete path — status change only (council design #3).
//
// Renders the tab through the real useClassMembers hook so the URL/body
// assertions hit the actual hook code. Network is mocked via fetchWithAuth at
// module level (same pattern as DevicesSessionsCard.test.js); no real backend.

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ClassBeneficiariesTab from '@/pages/beneficiaries/ClassBeneficiariesTab';
import { useClassMembers } from '@/pages/beneficiaries/hooks';
import { EDUCATION_SECTIONS, EMPTY_ROSTER_TEXT } from '@/pages/beneficiaries/constants';

jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(),
}));
jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

// lucide icons resolve to stubs.
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

// Dialog (radix) — pass-through so content renders inline if ever used.
jest.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }) => <div>{children}</div>,
  DialogContent: ({ children }) => <div>{children}</div>,
  DialogHeader: ({ children }) => <div>{children}</div>,
  DialogTitle: ({ children }) => <h2>{children}</h2>,
  DialogDescription: ({ children }) => <p>{children}</p>,
  DialogFooter: ({ children }) => <div>{children}</div>,
  DialogTrigger: ({ children }) => <div>{children}</div>,
}));

import { fetchWithAuth } from '@/utils/api';

const CLASS_ID = 'cb_1';
const TRUST = { trust_id: 'trust_1' };

const overviewData = {
  class_beneficiaries: [
    {
      class_beneficiary_id: CLASS_ID,
      class_type_label: 'Children',
      description: 'All children of the grantor',
      percentage: 60,
    },
  ],
};

const membersResponse = {
  items: [
    {
      class_member_id: 'cm_1',
      name: 'Alice Smith',
      member_status: 'active',
      member_order: 1,
      member_share_ppm: 600000,
      member_share_percent: 60,
      name_history: [],
      date_of_birth: '1990-01-01',
    },
    {
      class_member_id: 'cm_2',
      name: 'Bob Smith',
      member_status: 'inactive',
      status_reason: 'Requested pause',
      member_order: 2,
      member_share_ppm: 0,
      member_share_percent: 0,
      name_history: [{ previous_name: 'Robert Smith', changed_at: '2026-10-01T00:00:00Z' }],
    },
    {
      class_member_id: 'cm_3',
      name: 'Cara Smith',
      member_status: 'deceased',
      member_order: 3,
      member_share_ppm: 0,
      member_share_percent: 0,
      name_history: [],
    },
  ],
  member_count: 3,
  active_member_count: 1,
  pool_percentage: 60,
  pool_percentage_ppm: 600000,
  per_member_percentage: 60,
  per_member_share_percent: { cm_1: 60 },
  per_member_shares: [{ class_member_id: 'cm_1', share_ppm: 600000, share_pct: 60 }],
  sum_check: true,
  share_mode: 'per_capita_equal',
  sum_check_ppm: 0,
};

// Harness: real hook + real tab wired the way BeneficiariesPage wires them.
function Harness({ data = membersResponse }) {
  const members = useClassMembers(TRUST, jest.fn());
  return (
    <ClassBeneficiariesTab
      overviewData={overviewData}
      setShowClassBeneficiaryModal={() => undefined}
      setDeleteConfirmClass={() => undefined}
      membersState={members}
      onLoadMembers={members.loadMembers}
      onAddMember={members.addMember}
      onRenameMember={members.renameMember}
      onStatusChange={members.setMemberStatus}
    />
  );
}

function mockOk(data) {
  fetchWithAuth.mockImplementation(async () => ({
    ok: true,
    status: 200,
    json: async () => data,
  }));
}

// Expand the class card and wait for the roster fetch to land (roster or
// empty-roster state, depending on the mocked response). Since 2026-10-08 the
// cards render expanded by DEFAULT — the panel is already open after render.
// The toggle click remains in the helper for collapse/expand round-trips.
async function openPanel(data = membersResponse) {
  mockOk(data);
  render(<Harness data={data} />);
  await screen.findByTestId(`class-panel-${CLASS_ID}`);
  await waitFor(() => {
    expect(
      screen.queryByTestId(`roster-${CLASS_ID}`) || screen.queryByTestId(`empty-roster-${CLASS_ID}`)
    ).toBeTruthy();
  });
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ClassBeneficiariesTab expanded class member card', () => {
  it('fetches the roster and renders names, status chips, and member_share_percent values', async () => {
    await openPanel();

    expect(fetchWithAuth).toHaveBeenCalledWith(`/beneficiaries/class-beneficiaries/${CLASS_ID}/members`);

    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.getByText('Bob Smith')).toBeInTheDocument();
    expect(screen.getByText('Cara Smith')).toBeInTheDocument();

    // Live-computed share (per_member_share_percent) displayed per member.
    expect(screen.getByTestId('member-share-cm_1')).toHaveTextContent('60%');
    expect(screen.getByTestId('member-share-cm_2')).toHaveTextContent('0%');
    // Status chips on non-active members only.
    expect(screen.getByTestId('member-status-chip-cm_2')).toHaveTextContent('inactive');
    expect(screen.getByTestId('member-status-chip-cm_3')).toHaveTextContent('deceased');
    expect(screen.queryByTestId('member-status-chip-cm_1')).not.toBeInTheDocument();
  });

  it('shows the pool band: split-N-ways line, live per-member shares, and the sum-check confirm', async () => {
    await openPanel();

    expect(await screen.findByTestId(`split-ways-${CLASS_ID}`)).toHaveTextContent('split 1 way');
    expect(screen.getByTestId(`pool-split-${CLASS_ID}`)).toHaveTextContent('Alice Smith: 60%');
    expect(screen.getByTestId(`sum-check-${CLASS_ID}`)).toHaveTextContent('Shares add up ✓');
    expect(screen.queryByText('Σ = pool ✓')).not.toBeInTheDocument();
    // Fixed-instrument vs computed-pool distinction (one muted caption line).
    expect(
      screen.getByText(/computed pool split live across members, not an issued certificate/i)
    ).toBeInTheDocument();
  });

  it('renders the sum-check warning when the API reports sum_check false', async () => {
    await openPanel({ ...membersResponse, sum_check: false });

    await screen.findByTestId(`roster-${CLASS_ID}`);
    expect(screen.getByTestId(`sum-check-${CLASS_ID}`)).toHaveTextContent("don't add up to the pool");
    expect(screen.queryByText('Σ ≠ pool')).not.toBeInTheDocument();
  });

  it('shows NO sum-check chip and NO split line when the roster is empty (no scary math on first run)', async () => {
    await openPanel({
      ...membersResponse,
      items: [],
      member_count: 0,
      active_member_count: 0,
      per_member_share_percent: {},
      per_member_shares: [],
    });

    await screen.findByTestId(`empty-roster-${CLASS_ID}`);
    expect(screen.queryByTestId(`sum-check-${CLASS_ID}`)).not.toBeInTheDocument();
    expect(screen.queryByTestId(`split-ways-${CLASS_ID}`)).not.toBeInTheDocument();
  });

  it('cards render EXPANDED by default with roster and Add Member visible without any click', async () => {
    mockOk(membersResponse);
    render(<Harness />);
    // Panel opens automatically; no toggle click needed.
    await screen.findByTestId(`class-panel-${CLASS_ID}`);
    expect(screen.getByTestId(`add-member-btn-${CLASS_ID}`)).toBeInTheDocument();
    // Toggle collapses; toggle again re-expands.
    fireEvent.click(screen.getByTestId(`class-toggle-${CLASS_ID}`));
    expect(screen.queryByTestId(`class-panel-${CLASS_ID}`)).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId(`class-toggle-${CLASS_ID}`));
    expect(await screen.findByTestId(`class-panel-${CLASS_ID}`)).toBeInTheDocument();
  });

  it('collapsed card carries a click affordance line inviting the user to open the panel', async () => {
    mockOk(membersResponse);
    render(<Harness />);
    await screen.findByTestId(`class-panel-${CLASS_ID}`);
    fireEvent.click(screen.getByTestId(`class-toggle-${CLASS_ID}`)); // collapse
    expect(screen.getByTestId(`class-hint-${CLASS_ID}`)).toHaveTextContent('Click to view members and add a person');
    fireEvent.click(screen.getByTestId(`class-toggle-${CLASS_ID}`)); // expand again
    await screen.findByTestId(`class-panel-${CLASS_ID}`);
  });

  it('add member calls POST with {name, date_of_birth} then reloads roster and overview counts', async () => {
    await openPanel();

    fireEvent.click(screen.getByTestId(`add-member-btn-${CLASS_ID}`));
    fireEvent.change(screen.getByTestId(`add-member-name-${CLASS_ID}`), { target: { value: 'Dana Smith' } });
    fireEvent.change(screen.getByTestId(`add-member-dob-${CLASS_ID}`), { target: { value: '2001-02-03' } });
    fireEvent.click(screen.getByTestId(`add-member-save-${CLASS_ID}`));

    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith(
      `/beneficiaries/class-beneficiaries/${CLASS_ID}/members`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ name: 'Dana Smith', date_of_birth: '2001-02-03' }),
      })
    ));
    // Roster refetched (GET again after the POST) and success toast shown.
    await waitFor(() => expect(fetchWithAuth.mock.calls.filter((c) => c[1]?.method === 'POST')).toHaveLength(1));
    await waitFor(() => {
      const getCalls = fetchWithAuth.mock.calls.filter((c) => c[1] === undefined || c[1]?.method === undefined);
      expect(getCalls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('add-member submit is disabled until a name is entered', async () => {
    await openPanel();

    fireEvent.click(screen.getByTestId(`add-member-btn-${CLASS_ID}`));
    const submit = screen.getByTestId(`add-member-save-${CLASS_ID}`);
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId(`add-member-name-${CLASS_ID}`), { target: { value: 'Dana Smith' } });
    expect(submit).not.toBeDisabled();
  });

  it('status change requires a reason: submit stays disabled while empty, then POSTs {status, reason}', async () => {
    await openPanel();

    // Active member (cm_1): open the status-change panel.
    fireEvent.click(screen.getByTestId('member-status-cm_1'));
    const panel = await screen.findByTestId('member-status-panel-cm_1');

    const submit = screen.getByTestId('member-status-submit-cm_1');
    expect(submit).toBeDisabled();

    // Target status defaults to inactive; switching targets is available.
    fireEvent.click(withinPanel(panel, 'deceased'));

    fireEvent.change(screen.getByTestId('member-reason-input-cm_1'), { target: { value: 'Death certificate received' } });
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith(
      `/beneficiaries/class-beneficiaries/${CLASS_ID}/members/cm_1/status`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ status: 'deceased', reason: 'Death certificate received' }),
      })
    ));
  });

  it('restore-to-active also requires a reason before submit', async () => {
    await openPanel();

    // Excluded member (cm_2, inactive): restore path.
    fireEvent.click(screen.getByTestId('member-restore-cm_2'));
    await screen.findByTestId('member-status-panel-cm_2');

    const submit = screen.getByTestId('member-status-submit-cm_2');
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('member-reason-input-cm_2'), { target: { value: 'Custodian records corrected' } });
    expect(submit).not.toBeDisabled();

    fireEvent.click(submit);
    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith(
      `/beneficiaries/class-beneficiaries/${CLASS_ID}/members/cm_2/status`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ status: 'active', reason: 'Custodian records corrected' }),
      })
    ));
  });

  it('rename uses PATCH {name} via the inline edit path', async () => {
    await openPanel();

    fireEvent.click(screen.getByTestId('member-rename-cm_2'));
    const input = screen.getByTestId('member-rename-input');
    fireEvent.change(input, { target: { value: 'Robert Q. Smith' } });
    fireEvent.click(screen.getByTestId('member-rename-save'));

    await waitFor(() => expect(fetchWithAuth).toHaveBeenCalledWith(
      `/beneficiaries/class-beneficiaries/${CLASS_ID}/members/cm_2`,
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ name: 'Robert Q. Smith' }),
      })
    ));
  });

  it('renamed member shows the tiny tag with the previous name on hover', async () => {
    await openPanel();

    const tag = screen.getByTestId('member-renamed-cm_2');
    expect(tag).toHaveTextContent('renamed');
    expect(tag).toHaveAttribute('title', 'was: Robert Smith');
  });

  it('empty roster state renders the exact council phrasing', async () => {
    await openPanel({
      ...membersResponse,
      items: [],
      member_count: 0,
      active_member_count: 0,
      per_member_share_percent: {},
      per_member_shares: [],
    });

    const empty = await screen.findByTestId(`empty-roster-${CLASS_ID}`);
    expect(empty.textContent).toBe(EMPTY_ROSTER_TEXT);
    expect(empty.textContent).toContain('No members yet');
    expect(screen.queryByTestId(`roster-${CLASS_ID}`)).not.toBeInTheDocument();
  });

  it('education content and delete-class button remain untouched', () => {
    mockOk(membersResponse);
    render(<Harness />);

    expect(screen.getAllByText(EDUCATION_SECTIONS.classBeneficiaries.title).length).toBeGreaterThan(0);
    expect(screen.getByTestId(`class-toggle-${CLASS_ID}`)).toBeInTheDocument();
    expect(screen.getByTestId(`delete-class-${CLASS_ID}`)).toBeInTheDocument();
    expect(screen.getByTestId('add-class-beneficiary-btn')).toBeInTheDocument();
  });
});

// Helper: find a button by exact text inside the passed panel element.
function withinPanel(panelEl, text) {
  const btn = Array.from(panelEl.querySelectorAll('button')).find((b) => b.textContent.trim() === text);
  if (!btn) throw new Error(`button "${text}" not found in panel`);
  return btn;
}