import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CoursePage from '@/pages/CoursePage';
import { API } from '@/utils/api';

// The 2026-11-09 incident: the web-activity POST used a RELATIVE url
// (fetch('/api/admin/leads/activity')). The SPA host's catch-all serves
// text/html 200 for every path, so the fire-and-forget POST silently hit the
// SPA and nothing ever landed in the CRM. These tests pin CoursePage's fetch
// URLs to the ABSOLUTE API origin so the bug can't come back quietly.

jest.mock('@/utils/api', () => ({ fetchWithAuth: jest.fn(), API: 'https://api.test/api' }));
jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ user: { email: 'learner@example.com' }, subscription: {} }),
}));

jest.mock('@/components/Sidebar', () => ({ Sidebar: () => <nav data-testid="sidebar" /> }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => <div data-testid="mobile-nav" /> }));
jest.mock('@/components/PageHeader', () => ({ __esModule: true, default: (props) => <div data-testid="page-header">{props.title}</div> }));
jest.mock('@/components/Spinner', () => ({ __esModule: true, default: (props) => <div data-testid="spinner">{props.label || ''}</div> }));
jest.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, className }) => (
    <button type="button" onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
}));

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

const CURRICULUM = {
  course: 'Trustee 101',
  tagline: 'Guided course',
  free_lessons: [{ lesson: 1 }],
  lessons: [
    {
      lesson: 1,
      title: 'Intro lesson',
      duration: '5 min',
      free: true,
      video_guid: 'vid-1',
      pdf_url: '/worksheets/ws-1.pdf',
    },
  ],
};

const calls = [];

beforeEach(() => {
  calls.length = 0;
  global.fetch = jest.fn((url, opts) => {
    calls.push({ url: String(url), opts: opts || {} });
    if (String(url).includes('/courses/trustee-101/curriculum')) {
      return Promise.resolve({ ok: true, status: 200, json: async () => CURRICULUM });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) });
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

const activityCalls = () => calls.filter((c) => c.url.includes('/admin/leads/activity'));

async function renderLoaded() {
  render(<CoursePage />);
  await waitFor(() => expect(screen.getByText('All Lessons')).toBeInTheDocument());
  expect(calls[0].url).toBe(`${API}/courses/trustee-101/curriculum`);
}

describe('CoursePage web-activity calls hit the API origin (not the SPA host)', () => {
  test('every fetch URL is absolute against the API constant', async () => {
    await renderLoaded();
    // lesson 1 (free) is auto-selected without logging; click its LIST button
    // (role=button; the <h2> in the info bar repeats the title, so scope by role)
    fireEvent.click(screen.getAllByRole('button', { name: /Intro lesson/ })[0]);
    await waitFor(() => expect(activityCalls().length).toBe(1));
    for (const c of calls) {
      expect(c.url.startsWith(`${API}/`)).toBe(true);
      expect(c.url.startsWith('/api/')).toBe(false);
    }
  });

  test('lesson click posts video_open to ${API}/admin/leads/activity', async () => {
    await renderLoaded();
    fireEvent.click(screen.getAllByRole('button', { name: /Intro lesson/ })[0]);
    await waitFor(() => expect(activityCalls().length).toBe(1));
    const c = activityCalls()[0];
    expect(c.url).toBe(`${API}/admin/leads/activity`);
    expect(c.opts.method).toBe('POST');
    const body = JSON.parse(c.opts.body);
    expect(body).toEqual({
      email: 'learner@example.com',
      action_type: 'video_open',
      detail: 'Opened lesson 1: Intro lesson',
    });
  });

  test('PDF download click posts pdf_download to the same absolute URL', async () => {
    await renderLoaded();
    // lesson 1 carries pdf_url, so the Download PDF link is rendered for the
    // auto-selected lesson; clicking it logs pdf_download.
    fireEvent.click(screen.getByText('Download PDF'));
    await waitFor(() => expect(activityCalls().length).toBe(1));
    expect(activityCalls()[0].url).toBe(`${API}/admin/leads/activity`);
    expect(JSON.parse(activityCalls()[0].opts.body).action_type).toBe('pdf_download');
  });
});
