import React, { useState } from 'react';
import { format } from 'date-fns';
import {
  Save, X, Plus, Trash2,
  AlertCircle, CheckCircle2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from '@/components/ui/dialog';
import { toast } from 'sonner';
import { showError } from '@/utils/errors';
import { fetchWithAuth } from '@/utils/api';

const PURPOSE_OPTIONS = [
  { value: 'medical', label: 'Medical Expenses' },
  { value: 'housing', label: 'Housing Assistance' },
  { value: 'education', label: 'Education' },
  { value: 'food_necessities', label: 'Food & Necessities' },
  { value: 'utilities', label: 'Utilities' },
  { value: 'transportation', label: 'Transportation' },
  { value: 'emergency', label: 'Emergency Relief' },
  { value: 'spiritual', label: 'Spiritual/Ministry' },
  { value: 'other', label: 'Other' },
];

export function PolicyDraftEditor({ version, onSave, trustId }) {
  const [form, setForm] = useState({
    version_label: version.version_label || '',
    charitable_class: version.charitable_class || '',
    charitable_class_description: version.charitable_class_description || '',
    per_recipient_annual_limit: version.per_recipient_annual_limit || '',
    approval_process: version.approval_process || '',
    approval_threshold: version.approval_threshold || '',
    designated_gift_prohibition: version.designated_gift_prohibition || 'No earmarked contributions for specific individuals will be accepted.',
    employee_benevolence_note: version.employee_benevolence_note || '',
    board_approval_date: version.board_approval_date || '',
    board_approval_reference: version.board_approval_reference || '',
    effective_date: version.effective_date || format(new Date(), 'yyyy-MM-dd'),
    notes: version.notes || '',
  });

  const [eligibilityCriteria, setEligibilityCriteria] = useState(
    (version.eligibility_criteria || []).map(c => ({ ...c }))
  );
  const [assistanceTypes, setAssistanceTypes] = useState(
    (version.assistance_types || []).map(a => ({ ...a }))
  );
  const [committeeMembers, setCommitteeMembers] = useState(
    (version.committee_members || []).map(m => ({ ...m }))
  );
  const [docsReqs, setDocsReqs] = useState(
    (version.documentation_requirements || []).map(d => ({ ...d }))
  );

  const [saving, setSaving] = useState(false);

  const updateForm = (field, value) => setForm(f => ({ ...f, [field]: value }));

  // ----- Helpers for array fields -----
  const addItem = (setter, defaults) => {
    setter(prev => [...prev, { ...defaults }]);
  };

  const updateItem = (setter, index, field, value) => {
    setter(prev => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const removeItem = (setter, index) => {
    setter(prev => prev.filter((_, i) => i !== index));
  };

  // ----- Submit -----
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {
        ...form,
        eligibility_criteria: eligibilityCriteria.map(c => ({
          criterion: c.criterion,
          is_required: c.is_required ?? true,
        })),
        assistance_types: assistanceTypes.map(a => ({
          purpose: a.purpose,
          label: a.label || '',
          is_allowed: a.is_allowed ?? true,
          per_recipient_limit: a.per_recipient_limit ? Number(a.per_recipient_limit) : null,
          per_recipient_period: a.per_recipient_period || null,
          notes: a.notes || '',
        })),
        committee_members: committeeMembers.map(m => ({
          name: m.name || '',
          role: m.role || 'member',
          email: m.email || null,
        })),
        documentation_requirements: docsReqs.map(d => ({
          item: d.item || '',
          is_required: d.is_required ?? true,
        })),
        per_recipient_annual_limit: form.per_recipient_annual_limit ? Number(form.per_recipient_annual_limit) : null,
        approval_threshold: form.approval_threshold ? Number(form.approval_threshold) : null,
      };

      const res = await fetchWithAuth(`/benevolence/policies/versions/${version.policy_version_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to save');
        return;
      }

      toast.success('Draft saved');
      onSave();
    } catch (err) {
      showError(toast, err, { operation: 'save_policy_draft', page: 'BenevolencePolicy', silent: true });
    } finally {
      setSaving(false);
    }
  };

  // ----- Render -----
  return (
    <div className="space-y-6">
      {/* Section 1: Charitable Class */}
      <SectionCard title="§1  Charitable Class & Eligibility">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Charitable Class *</Label>
            <Input
              value={form.charitable_class}
              onChange={e => updateForm('charitable_class', e.target.value)}
              placeholder="e.g. Indigent persons in Hamilton County"
            />
          </div>
          <div className="space-y-1">
            <Label>Description</Label>
            <Input
              value={form.charitable_class_description}
              onChange={e => updateForm('charitable_class_description', e.target.value)}
              placeholder="Broader description of the charitable class"
            />
          </div>
        </div>

        <div className="mt-4">
          <Label className="flex items-center gap-2">
            Eligibility Criteria
            <button
              type="button"
              onClick={() => addItem(setEligibilityCriteria, { criterion: '', is_required: true })}
              className="text-blue-600 hover:text-blue-800 text-sm font-medium"
            >
              <Plus className="h-4 w-4 inline mr-1" /> Add
            </button>
          </Label>
          <div className="space-y-2 mt-2">
            {eligibilityCriteria.map((c, i) => (
              <div key={i} className="flex items-center gap-2 bg-gray-50 rounded px-3 py-2">
                <Input
                  value={c.criterion}
                  onChange={e => updateItem(setEligibilityCriteria, i, 'criterion', e.target.value)}
                  placeholder="Criterion..."
                  className="flex-1"
                />
                <Select
                  value={c.is_required ? 'required' : 'preferred'}
                  onValueChange={v => updateItem(setEligibilityCriteria, i, 'is_required', v === 'required')}
                >
                  <SelectTrigger className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="required">Required</SelectItem>
                    <SelectItem value="preferred">Preferred</SelectItem>
                  </SelectContent>
                </Select>
                <button onClick={() => removeItem(setEligibilityCriteria, i)} className="text-red-400 hover:text-red-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      {/* Section 2: Assistance Types */}
      <SectionCard title="§2  Allowable Assistance Types">
        <div className="mt-2">
          <button
            type="button"
            onClick={() => addItem(setAssistanceTypes, { purpose: 'other', label: '', is_allowed: true })}
            className="text-blue-600 hover:text-blue-800 text-sm font-medium mb-3 inline-flex items-center gap-1"
          >
            <Plus className="h-4 w-4" /> Add type
          </button>
          <div className="space-y-3">
            {assistanceTypes.map((at, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3 space-y-2">
                <div className="flex items-center gap-3">
                  <Select
                    value={at.purpose || 'other'}
                    onValueChange={v => updateItem(setAssistanceTypes, i, 'purpose', v)}
                  >
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PURPOSE_OPTIONS.map(p => (
                        <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Input
                    value={at.label || ''}
                    onChange={e => updateItem(setAssistanceTypes, i, 'label', e.target.value)}
                    placeholder="Display name"
                    className="w-48"
                  />
                  <Select
                    value={at.is_allowed ? 'allowed' : 'excluded'}
                    onValueChange={v => updateItem(setAssistanceTypes, i, 'is_allowed', v === 'allowed')}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="allowed">Allowed</SelectItem>
                      <SelectItem value="excluded">Excluded</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input
                    type="number"
                    value={at.per_recipient_limit || ''}
                    onChange={e => updateItem(setAssistanceTypes, i, 'per_recipient_limit', e.target.value)}
                    placeholder="$/person"
                    className="w-28"
                  />
                  <Select
                    value={at.per_recipient_period || 'per_request'}
                    onValueChange={v => updateItem(setAssistanceTypes, i, 'per_recipient_period', v)}
                    disabled={!at.per_recipient_limit}
                  >
                    <SelectTrigger className="w-28">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="per_request">Per Request</SelectItem>
                      <SelectItem value="annual">Annual</SelectItem>
                      <SelectItem value="lifetime">Lifetime</SelectItem>
                    </SelectContent>
                  </Select>
                  <button onClick={() => removeItem(setAssistanceTypes, i)} className="text-red-400 hover:text-red-600 self-start">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      {/* Section 3: Limits */}
      <SectionCard title="§3  Per-Recipient Limits">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1">
            <Label>Global Annual Limit per Recipient ($)</Label>
            <Input
              type="number"
              value={form.per_recipient_annual_limit || ''}
              onChange={e => updateForm('per_recipient_annual_limit', e.target.value)}
              placeholder="Leave blank for no limit"
            />
          </div>
          <div className="space-y-1">
            <Label>Single-Approver Threshold ($)</Label>
            <Input
              type="number"
              value={form.approval_threshold || ''}
              onChange={e => updateForm('approval_threshold', e.target.value)}
              placeholder="Below this amount = single approver"
            />
          </div>
        </div>
      </SectionCard>

      {/* Section 4: Approval Process */}
      <SectionCard title="§4  Approval Process">
        <div className="space-y-2">
          <Label>Approval Workflow Description</Label>
          <Textarea
            value={form.approval_process}
            onChange={e => updateForm('approval_process', e.target.value)}
            placeholder="Describe the approval process: who approves, how meetings are held, voting requirements..."
            rows={4}
          />
        </div>
      </SectionCard>

      {/* Section 5: Committee */}
      <SectionCard title="§5  Committee Members">
        <div className="mt-2">
          <button
            type="button"
            onClick={() => addItem(setCommitteeMembers, { name: '', role: 'member', email: '' })}
            className="text-blue-600 hover:text-blue-800 text-sm font-medium mb-3 inline-flex items-center gap-1"
          >
            <Plus className="h-4 w-4" /> Add member
          </button>
          <div className="space-y-2">
            {committeeMembers.map((cm, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3 flex items-center gap-2">
                <Input
                  value={cm.name}
                  onChange={e => updateItem(setCommitteeMembers, i, 'name', e.target.value)}
                  placeholder="Name"
                  className="flex-1"
                />
                <Select
                  value={cm.role || 'member'}
                  onValueChange={v => updateItem(setCommitteeMembers, i, 'role', v)}
                >
                  <SelectTrigger className="w-28">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="chair">Chair</SelectItem>
                    <SelectItem value="secretary">Secretary</SelectItem>
                    <SelectItem value="member">Member</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  value={cm.email || ''}
                  onChange={e => updateItem(setCommitteeMembers, i, 'email', e.target.value)}
                  placeholder="Email"
                  type="email"
                  className="w-48"
                />
                <button onClick={() => removeItem(setCommitteeMembers, i)} className="text-red-400 hover:text-red-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      {/* Section 6: Documentation */}
      <SectionCard title="§6  Documentation Requirements">
        <div className="mt-2">
          <button
            type="button"
            onClick={() => addItem(setDocsReqs, { item: '', is_required: true })}
            className="text-blue-600 hover:text-blue-800 text-sm font-medium mb-3 inline-flex items-center gap-1"
          >
            <Plus className="h-4 w-4" /> Add requirement
          </button>
          <div className="space-y-2">
            {docsReqs.map((d, i) => (
              <div key={i} className="bg-gray-50 rounded-lg p-3 flex items-center gap-2">
                <select
                  value={d.is_required ? 'required' : 'optional'}
                  onChange={e => updateItem(setDocsReqs, i, 'is_required', e.target.value === 'required')}
                  className="border rounded px-2 py-1 text-sm"
                >
                  <option value="required">Required</option>
                  <option value="optional">Optional</option>
                </select>
                <Input
                  value={d.item}
                  onChange={e => updateItem(setDocsReqs, i, 'item', e.target.value)}
                  placeholder="e.g. Receipt for medical bill"
                  className="flex-1"
                />
                <button onClick={() => removeItem(setDocsReqs, i)} className="text-red-400 hover:text-red-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </SectionCard>

      {/* Section 7: IRS Compliance */}
      <SectionCard title="§7  Gift Prohibition & Tax Notes">
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Designated Gift Prohibition</Label>
            <Textarea
              value={form.designated_gift_prohibition}
              onChange={e => updateForm('designated_gift_prohibition', e.target.value)}
              rows={2}
            />
            <p className="text-xs text-gray-400">IRS requires that benevolence funds not accept earmarked contributions for specific individuals.</p>
          </div>
          <div className="space-y-1">
            <Label>Employee Benevolence Tax Note (IRC §102 / §139)</Label>
            <Textarea
              value={form.employee_benevolence_note}
              onChange={e => updateForm('employee_benevolence_note', e.target.value)}
              placeholder="Describe tax treatment of employee benevolence payments..."
              rows={2}
            />
          </div>
        </div>
      </SectionCard>

      {/* Section 8: Board Approval */}
      <SectionCard title="§8  Board Approval & Effective Date">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-1">
            <Label>Board Approval Date</Label>
            <Input
              type="date"
              value={form.board_approval_date || ''}
              onChange={e => updateForm('board_approval_date', e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Board Approval Reference</Label>
            <Input
              value={form.board_approval_reference || ''}
              onChange={e => updateForm('board_approval_reference', e.target.value)}
              placeholder="e.g. Minutes ID or reference number"
            />
          </div>
          <div className="space-y-1">
            <Label>Effective Date</Label>
            <Input
              type="date"
              value={form.effective_date || ''}
              onChange={e => updateForm('effective_date', e.target.value)}
            />
          </div>
        </div>
      </SectionCard>

      {/* Section 9: Notes */}
      <SectionCard title="Notes">
        <Textarea
          value={form.notes}
          onChange={e => updateForm('notes', e.target.value)}
          placeholder="Any additional notes about this policy version..."
          rows={3}
        />
      </SectionCard>

      {/* Actions */}
      <div className="flex gap-3 pt-4 border-t">
        <Button onClick={handleSave} disabled={saving} className="min-w-[120px]">
          {saving ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Saving...</> : <><Save className="h-4 w-4 mr-2" /> Save Draft</>}
        </Button>
      </div>
    </div>
  );
}

function SectionCard({ title, children }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-800 mb-4">{title}</h3>
      {children}
    </div>
  );
}