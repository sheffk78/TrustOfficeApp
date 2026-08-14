import React from 'react';

export function PolicyConstants() {
  return {
    PURPOSE_OPTIONS: [
      { value: 'medical', label: 'Medical Expenses' },
      { value: 'housing', label: 'Housing Assistance' },
      { value: 'education', label: 'Education' },
      { value: 'food_necessities', label: 'Food & Necessities' },
      { value: 'utilities', label: 'Utilities' },
      { value: 'transportation', label: 'Transportation' },
      { value: 'emergency', label: 'Emergency Relief' },
      { value: 'spiritual', label: 'Spiritual/Ministry' },
      { value: 'other', label: 'Other' },
    ],

    PERIOD_OPTIONS: [
      { value: 'per_request', label: 'Per Request' },
      { value: 'annual', label: 'Annual' },
      { value: 'lifetime', label: 'Lifetime' },
    ],

    STATUS_LABELS: {
      draft: 'Draft',
      published: 'Published',
      superseded: 'Superseded',
    },

    ROLE_OPTIONS: [
      { value: 'chair', label: 'Chair' },
      { value: 'secretary', label: 'Secretary' },
      { value: 'member', label: 'Member' },
    ],

    DOC_TYPE_OPTIONS: [
      { value: 'bill', label: 'Bill / Invoice' },
      { value: 'receipt', label: 'Receipt' },
      { value: 'lease', label: 'Lease / Rent Agreement' },
      { value: 'medical', label: 'Medical Record' },
      { value: 'legal', label: 'Legal Document' },
      { value: 'tax', label: 'Tax Document' },
      { value: 'other', label: 'Other' },
    ],
  };
}