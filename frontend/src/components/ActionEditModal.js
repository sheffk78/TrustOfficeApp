import React, { useState, useEffect } from 'react';
import { X, AlertTriangle } from 'lucide-react';

const FIELD_DEFS = {
  distribution_preview: [
    { key: 'beneficiary_name', label: 'Beneficiary Name', type: 'text' },
    { key: 'amount', label: 'Amount', type: 'number' },
    { key: 'purpose', label: 'Purpose', type: 'text' },
    { key: 'date', label: 'Date', type: 'date' },
  ],
  asset_preview: [
    { key: 'description', label: 'Description', type: 'text' },
    { key: 'value', label: 'Value', type: 'number' },
    { key: 'asset_type', label: 'Asset Type', type: 'text' },
    { key: 'date_acquired', label: 'Date Acquired', type: 'date' },
  ],
  minutes_preview: [
    { key: 'minutes_type', label: 'Minutes Type', type: 'text' },
    { key: 'meeting_date', label: 'Meeting Date', type: 'date' },
    { key: 'participants', label: 'Participants', type: 'textarea' },
    { key: 'decisions', label: 'Decisions', type: 'textarea' },
  ],
  beneficiary_preview: [
    { key: 'name', label: 'Name', type: 'text' },
    { key: 'email', label: 'Email', type: 'email' },
    { key: 'phone', label: 'Phone', type: 'tel' },
    { key: 'allocation_pct', label: 'Allocation %', type: 'number' },
  ],
  beneficiary_update_preview: [
    { key: 'beneficiary_name', label: 'Current Name', type: 'text' },
    { key: 'email', label: 'New Email', type: 'email' },
    { key: 'phone', label: 'New Phone', type: 'tel' },
    { key: 'notes', label: 'Notes', type: 'textarea' },
  ],
  beneficiary_removal_preview: [
    { key: 'beneficiary_name', label: 'Beneficiary Name', type: 'text' },
    { key: 'reason', label: 'Reason for Removal', type: 'text' },
  ],
  certificate_preview: [
    { key: 'beneficiary_name', label: 'Beneficiary Name', type: 'text' },
    { key: 'email', label: 'Email (leave blank to use email on file)', type: 'email' },
    { key: 'notes', label: 'Personal Note (optional)', type: 'textarea' },
  ],
  distribution_cancel_preview: [
    { key: 'beneficiary_name', label: 'Beneficiary Name', type: 'text' },
    { key: 'amount', label: 'Amount', type: 'number' },
    { key: 'date', label: 'Date', type: 'date' },
  ],
  document_upload_preview: [
    { key: 'title', label: 'Document Title', type: 'text' },
    { key: 'category', label: 'Category', type: 'text' },
    { key: 'notes', label: 'Notes', type: 'textarea' },
  ],
  compensation_plan_preview: [
    { key: 'trustee_name', label: 'Trustee Name', type: 'text' },
    { key: 'amount', label: 'Amount', type: 'number' },
    { key: 'frequency', label: 'Frequency (monthly/quarterly/annually/per_meeting)', type: 'text' },
    { key: 'effective_date', label: 'Effective Date', type: 'date' },
  ],
  task_preview: [
    { key: 'task_type', label: 'Task Type', type: 'text' },
    { key: 'description', label: 'Description', type: 'textarea' },
    { key: 'due_date', label: 'Due Date', type: 'date' },
    { key: 'priority', label: 'Priority (normal/high/critical)', type: 'text' },
  ],
  transaction_preview: [
    { key: 'type', label: 'Type (income/expense/transfer)', type: 'text' },
    { key: 'amount', label: 'Amount', type: 'number' },
    { key: 'category', label: 'Category', type: 'text' },
    { key: 'date', label: 'Date', type: 'date' },
    { key: 'description', label: 'Description', type: 'text' },
  ],
  settings_update_preview: [
    { key: 'field', label: 'Field to Update', type: 'text' },
    { key: 'value', label: 'New Value', type: 'text' },
  ],
};

// Confirmation-only types (show warning, no editable form)
const CONFIRMATION_ONLY_TYPES = [
  'beneficiary_removal_preview',
  'distribution_cancel_preview',
  'alert_dismiss',
];

