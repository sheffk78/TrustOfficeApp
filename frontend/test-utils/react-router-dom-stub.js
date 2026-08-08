// Test stub for react-router-dom (v7 ships ESM-only exports that CRA's Jest
// cannot resolve/transform). Provides the minimal Link used by tested pages.
import React from 'react';

const noop = () => undefined;
export const Link = ({ to, children, ...rest }) => (
  <a href={to} {...rest}>{children}</a>
);

export const Navigate = ({ to }) => <span data-testid="navigate">{to}</span>;
export const useNavigate = () => noop;
export const useParams = () => ({});
export const useSearchParams = () => [new URLSearchParams(), noop];
export const useLocation = () => ({ pathname: '/', search: '' });
export const Routes = ({ children }) => <>{children}</>;
export const Route = () => null;
export default {};
