import React from 'react';
import { format, parseISO } from 'date-fns';
import { Clock, Users, FileText, AlertCircle, CheckCircle2, DollarSign, Shield } from 'lucide-react';

export function PolicyViewTab({ version, summary }) {
  const hasContent = version.charitable_class ||
    version.eligibility_criteria?.length > 0 ||
    version.assistance_types?.length > 0 ||
    version.approval_process ||
    version.committee_members?.length > 0 ||
    version.documentation_requirements?.length > 0;

  if (!hasContent) {
    return (
      <div className="text-center py-12 text-gray-400">
        <FileText className="h-12 w-12 mx-auto mb-3" />
        <p>No policy content yet. Edit this draft to add policy details.</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Charitable Class */}
      <Section title="Charitable Class & Purpose" icon={Shield}>
        <p className="text-gray-700">{version.charitable_class || '<em>Not specified</em>'}</p>
        {version.charitable_class_description && (
          <p className="text-sm text-gray-500 mt-1">{version.charitable_class_description}</p>
        )}
      </Section>

      {/* Eligibility Criteria */}
      {version.eligibility_criteria?.length > 0 && (
        <Section title="Eligibility Criteria" icon={CheckCircle2}>
          <ul className="space-y-2">
            {version.eligibility_criteria.map((c, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className={`mt-0.5 h-4 w-4 rounded border flex items-center justify-center text-xs font-bold ${
                  c.is_required ? 'bg-blue-50 border-blue-500 text-blue-700' : 'bg-gray-50 border-gray-300 text-gray-500'
                }`}>
                  {c.is_required ? 'R' : 'P'}
                </span>
                <span>{c.criterion}</span>
              </li>
            ))}
          </ul>
          <p className="text-xs text-gray-400 mt-2 italic">R = Required, P = Preferred</p>
        </Section>
      )}

      {/* Assistance Types */}
      {version.assistance_types?.length > 0 && (
        <Section title="Allowable Assistance Types" icon={DollarSign}>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Purpose</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Label</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Status</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Limit</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {version.assistance_types.map((at, i) => (
                  <tr key={i} className={!at.is_allowed ? 'bg-red-50' : ''}>
                    <td className="px-3 py-2">{at.purpose}</td>
                    <td className="px-3 py-2">{at.label || '—'}</td>
                    <td className="px-3 py-2">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                        at.is_allowed
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}>
                        {at.is_allowed ? 'Allowed' : 'Excluded'}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      {at.per_recipient_limit
                        ? `$${Number(at.per_recipient_limit).toLocaleString()} / ${at.per_recipient_period || 'request'}`
                        : 'No limit'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* Per-Recipient Limits */}
      {version.per_recipient_annual_limit && (
        <Section title="Global Per-Recipient Limit" icon={DollarSign}>
          <p className="text-gray-700">
            ${Number(version.per_recipient_annual_limit).toLocaleString()} per recipient per year
          </p>
        </Section>
      )}

      {/* Approval Process */}
      {version.approval_process && (
        <Section title="Approval Process" icon={Users}>
          <p className="text-gray-700 whitespace-pre-wrap">{version.approval_process}</p>
          {version.approval_threshold && (
            <p className="text-sm text-gray-500 mt-2">
              Single-approver threshold: ${Number(version.approval_threshold).toLocaleString()}
            </p>
          )}
        </Section>
      )}

      {/* Committee */}
      {version.committee_members?.length > 0 && (
        <Section title="Committee Members" icon={Users}>
          <div className="space-y-2">
            {version.committee_members.map((cm, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-gray-700 bg-gray-50 rounded px-3 py-2">
                <span className="font-medium">{cm.name}</span>
                <span className="text-gray-400">—</span>
                <span className="text-gray-500">{cm.role || 'member'}</span>
                {cm.email && <span className="text-gray-400">({cm.email})</span>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Documentation */}
      {version.documentation_requirements?.length > 0 && (
        <Section title="Documentation Requirements" icon={FileText}>
          <ul className="space-y-1">
            {version.documentation_requirements.map((dr, i) => (
              <li key={i} className="flex items-center gap-2 text-sm text-gray-700">
                <span className={`text-xs font-bold ${
                  dr.is_required ? 'text-red-600' : 'text-gray-400'
                }`}>[{dr.is_required ? 'Required' : 'Optional'}]</span>
                <span>{dr.item}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Gift Prohibition */}
      {version.designated_gift_prohibition && (
        <Section title="Designated Gift Prohibition" icon={AlertCircle}>
          <p className="text-gray-700 text-sm">{version.designated_gift_prohibition}</p>
        </Section>
      )}

      {/* Employee Benevolence */}
      {version.employee_benevolence_note && (
        <Section title="Employee Benevolence (IRC §102 / §139)" icon={FileText}>
          <p className="text-gray-700 text-sm">{version.employee_benevolence_note}</p>
        </Section>
      )}

      {/* Board Approval */}
      <Section title="Board Approval" icon={CheckCircle2}>
        <div className="text-sm text-gray-700 space-y-1">
          <p>Date: {version.board_approval_date || 'Not recorded'}</p>
          <p>Reference: {version.board_approval_reference || 'Not recorded'}</p>
          <p>Effective Date: {version.effective_date || 'Not specified'}</p>
        </div>
      </Section>

      {/* Summary Stats */}
      {summary && (
        <Section title="Benevolence Activity Summary" icon={DollarSign}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-blue-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-blue-700">{summary.total_count || 0}</div>
              <div className="text-xs text-blue-600">Total Grants</div>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-700">${summary.total_amount ? Number(summary.total_amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'}</div>
              <div className="text-xs text-green-600">Total Disbursed</div>
            </div>
          </div>
        </Section>
      )}
    </div>
  );
}

function Section({ title, icon: Icon, children }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-5 w-5 text-blue-600" />
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
      </div>
      {children}
    </div>
  );
}