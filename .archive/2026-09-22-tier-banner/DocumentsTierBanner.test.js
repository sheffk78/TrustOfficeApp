import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import DocumentsTierBanner from '@/components/documents/DocumentsTierBanner';

const mockSetSearchParams = jest.fn();

jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
  Navigate: ({ to }) => <span data-testid="navigate">{to}</span>,
  useNavigate: () => jest.fn(),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), mockSetSearchParams],
  useLocation: () => ({ pathname: '/', search: '' }),
  Routes: ({ children }) => <>{children}</>,
  Route: () => null,
  default: {},
}));

jest.mock('lucide-react', () => {
  const Stub = (props) => <span data-testid="icon" {...props} />;
  return new Proxy({}, { get: () => Stub });
});

describe('DocumentsTierBanner', () => {
  beforeEach(() => { jest.clearAllMocks(); });

  it('renders the three-tier strip', () => {
    render(<DocumentsTierBanner />);
    expect(screen.getByTestId('documents-tier-banner')).toBeInTheDocument();
    expect(screen.getByTestId('tier-banner-1')).toHaveTextContent('TrustOffice (this vault)');
    expect(screen.getByTestId('tier-banner-2')).toHaveTextContent('Printed Record Book');
    expect(screen.getByTestId('tier-banner-3')).toHaveTextContent('Your own cloud backup');
  });

  it('clicking Record Book switches to the binder tab', () => {
    render(<DocumentsTierBanner />);
    fireEvent.click(screen.getByTestId('tier-banner-2'));
    expect(mockSetSearchParams).toHaveBeenCalledWith({ tab: 'binder' });
  });

  it('clicking cloud backup focuses backup (tab=vault&focus=backup)', () => {
    render(<DocumentsTierBanner />);
    fireEvent.click(screen.getByTestId('tier-banner-3'));
    expect(mockSetSearchParams).toHaveBeenCalledWith({ tab: 'vault', focus: 'backup' });
  });
});
