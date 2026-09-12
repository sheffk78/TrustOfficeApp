import React from 'react';
import { render, screen } from '@testing-library/react';
import { getOnboardingProgress } from '@/pages/dashboard/constants';

describe('getOnboardingProgress — backup_connect step', () => {
  const base = {
    trust_doc_uploaded: true,
    beneficiaries_added: true,
    successor_trustee_added: true,
    assets_added: true,
    minutes_generated: true,
    ein_doc_uploaded: true,
    formation_date_added: true,
    ein_entered: true,
    calendar_set: true,
  };

  it('includes the backup_connect step after formation_date', () => {
    const { allSteps } = getOnboardingProgress(base, null);
    const ids = allSteps.map((s) => s.id);
    expect(ids).toContain('backup_connect');
    const idxBackup = ids.indexOf('backup_connect');
    const idxForm = ids.indexOf('formation_date');
    expect(idxBackup).toBeGreaterThan(idxForm);
  });

  it('backup_connect step uses the expected action + field', () => {
    const { allSteps } = getOnboardingProgress(base, null);
    const step = allSteps.find((s) => s.id === 'backup_connect');
    expect(step).toEqual(expect.objectContaining({
      label: 'Connect your off-site backup',
      action: '/vault?tab=vault&focus=backup',
      priority: 7,
      field: 'backup_connected',
    }));
  });

  it('is marked done when onboarding.backup_connected is true', () => {
    const { allSteps, completed, total } = getOnboardingProgress(
      { ...base, backup_connected: true },
      null
    );
    const step = allSteps.find((s) => s.id === 'backup_connect');
    expect(step.done).toBe(true);
    // 10 steps total now (incl. backup_connect)
    expect(total).toBe(10);
    expect(completed).toBe(10);
  });

  it('does not break existing toggles (field names still match backend model)', () => {
    const { allSteps } = getOnboardingProgress(base, null);
    const fields = allSteps.map((s) => s.field);
    // All fields other than the new backup_connected must remain the original
    // OnboardingState fields consumed by toggleOnboardingStep.
    expect(fields).not.toContain(undefined);
    expect(fields).toContain('trust_doc_uploaded');
    expect(fields).toContain('calendar_set');
  });
});
