import React from 'react';
import { render, screen } from '@testing-library/react';
import ActionCard from '@/components/ActionCard';

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  useNavigate: () => jest.fn(),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), jest.fn()],
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
  default: {},
}));

describe('ActionCard execution_result link', () => {
  it('renders a working link to the created record when execution_result carries one', () => {
    render(
      <ActionCard
        card={{
          type: 'minutes_preview',
          data: { minutes_type: 'quarterly' },
          status: 'approved',
          execution_result: {
            success: true,
            record_id: 'min_abc123',
            endpoint: 'minutes',
            endpoint_type: 'minutes',
          },
        }}
      />
    );

    const link = screen.getByRole('link', { name: /view in minutes/i });
    expect(link.getAttribute('href')).toBe('/minutes/min_abc123');
    expect(screen.getByText(/record created/i)).toBeInTheDocument();
  });

  it('shows the plain failure text and no link when execution_result failed', () => {
    render(
      <ActionCard
        card={{
          type: 'minutes_preview',
          data: {},
          status: 'pending',
          execution_result: {
            success: false,
            error: 'record not found after write',
          },
        }}
      />
    );

    expect(screen.getByText(/failed/i)).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });
});