const ActionEditModal = ({ card, onSave, onCancel }) => {
  const fields = FIELD_DEFS[card.type] || [];
  const isConfirmationOnly = CONFIRMATION_ONLY_TYPES.includes(card.type);
  const [formData, setFormData] = useState({});

  useEffect(() => {
    // Pre-populate from card.data
    const initial = {};
    fields.forEach((f) => {
      const raw = card.data?.[f.key];
      if (raw !== undefined && raw !== null) {
        initial[f.key] = Array.isArray(raw) ? raw.join(', ') : String(raw);
      } else {
        initial[f.key] = '';
      }
    });
    setFormData(initial);
  }, [card, fields]);

  const handleChange = (key, value) => {
    setFormData((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    if (isConfirmationOnly) {
      // For confirmation-only actions, just confirm with the existing data
      onSave(card, card.data || {});
      return;
    }
    // Convert types for number fields
    const editedData = {};
    fields.forEach((f) => {
      let val = formData[f.key];
      if (val === '' || val === undefined) return;
      if (f.type === 'number') {
        val = parseFloat(val);
        if (isNaN(val)) return;
      }
      editedData[f.key] = val;
    });
    onSave(card, editedData);
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onCancel();
    }
  };

  // Confirmation-only banner text
  const getConfirmationMessage = () => {
    switch (card.type) {
      case 'beneficiary_removal_preview':
        return `This will permanently remove ${card.data?.beneficiary_name || 'this beneficiary'} from the trust. This action cannot be undone.`;
      case 'distribution_cancel_preview':
        return `This will cancel the distribution${card.data?.amount ? ` for $${card.data.amount}` : ''}${card.data?.beneficiary_name ? ` to ${card.data.beneficiary_name}` : ''}.`;
      case 'alert_dismiss':
        return `This will dismiss the "${card.data?.criterion_name || 'selected'}" insight.`;
      default:
        return 'Are you sure you want to proceed?';
    }
  };

  const getTypeLabel = () => {
    switch (card.type) {
      case 'beneficiary_update_preview': return 'Update Beneficiary';
      case 'beneficiary_removal_preview': return 'Remove Beneficiary';
      case 'certificate_preview': return 'Send Certificate';
      case 'distribution_cancel_preview': return 'Cancel Distribution';
      case 'document_upload_preview': return 'Upload Document';
      case 'compensation_plan_preview': return 'Set Up Compensation';
      case 'task_preview': return 'Schedule Task';
      case 'transaction_preview': return 'Log Transaction';
      case 'settings_update_preview': return 'Update Settings';
      default: return card.type?.replace(/_/g, ' ').replace(' preview', '') || 'Action';
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={handleBackdropClick}
    >
      <div
        className="bg-white border border-navy/20 w-full max-w-md mx-4 shadow-xl"
        style={{ borderRadius: 0 }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-navy/10 bg-navy/5">
          <span className="font-mono text-xs uppercase tracking-wider text-navy">
            {isConfirmationOnly ? 'Confirm' : 'Edit'} {getTypeLabel()}
          </span>
          <button
            onClick={onCancel}
            className="p-1 text-muted-foreground hover:text-navy transition-colors"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Confirmation-only warning banner */}
        {isConfirmationOnly && (
          <div className="px-5 py-4 bg-rust/5 border-b border-rust/20 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rust flex-shrink-0 mt-0.5" />
            <p className="text-sm text-rust">{getConfirmationMessage()}</p>
          </div>
        )}

        {/* Form fields (hidden for confirmation-only) */}
        {!isConfirmationOnly && fields.length > 0 && (
          <div className="px-5 py-4 space-y-4">
            {fields.map((f) => (
              <div key={f.key}>
                <label
                  htmlFor={`edit-${f.key}`}
                  className="block font-mono text-[10px] uppercase tracking-wider text-muted-foreground mb-1"
                >
                  {f.label}
                </label>
                {f.type === 'textarea' ? (
                  <textarea
                    id={`edit-${f.key}`}
                    value={formData[f.key] || ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                    rows={3}
                    className="w-full border border-gold/30 px-3 py-2 font-serif text-sm text-navy bg-white focus:outline-none focus:border-gold transition-colors resize-none"
                    style={{ borderRadius: 0 }}
                  />
                ) : (
                  <input
                    id={`edit-${f.key}`}
                    type={f.type}
                    value={formData[f.key] || ''}
                    onChange={(e) => handleChange(f.key, e.target.value)}
                    className="w-full border border-gold/30 px-3 py-2 font-serif text-sm text-navy bg-white focus:outline-none focus:border-gold transition-colors"
                    style={{ borderRadius: 0 }}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-5 py-3 border-t border-navy/10">
          <button
            onClick={onCancel}
            className="px-4 py-2 font-mono text-[10px] uppercase tracking-wider border border-navy/20 text-navy bg-navy/5 hover:bg-navy/10 transition-colors"
            style={{ borderRadius: 0 }}
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 font-mono text-[10px] uppercase tracking-writer border border-gold bg-gold text-navy hover:bg-gold/90 transition-colors"
            style={{ borderRadius: 0 }}
          >
            {isConfirmationOnly ? 'Confirm' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ActionEditModal;