import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useUpgradeModal } from '@/context/UpgradeModalContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';
import {
  Plus, Download, Upload, FileText,
  AlertCircle, CheckCircle2, Clock,
  Loader2, X, Save, Send,
  Info, ChevronDown, ChevronUp,
  Printer, Trash2, Link2
} from 'lucide-react';
import { format } from 'date-fns';
import { safeFormatDate } from '@/utils/safeDate';
import { PolicyViewTab } from '@/pages/benevolence-policy/PolicyViewTab';
import { PolicyDraftEditor } from '@/pages/benevolence-policy/PolicyDraftEditor';
import { VersionHistoryTab } from '@/pages/benevolence-policy/VersionHistoryTab';
import { ComplianceChecklist } from '@/pages/benevolence-policy/ComplianceChecklist';

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'published', label: 'Published' },
  { value: 'superseded', label: 'Superseded' },
];

export default function BenevolencePolicyPage() {
  const { selectedTrust, isReadOnly } = useAuth();
  const { showUpgradeModal } = useUpgradeModal();
  const [activeTab, setActiveTab] = useState('view'); // 'view' | 'edit' | 'history'
  const [loading, setLoading] = useState(true);
  const [policy, setPolicy] = useState(null);       // policy container
  const [versions, setVersions] = useState([]);
  const [activeVersion, setActiveVersion] = useState(null);
  const [summary, setSummary] = useState(null);

  const trustId = selectedTrust?.trust_id;

  const loadData = useCallback(async () => {
    if (!trustId) return;
    setLoading(true);
    try {
      const [policyRes, versionsRes, summaryRes] = await Promise.all([
        fetchWithAuth(`/benevolence/policies/${trustId}`).catch(() => null),
        fetchWithAuth(`/benevolence/policies/${trustId}/versions`).catch(() => null),
        fetchWithAuth(`/benevolence/summary/${trustId}`).catch(() => null),
      ]);

      const p = policyRes?.ok ? await policyRes.json() : null;
      setPolicy(p);

      if (versionsRes?.ok) {
        const vData = await versionsRes.json();
        setVersions(vData);
        if (p?.current_version_id) {
          const active = vData.find(v => v.policy_version_id === p.current_version_id);
          setActiveVersion(active || null);
        }
      }

      if (summaryRes?.ok) setSummary(await summaryRes.json());
    } catch (err) {
      showError(toast, err, { operation: 'load_benevolence_policy', page: 'BenevolencePolicy', silent: true });
    } finally {
      setLoading(false);
    }
  }, [trustId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCreatePolicy = async () => {
    try {
      const today = format(new Date(), 'yyyy-MM-dd');
      const res = await fetchWithAuth(`/benevolence/policies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trust_id: trustId,
          version_label: '1.0',
          charitable_class: '',
          charitable_class_description: '',
          eligibility_criteria: [],
          assistance_types: [],
          per_recipient_annual_limit: null,
          approval_process: '',
          approval_threshold: null,
          committee_members: [],
          documentation_requirements: [],
          designated_gift_prohibition: 'No earmarked contributions for specific individuals will be accepted.',
          employee_benevolence_note: '',
          effective_date: today,
          notes: '',
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Failed to create policy');
        return;
      }
      toast.success('Policy created successfully');
      loadData();
      setActiveTab('edit');
    } catch (err) {
      showError(toast, err, { operation: 'create_benevolence_policy', page: 'BenevolencePolicy', silent: true });
    }
  };

  const handleAmend = async () => {
    try {
      const res = await fetchWithAuth(`/benevolence/policies/${trustId}/amend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_label: '', notes: '' }),
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Failed to create amendment');
        return;
      }
      toast.success('Draft amendment created');
      await loadData();
      setActiveTab('edit');
    } catch (err) {
      showError(toast, err, { operation: 'amend_benevolence_policy', page: 'BenevolencePolicy', silent: true });
    }
  };

  const handlePublish = async (versionId) => {
    try {
      const res = await fetchWithAuth(`/benevolence/policies/versions/${versionId}/publish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const err = await res.json();
        toast.error(err.detail || 'Failed to publish');
        return;
      }
      toast.success('Policy published successfully');
      loadData();
      setActiveTab('view');
    } catch (err) {
      showError(toast, err, { operation: 'publish_benevolence_policy', page: 'BenevolencePolicy', silent: true });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Benevolence Policy</h1>
          <p className="text-sm text-gray-500 mt-1">
            Create, manage, and publish your written benevolence policy
          </p>
        </div>
        <div className="flex gap-2">
          {activeTab === 'view' && policy && (
            <Button onClick={handleAmend} variant="outline">
              <Plus className="h-4 w-4 mr-2" /> Amend Policy
            </Button>
          )}
          {activeVersion?.status === 'draft' && (
            <Button onClick={() => handlePublish(activeVersion.policy_version_id)}>
              <Send className="h-4 w-4 mr-2" /> Publish v{activeVersion.version_label}
            </Button>
          )}
          {!policy && (
            <Button onClick={handleCreatePolicy}>
              <Plus className="h-4 w-4 mr-2" /> Create Policy
            </Button>
          )}
        </div>
      </div>

      {/* Status Banner */}
      <div className="rounded-lg border p-4 bg-white shadow-sm">
        {!policy ? (
          <div className="flex items-center gap-3 text-amber-600">
            <AlertCircle className="h-5 w-5" />
            <span className="font-medium">No benevolence policy on file.</span>
            <span className="text-sm text-amber-500">
              Creating and publishing a written policy is required for IRS compliance. Click "Create Policy" to get started.
            </span>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-gray-400" />
                <span className="font-medium">Policy v{activeVersion?.version_label || policy.current_version_label}</span>
              </div>
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                activeVersion?.status === 'published'
                  ? 'bg-green-100 text-green-800'
                  : activeVersion?.status === 'draft'
                  ? 'bg-yellow-100 text-yellow-800'
                  : 'bg-gray-100 text-gray-800'
              }`}>
                {activeVersion?.status?.toUpperCase() || policy.current_version_status?.toUpperCase()}
              </span>
              {activeVersion?.published_at && (
                <span className="text-sm text-gray-500">
                  Published {safeFormatDate(activeVersion.published_at, 'MMM d, yyyy')}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setActiveTab(activeTab === 'view' ? 'history' : 'view')}
              >
                {activeTab === 'view' ? 'Version History' : 'Back to View'}
              </Button>
              {activeVersion && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setActiveTab(activeTab === 'view' ? 'edit' : 'view')}
                  disabled={activeVersion.status !== 'draft' && activeTab === 'edit'}
                >
                  {activeTab === 'edit' ? 'View' : 'Edit Draft'}
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                disabled={!activeVersion}
                onClick={() => activeVersion && window.open(`/api/benevolence/policies/${trustId}/export/pdf?version_id=${activeVersion.policy_version_id}`, '_blank')}
                title="Download PDF"
              >
                <Download className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === 'view' && activeVersion && (
        <PolicyViewTab version={activeVersion} summary={summary} />
      )}
      {activeTab === 'edit' && activeVersion?.status === 'draft' && (
        <PolicyDraftEditor
          version={activeVersion}
          onSave={loadData}
          trustId={trustId}
        />
      )}
      {activeTab === 'edit' && activeVersion?.status !== 'draft' && (
        <div className="text-center py-12 text-gray-500">
          <AlertCircle className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">Cannot edit a {activeVersion.status} version</p>
          <p className="text-sm">Create a new draft via "Amend Policy" or view the published version.</p>
        </div>
      )}
      {activeTab === 'history' && (
        <VersionHistoryTab
          versions={versions}
          activeVersionId={policy?.current_version_id}
          onSelectVersion={(v) => {
            setActiveVersion(v);
            setActiveTab('view');
          }}
          trustId={trustId}
        />
      )}

      {/* IRS Compliance Checklist */}
      {activeVersion && (
        <ComplianceChecklist version={activeVersion} />
      )}
    </div>
  );
}