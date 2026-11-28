// Regression: template-created minutes rendered in MinutesDetailPage must send
// edits/deletes to /minutes-templates/{id}; non-template minutes keep using
// /minutes/{id}. Finalize stays on /minutes/{id}.
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@/context/AuthContext', () => ({
  useAuth: () => ({ selectedTrust: { trust_id: 't1', name: 'Test Trust' } }),
}));

const mockFetch = jest.fn();
jest.mock('@/utils/api', () => ({
  fetchWithAuth: (...args) => mockFetch(...args),
}));

const mockToast = { success: jest.fn(), error: jest.fn() };
jest.mock('sonner', () => ({ toast: { success: (...a) => mockToast.success(...a), error: (...a) => mockToast.error(...a) } }));
jest.mock('@/utils/errors', () => ({ showError: jest.fn() }));

jest.mock('@/components/Sidebar', () => ({ Sidebar: () => null }));
jest.mock('@/components/MobileBottomNav', () => ({ MobileBottomNav: () => null }));
jest.mock('@/components/PDFPreviewModal', () => () => null);
jest.mock('@/components/LegalTextRenderer', () => {
  const React = require('react');
  return ({ text }) => React.createElement('div', null, text);
});

jest.mock('lucide-react', () => {
  const React = require('react');
  const Stub = (props) => React.createElement('span', { 'data-testid': props['data-testid'] });
  return new Proxy({}, { get: () => Stub });
});

jest.mock('react-router-dom', () => {
  const React = require('react');
  const nav = jest.fn(); // stable identity — a fresh fn per render would recreate loadMinutes and loop its effect
  return ({
    Link: ({ to, children, ...rest }) => React.createElement('a', { href: to, ...rest }, children),
    Navigate: ({ to }) => React.createElement('span', { 'data-testid': 'navigate' }, to),
    useNavigate: () => nav,
    useParams: () => ({ minutesId: 'min_test_seed' }),
    useSearchParams: () => [new URLSearchParams(), jest.fn()],
    useLocation: () => ({ pathname: '/minutes/min_test_seed', search: '' }),
    Routes: ({ children }) => React.createElement(React.Fragment, null, children),
    Route: () => null,
    default: {},
  });
});

import MinutesDetailPage from '@/pages/MinutesDetailPage';

const okJson = (data) => ({ ok: true, json: async () => data });

describe('MinutesDetailPage save/delete routing', () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockToast.success.mockClear();
    mockToast.error.mockClear();
  });

  test('template minutes PUTs edits to /minutes-templates/{id}', async () => {
    mockFetch.mockImplementation((ep) => {
      if (ep === '/minutes/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          minutes_type: 'general_meeting',
          meeting_date: '2026-11-27',
          participants_text: 'John Smith',
          other_attendees_text: 'Advisor',
          decisions_text: 'Old content',
          created_at: '2026-11-27T00:00:00Z',
          status: 'draft',
          template_type: 'general_meeting',
          template_data: { meeting_date: 'November 27, 2026' },
        }));
      }
      if (ep === '/minutes-templates/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          template_type: 'general_meeting',
          template_data: { meeting_date: 'November 27, 2026', decisions_text: 'New content', participants_text: 'John Smith', other_attendees_text: 'Advisor' },
          status: 'draft',
        }));
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(React.createElement(MinutesDetailPage));
    const editBtn = await screen.findByTestId('edit-minutes-btn');
    fireEvent.click(editBtn);
    const textarea = await screen.findByTestId('minutes-content-textarea');
    fireEvent.change(textarea, { target: { value: 'New content' } });
    fireEvent.click(await screen.findByTestId('save-minutes-btn'));

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(([path, opts]) => opts?.method === 'PUT');
      expect(putCall).toBeTruthy();
      expect(putCall[0]).toBe('/minutes-templates/min_test_seed');
      const parsed = JSON.parse(putCall[1].body);
      expect(parsed.template_data.decisions_text).toBe('New content');
      expect(parsed.template_data.participants_text).toBe('John Smith');
    });
  });

  test('non-template minutes PUTs edits to /minutes/{id}', async () => {
    mockFetch.mockImplementation((ep) => {
      if (ep === '/minutes/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          minutes_type: 'annual',
          meeting_date: '2026-11-27',
          participants_text: 'Jane Doe',
          other_attendees_text: 'CPA',
          decisions_text: 'Old record',
          created_at: '2026-11-27T00:00:00Z',
          status: 'draft',
        }));
      }
      if (ep === '/minutes/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          minutes_type: 'annual',
          meeting_date: '2026-11-27',
          participants_text: 'Jane Doe',
          other_attendees_text: 'CPA',
          decisions_text: 'New record',
          created_at: '2026-11-27T00:00:00Z',
          status: 'draft',
        }));
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    render(React.createElement(MinutesDetailPage));
    fireEvent.click(await screen.findByTestId('edit-minutes-btn'));
    const textarea = await screen.findByTestId('minutes-content-textarea');
    fireEvent.change(textarea, { target: { value: 'New record' } });
    fireEvent.click(await screen.findByTestId('save-minutes-btn'));

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(([path, opts]) => opts?.method === 'PUT');
      expect(putCall).toBeTruthy();
      expect(putCall[0]).toBe('/minutes/min_test_seed');
      const parsed = JSON.parse(putCall[1].body);
      expect(parsed.decisions_text).toBe('New record');
      expect(parsed.template_data).toBeUndefined();
    });
  });

  test('template minutes DELETEs via /minutes-templates/{id}', async () => {
    mockFetch.mockImplementation((ep) => {
      if (ep === '/minutes/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          minutes_type: 'general_meeting',
          meeting_date: '2026-11-27',
          participants_text: '',
          decisions_text: '',
          created_at: '2026-11-27T00:00:00Z',
          status: 'draft',
          template_type: 'general_meeting',
          template_data: {},
        }));
      }
      return Promise.resolve(okJson({}));
    });

    render(React.createElement(MinutesDetailPage));
    fireEvent.click(await screen.findByTestId('delete-minutes-btn'));
    fireEvent.click(await screen.findByTestId('confirm-delete-btn'));

    await waitFor(() => {
      const deleteCall = mockFetch.mock.calls.find(([path, opts]) => opts?.method === 'DELETE');
      expect(deleteCall).toBeTruthy();
      expect(deleteCall[0]).toBe('/minutes-templates/min_test_seed');
    });
  });

  test('non-template minutes DELETEs via /minutes/{id}', async () => {
    mockFetch.mockImplementation((ep) => {
      if (ep === '/minutes/min_test_seed') {
        return Promise.resolve(okJson({
          minutes_id: 'min_test_seed',
          trust_id: 't1',
          minutes_type: 'annual',
          meeting_date: '2026-11-27',
          participants_text: '',
          decisions_text: '',
          created_at: '2026-11-27T00:00:00Z',
          status: 'draft',
        }));
      }
      return Promise.resolve(okJson({}));
    });

    render(React.createElement(MinutesDetailPage));
    fireEvent.click(await screen.findByTestId('delete-minutes-btn'));
    fireEvent.click(await screen.findByTestId('confirm-delete-btn'));

    await waitFor(() => {
      const deleteCall = mockFetch.mock.calls.find(([path, opts]) => opts?.method === 'DELETE');
      expect(deleteCall).toBeTruthy();
      expect(deleteCall[0]).toBe('/minutes/min_test_seed');
    });
  });
});
