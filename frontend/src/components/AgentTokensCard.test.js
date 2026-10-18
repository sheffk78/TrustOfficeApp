// AgentTokensCard test — token self-serve for the read-only MCP bridge.
//
// Verifies (all network mocked via fetchWithAuth):
//  - empty state renders when there are no agents connected
//  - listing tokens: agent name, hint mask, call counts
//  - issuing: POST /mcp/tokens, raw token shown once with copy button,
//    form hidden while the issued-token panel is up, list reloads after
//  - one-time display: dismissing the panel clears the raw token from the DOM
//  - revocation: two-click confirm flow calls DELETE /mcp/tokens/<id>
//  - API errors show an error message with a retry affordance

import React from 'react';
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import AgentTokensCard from '@/components/AgentTokensCard';

jest.mock('@/utils/api', () => ({
  fetchWithAuth: jest.fn(),
  getErrorMessage: async (res) => {
    try {
      const data = await res.json();
      return data.detail || 'Error';
    } catch {
      return 'Error';
    }
  },
}));
jest.mock('@/utils/errors', () => ({
  showError: jest.fn(),
}));

import { fetchWithAuth } from '@/utils/api';

function okResponse(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

function errResponse(detail, status = 500) {
  return {
    ok: false,
    status,
    json: async () => ({ detail }),
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  // Default: navigator.clipboard exists (jsdom needs the stub).
  Object.assign(navigator, {
    clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
  });
});

test('renders empty state when no agents connected', async () => {
  fetchWithAuth.mockImplementation((endpoint) => {
    expect(endpoint).toBe('/mcp/tokens');
    return Promise.resolve(okResponse({ tokens: [] }));
  });

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-tokens-empty')).toBeTruthy();
  });
  expect(screen.getByTestId('agent-token-form')).toBeTruthy();
  expect(screen.queryByTestId('agent-tokens-list')).toBeNull();
});

test('lists connected agents with hint and usage', async () => {
  fetchWithAuth.mockResolvedValue(
    okResponse({
      tokens: [
        {
          token_id: 'tok_1',
          agent_name: 'Claude',
          token_hint: 'aB3dEf',
          scope: ['read'],
          created_at: new Date(Date.now() - 3600_000).toISOString(),
          last_used_at: new Date(Date.now() - 60_000).toISOString(),
          call_count: 7,
        },
      ],
    })
  );

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-tokens-list')).toBeTruthy();
  });
  const list = screen.getByTestId('agent-tokens-list');
  const row = within(list).getByTestId('agent-token-row');
  expect(row.textContent).toContain('Claude');
  expect(row.textContent).toContain('•••aB3dEf');
  expect(row.textContent).toContain('7 reads');
  expect(screen.queryByTestId('agent-tokens-empty')).toBeNull();
});

test('issue flow: POST, raw token shown once, copy button works', async () => {
  fetchWithAuth.mockImplementation((endpoint, options = {}) => {
    if (endpoint === '/mcp/tokens' && (!options.method || options.method === 'GET')) {
      return Promise.resolve(okResponse({ tokens: [] }));
    }
    if (endpoint === '/mcp/tokens' && options.method === 'POST') {
      const body = JSON.parse(options.body);
      expect(body).toEqual({ agent_name: 'My Jarvis' });
      return Promise.resolve(
        okResponse({
          token: 'toagt_RAWONCE-token-value_123',
          token_id: 'tok_new',
          agent_name: 'My Jarvis',
          scope: ['read'],
          note: 'shown only once',
        })
      );
    }
    return Promise.reject(new Error(`unexpected endpoint ${endpoint}`));
  });

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-token-form')).toBeTruthy();
  });

  fireEvent.change(screen.getByTestId('agent-name-input'), {
    target: { value: 'My Jarvis' },
  });
  fireEvent.click(screen.getByTestId('agent-token-create'));

  await waitFor(() => {
    expect(screen.getByTestId('agent-token-issued')).toBeTruthy();
  });
  const panel = screen.getByTestId('agent-token-issued');
  expect(panel.textContent).toContain('My Jarvis');
  expect(within(panel).getByTestId('agent-token-raw').textContent).toBe(
    'toagt_RAWONCE-token-value_123'
  );
  // Form is hidden while the one-time panel is up (prevents token confusion).
  expect(screen.queryByTestId('agent-token-form')).toBeNull();

  // Copy writes exactly the raw token.
  fireEvent.click(within(panel).getByTestId('agent-token-copy'));
  await waitFor(() => {
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      'toagt_RAWONCE-token-value_123'
    );
  });
});

test('dismiss clears the raw token from the DOM (shown-once contract)', async () => {
  fetchWithAuth.mockResolvedValue(okResponse({ tokens: [] }));

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-token-form')).toBeTruthy();
  });

  fireEvent.change(screen.getByTestId('agent-name-input'), { target: { value: 'X' } });
  fireEvent.click(screen.getByTestId('agent-token-create'));
  await waitFor(() => {
    expect(screen.getByTestId('agent-token-issued')).toBeTruthy();
  });

  fireEvent.click(screen.getByTestId('agent-token-dismiss'));
  expect(screen.queryByTestId('agent-token-issued')).toBeNull();
  expect(document.body.textContent).not.toContain('toagt_');
  // Form returns for the next issuance.
  expect(screen.getByTestId('agent-token-form')).toBeTruthy();
});

test('revoke flow: two-click confirm then DELETE', async () => {
  fetchWithAuth.mockImplementation((endpoint, options = {}) => {
    if (endpoint === '/mcp/tokens' && (!options.method || options.method === 'GET')) {
      return Promise.resolve(
        okResponse({
          tokens: [
            {
              token_id: 'tok_del',
              agent_name: 'Old Agent',
              token_hint: 'xY99zz',
              call_count: 0,
            },
          ],
        })
      );
    }
    if (endpoint === '/mcp/tokens/tok_del' && options.method === 'DELETE') {
      return Promise.resolve(okResponse({ revoked: true, token_id: 'tok_del' }));
    }
    return Promise.reject(new Error(`unexpected endpoint ${endpoint}`));
  });

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-token-row')).toBeTruthy();
  });

  // First click arms the inline confirm; nothing is deleted yet.
  fireEvent.click(screen.getByTestId('agent-token-revoke'));
  expect(fetchWithAuth.mock.calls.filter((c) => c[1] && c[1].method === 'DELETE')).toHaveLength(0);
  await waitFor(() => {
    expect(screen.getByTestId('agent-token-revoke-yes')).toBeTruthy();
  });

  fireEvent.click(screen.getByTestId('agent-token-revoke-yes'));
  await waitFor(() => {
    const deletes = fetchWithAuth.mock.calls.filter(
      (c) => c[0] === '/mcp/tokens/tok_del' && c[1] && c[1].method === 'DELETE'
    );
    expect(deletes).toHaveLength(1);
  });
});

test('API error renders message with retry', async () => {
  fetchWithAuth.mockResolvedValue(errResponse('Subscription required', 403));

  render(<AgentTokensCard />);
  await waitFor(() => {
    expect(screen.getByTestId('agent-tokens-error')).toBeTruthy();
  });
  expect(screen.getByTestId('agent-tokens-error').textContent).toContain('Subscription required');
  expect(screen.getByTestId('agent-tokens-retry')).toBeTruthy();
});