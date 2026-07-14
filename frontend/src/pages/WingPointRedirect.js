import { useSearchParams, Navigate } from 'react-router-dom';
import WingPointWelcomePage from './WingPointWelcomePage';

/**
 * Smart route handler for /wingpoint.
 * - If action=set_password&token=xxx is present, render the interactive React page (auth flow).
 * - Otherwise, redirect to the marketing site: trustoffice.app/wingpoint/
 */
export default function WingPointRedirect() {
  const [searchParams] = useSearchParams();
  const action = searchParams.get('action');
  const token = searchParams.get('token');

  // Interactive auth flow — keep the React page
  if (action === 'set_password' && token) {
    return <WingPointWelcomePage />;
  }

  // Everyone else — redirect to the marketing page
  // Preserve any other query params (e.g. plan=estate)
  const queryString = searchParams.toString();
  const target = queryString
    ? `https://trustoffice.app/wingpoint/?${queryString}`
    : 'https://trustoffice.app/wingpoint/';

  return <Navigate to={target} replace />;
}
