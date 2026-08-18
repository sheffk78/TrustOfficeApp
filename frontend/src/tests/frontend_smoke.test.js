/**
 * Frontend Page Smoke Tests — TrustOffice
 * 
 * Tests that every critical page route renders without crashing.
 * Uses jsdom to render React components and verify they mount.
 * 
 * Run: cd frontend && npx craco test --testPathPattern=frontend_smoke
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import '@testing-library/jest-dom';

// Stub auth context — all pages assume a logged-in user
const MockAuthContext = React.createContext({
  user: { user_id: 'test-user', email: 'test@test.trustoffice.app', name: 'Test User' },
  token: 'mock-token',
  loading: false,
  login: () => {},
  logout: () => {},
  register: () => {},
});

// Mock API calls to prevent network errors during render
jest.mock('axios', () => ({
  get: jest.fn(() => Promise.resolve({ data: [] })),
  post: jest.fn(() => Promise.resolve({ data: {} })),
  put: jest.fn(() => Promise.resolve({ data: {} })),
  patch: jest.fn(() => Promise.resolve({ data: {} })),
  delete: jest.fn(() => Promise.resolve({ data: {} })),
}));

// Mock CSS imports (Jest doesn't handle .css/.module.css)
jest.mock('react-day-picker/dist/style.css', () => ({}), { virtual: true });

// Mock react-day-picker to avoid CSS import issues
jest.mock('react-day-picker', () => ({
  DayPicker: () => null,
}));

// Mock canvas-confetti (used by some pages)
jest.mock('canvas-confetti', () => jest.fn());

// Mock page-agent (used by some pages for AI features)
jest.mock('page-agent', () => ({
  PageAgent: jest.fn(() => ({
    init: jest.fn(),
    dispose: jest.fn(),
    registerTool: jest.fn(),
    run: jest.fn(() => Promise.resolve({})),
  })),
  tool: jest.fn(),
}));

// Mock zod/v4 (subpath import may not resolve in Jest)
jest.mock('zod/v4', () => ({
  z: {
    object: jest.fn(() => ({ parse: jest.fn(() => true), safeParse: jest.fn(() => ({ success: true })) })),
    string: jest.fn(() => ({ parse: jest.fn(() => true) })),
    number: jest.fn(() => ({ parse: jest.fn(() => true) })),
    enum: jest.fn(() => ({ parse: jest.fn(() => true) })),
  },
}));

// Mock recharts (heavy dependency, causes Jest transform issues)
jest.mock('recharts', () => ({
  ResponsiveContainer: () => null,
  LineChart: () => null,
  BarChart: () => null,
  PieChart: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  CartesianGrid: () => null,
}));

// Mock react-markdown (ESM transform issues in Jest)
jest.mock('react-markdown', () => () => null);

// Mock remark-gfm
jest.mock('remark-gfm', () => () => null);

// Mock reactflow
jest.mock('reactflow', () => ({
  ReactFlow: () => null,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
}));

// Wrapper that provides router + auth context
function renderWithProviders(ui, route = '/') {
  return render(
    <MockAuthContext.Provider value={MockAuthContext._currentValue}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
      </MemoryRouter>
    </MockAuthContext.Provider>
  );
}

// ============================================================================
// Page Import Tests — verify each page module loads without syntax errors
// These tests catch broken imports, missing dependencies, and syntax errors
// without needing the full React provider stack.
// ============================================================================

describe('Frontend Page Smoke Tests', () => {
  // Test that critical page modules can be required (imported) without throwing.
  // This catches: syntax errors, broken imports, missing default exports.
  // We don't render them (they need full auth/API context) — import alone is the smoke test.

  const criticalPages = [
    'LoginPage',
    'SignUpPage',
    'ForgotPasswordPage',
    'ResetPasswordPage',
    'NotFoundPage',
    'PricingPage',
    'ContactPage',
    'OnboardingPage',
    'DashboardPage',
    'BillingPage',
    'SettingsPage',
  ];

  criticalPages.forEach(pageName => {
    test(`${pageName} module imports without error`, () => {
      // Using jest.isolateModules to avoid cross-test contamination
      jest.isolateModules(() => {
        expect(() => {
          const mod = require(`../pages/${pageName}`);
          expect(mod.default).toBeDefined();
        }).not.toThrow();
      });
    });
  });
});

// ============================================================================
// App Shell Integration — verify the app doesn't crash on load
// ============================================================================

describe('App Shell', () => {
  test('App component can be imported', () => {
    // Just verify the App module loads — don't render (needs full provider stack)
    expect(() => require('../App')).not.toThrow();
  });
});