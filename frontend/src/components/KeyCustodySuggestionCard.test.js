/**
 * KeyCustodySuggestionCard — render + content assertions.
 *
 * Verifies the successor-instructions custody suggestion renders with all
 * three provider options, neutral "options not endorsement" copy, FTC
 * disclosure, and sponsored rel on outbound links.
 *
 * Run: cd frontend && npx craco test --testPathPattern=KeyCustodySuggestionCard
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

import KeyCustodySuggestionCard from '@/components/KeyCustodySuggestionCard';

// Proxy-backed mock so any lucide icon resolves to a stub (same pattern as BankingSummaryCard.test.js).
jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

describe('KeyCustodySuggestionCard', () => {
  it('renders the suggestion tag, headline, and non-custody disclaimer', () => {
    render(<KeyCustodySuggestionCard />);
    expect(screen.getByText(/Suggestion — Key Custody/i)).toBeInTheDocument();
    expect(screen.getByText('Where will your digital keys live?')).toBeInTheDocument();
    expect(screen.getByText(/never stores private keys/i)).toBeInTheDocument();
    expect(screen.getByText(/may receive a commission/i)).toBeInTheDocument();
  });

  it('lists exactly three custody providers with outbound sponsored links', () => {
    render(<KeyCustodySuggestionCard />);
    const links = screen.getAllByRole('link');
    expect(links).toHaveLength(3);

    const hrefs = links.map((a) => a.getAttribute('href'));
    expect(hrefs).toEqual(
      expect.arrayContaining([
        'https://my-legacy.ai/',
        'https://vault12.com/',
        'https://casa.io/inheritance',
      ])
    );

    for (const a of links) {
      expect(a.getAttribute('rel')).toContain('noopener');
      expect(a.getAttribute('rel')).toContain('sponsored');
      expect(a.getAttribute('target')).toBe('_blank');
    }
  });

  it('renders a logo for each provider', () => {
    render(<KeyCustodySuggestionCard />);
    const imgs = screen.getAllByRole('img');
    expect(imgs).toHaveLength(3);
    for (const img of imgs) {
      expect(img.getAttribute('src')).toMatch(/\/assets\/partners\/.+\.png$/);
      expect(img.getAttribute('alt')).toMatch(/logo$/);
    }
  });

  it('carries the integration testid hook', () => {
    render(<KeyCustodySuggestionCard />);
    expect(screen.getByTestId('key-custody-suggestion')).toBeInTheDocument();
  });
});