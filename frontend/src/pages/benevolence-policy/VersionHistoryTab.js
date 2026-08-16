import React from 'react';
import { safeFormatDate } from '@/utils/safeDate';
import { Clock, FileText, CheckCircle2, AlertCircle, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function VersionHistoryTab({ versions, activeVersionId, onSelectVersion, trustId }) {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Version</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Effective</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Published</th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Supersedes</th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {versions.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  No policy versions found. Create a policy to get started.
                </td>
              </tr>
            ) : (
              versions.map(v => (
                <tr
                  key={v.policy_version_id}
                  className={`cursor-pointer hover:bg-blue-50 ${v.policy_version_id === activeVersionId ? 'bg-blue-50' : ''}`}
                  onClick={() => onSelectVersion(v)}
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-sm text-gray-900">v{v.version_label}</div>
                    <div className="text-xs text-gray-500">#{v.version_number}</div>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={v.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {safeFormatDate(v.effective_date, 'MMM d, yyyy', '—')}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {safeFormatDate(v.published_at, 'MMM d, yyyy', '—')}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {v.supersedes_version_id ? 'v' + getVersionLabel(versions, v.supersedes_version_id) : '—'}
                  </td>
                  <td className="px-4 py-3 text-right text-sm font-medium space-x-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={(e) => { e.stopPropagation(); window.open(`/api/benevolence/policies/${trustId}/export/pdf?version_id=${v.policy_version_id}`, '_blank'); }}
                      title="Download PDF"
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                    {v.status === 'published' && (
                      <Button variant="ghost" size="sm" title="View (current)">
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                      </Button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }) {
  const styles = {
    draft: { bg: 'bg-yellow-100', text: 'text-yellow-800', label: 'Draft' },
    published: { bg: 'bg-green-100', text: 'text-green-800', label: 'Published' },
    superseded: { bg: 'bg-gray-100', text: 'text-gray-800', label: 'Superseded' },
  };
  const s = styles[status] || styles.draft;
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}

function getVersionLabel(versions, versionId) {
  const v = versions.find(x => x.policy_version_id === versionId);
  return v ? v.version_label : '?';
}