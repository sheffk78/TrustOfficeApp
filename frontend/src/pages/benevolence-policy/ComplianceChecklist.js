import React from 'react';
import { CheckCircle2, AlertCircle, XCircle } from 'lucide-react';

const REQUIREMENTS = [
  {
    key: 'charitable_class',
    label: 'Charitable class defined',
    detail: 'A clearly defined class of beneficiaries who may receive assistance',
    field: 'charitable_class',
  },
  {
    key: 'eligibility_criteria',
    label: 'Eligibility criteria specified',
    detail: 'Objective criteria for determining who qualifies for assistance',
    field: 'eligibility_criteria',
  },
  {
    key: 'assistance_types',
    label: 'Types of assistance defined',
    detail: 'Allowable and excluded categories of benevolence assistance',
    field: 'assistance_types',
  },
  {
    key: 'approval_process',
    label: 'Approval process documented',
    detail: 'Written description of how distributions are approved',
    field: 'approval_process',
  },
  {
    key: 'committee_members',
    label: 'Review committee established',
    detail: 'At least 2 individuals designated to review requests',
    field: 'committee_members',
  },
  {
    key: 'documentation_requirements',
    label: 'Documentation requirements',
    detail: 'What supporting documents are required for requests',
    field: 'documentation_requirements',
  },
  {
    key: 'designated_gift_prohibition',
    label: 'Designated gift prohibition',
    detail: 'Policy prohibits earmarking contributions for specific individuals',
    field: 'designated_gift_prohibition',
  },
  {
    key: 'employee_benevolence_note',
    label: 'Employee tax treatment noted',
    detail: 'Policy addresses IRC §102 taxability of employee benevolence',
    field: 'employee_benevolence_note',
  },
  {
    key: 'per_recipient_annual_limit',
    label: 'Per-recipient limits set',
    detail: 'Maximum amounts individuals can receive are defined',
    field: 'per_recipient_annual_limit',
  },
  {
    key: 'board_approval_date',
    label: 'Board approval recorded',
    detail: 'Date of board approval is documented',
    field: 'board_approval_date',
  },
  {
    key: 'effective_date',
    label: 'Effective date set',
    detail: 'Date the policy takes effect is specified',
    field: 'effective_date',
  },
];

export function ComplianceChecklist({ version }) {
  if (!version) return null;

  const results = REQUIREMENTS.map(req => {
    const val = version[req.field];
    let status = 'ok';
    let detail = '';

    if (req.field === 'charitable_class') {
      if (!val) { status = 'warn'; detail = 'Required for IRS compliance'; }
    } else if (req.field === 'eligibility_criteria') {
      if (!val || val.length === 0) { status = 'warn'; detail = 'Define who qualifies'; }
    } else if (req.field === 'assistance_types') {
      if (!val || val.length === 0) { status = 'warn'; detail = 'Specify covered/excluded types'; }
      else {
        const hasAllowed = val.some(a => a.is_allowed);
        const hasExcluded = val.some(a => !a.is_allowed);
        if (!hasExcluded) { status = 'warn'; detail = 'Consider specifying excluded types'; }
        else if (hasAllowed) { status = 'ok'; }
      }
    } else if (req.field === 'approval_process') {
      if (!val || val.length < 10) { status = 'warn'; detail = 'Describe the workflow'; }
    } else if (req.field === 'committee_members') {
      if (!val || val.length < 2) { status = 'warn'; detail = 'Need at least 2 reviewers'; }
      else { status = 'ok'; }
    } else if (req.field === 'documentation_requirements') {
      if (!val || val.length === 0) { status = 'info'; detail = 'Recommended but not required'; }
    } else if (req.field === 'designated_gift_prohibition') {
      if (!val) { status = 'warn'; detail = 'Required by IRS'; }
    } else if (req.field === 'employee_benevolence_note') {
      if (!val) { status = 'info'; detail = 'Recommended to address §102/§139'; }
    } else if (req.field === 'per_recipient_annual_limit') {
      if (!val) { status = 'info'; detail = 'Recommended for fiscal control'; }
    } else if (req.field === 'board_approval_date') {
      if (!val) { status = 'warn'; detail = 'Needed for published version'; }
    } else if (req.field === 'effective_date') {
      if (!val) { status = 'info'; detail = 'Recommended'; }
    }

    return { ...req, status, detail };
  });

  const okCount = results.filter(r => r.status === 'ok').length;
  const warnCount = results.filter(r => r.status === 'warn').length;
  const infoCount = results.filter(r => r.status === 'info').length;

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-800 flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5 text-blue-600" />
          IRS Compliance Checklist
        </h3>
        <div className="flex gap-4 text-xs">
          <span className="text-green-600 font-medium">{okCount} met</span>
          {warnCount > 0 && <span className="text-amber-600 font-medium">{warnCount} warnings</span>}
          {infoCount > 0 && <span className="text-gray-400">{infoCount} suggestions</span>}
        </div>
      </div>

      <div className="space-y-2">
        {results.map(r => (
          <div
            key={r.key}
            className={`flex items-start gap-3 p-2 rounded ${
              r.status === 'ok' ? 'bg-green-50/50' :
              r.status === 'warn' ? 'bg-amber-50' :
              'bg-gray-50/50'
            }`}
          >
            {r.status === 'ok' ? (
              <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5 flex-shrink-0" />
            ) : r.status === 'warn' ? (
              <AlertCircle className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
            ) : (
              <XCircle className="h-4 w-4 text-gray-400 mt-0.5 flex-shrink-0 opacity-50" />
            )}
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-800">{r.label}</div>
              {r.detail && <div className="text-xs text-gray-500 mt-0.5">{typeof r.detail === 'string' ? r.detail : 'Consider specifying excluded types'}</div>}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t text-xs text-gray-400">
        This checklist highlights common IRS compliance areas. It is not legal advice — consult
        a qualified attorney or CPA for formal compliance guidance.
      </div>
    </div>
  );
}