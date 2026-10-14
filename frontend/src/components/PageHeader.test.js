import React from 'react';
import { render } from '@testing-library/react';
import { PageHelpProvider } from '@/context/PageHelpContext';
import PageHeader from '@/components/PageHeader';
import Spinner from '@/components/Spinner';

// NOTE: build instrumentation wraps text nodes in display:contents spans,
// so assert structure (querySelector/textContent), not getByText classes.
test('PageHeader renders title, subtitle, and action node', () => {
  const { container } = render(
    <PageHelpProvider>
      <PageHeader title="Distributions" subtitle="Record and manage" actions={<button>x</button>} />
    </PageHelpProvider>
  );
  const header = container.querySelector('.page-header');
  expect(header).not.toBeNull();
  expect(header.querySelector('.page-title').textContent).toContain('Distributions');
  expect(header.querySelector('.page-subtitle').textContent).toContain('Record and manage');
  expect(header.querySelector('button')).not.toBeNull();
});

test('PageHeader omits subtitle and action block when absent', () => {
  const { container } = render(
    <PageHelpProvider>
      <PageHeader title="Calendar" />
    </PageHelpProvider>
  );
  expect(container.querySelector('.page-title').textContent).toContain('Calendar');
  expect(container.querySelector('.page-subtitle')).toBeNull();
  expect(container.querySelector('.page-header .flex.items-center')).toBeNull();
});

test('Spinner renders accessible status with size style', () => {
  const { container } = render(<Spinner size={20} label="Loading trusts" />);
  const el = container.querySelector('[role="status"]');
  expect(el.getAttribute('aria-label')).toBe('Loading trusts');
  expect(el.style.width).toBe('20px');
  expect(el.className).toContain('animate-spin');
});