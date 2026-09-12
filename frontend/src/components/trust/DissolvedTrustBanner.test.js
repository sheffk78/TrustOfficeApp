import React from 'react';
import { render, screen } from '@testing-library/react';
import DissolvedTrustBanner, { isTrustDissolved } from '@/components/trust/DissolvedTrustBanner';

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

describe('DissolvedTrustBanner', () => {
  it('renders nothing when no trust is selected', () => {
    const { container } = render(<DissolvedTrustBanner trust={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing for an active trust', () => {
    const { container } = render(<DissolvedTrustBanner trust={{ status: 'active' }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the dissolved banner with date when status is dissolved_archived', () => {
    render(<DissolvedTrustBanner trust={{ status: 'dissolved_archived', dissolved_on: '2026-09-12T00:00:00Z' }} />);
    const banner = screen.getByTestId('dissolved-trust-banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(/Dissolved .* 2026 .* records preserved read-only/i);
  });

  it('isTrustDissolved predicate is true only for dissolved_archived', () => {
    expect(isTrustDissolved({ status: 'dissolved_archived' })).toBe(true);
    expect(isTrustDissolved({ status: 'active' })).toBe(false);
    expect(isTrustDissolved(null)).toBe(false);
  });
});
