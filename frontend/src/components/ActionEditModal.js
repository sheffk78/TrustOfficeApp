import React, { useState, useEffect } from 'react';
import { X } from 'lucide-react';

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
};

const ActionEditModal = ({ card, onSave, onCancel }) => {
  const fields = FIELD_DEFS[card.type] || FIELD_DEFS.distribution_preview;
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
    // Convert types for number fields
    const editedData = {};
    fields.forEach((f) => {
      let val = formData[f.key];
      if (val === '' || val === undefined) return;
      if (f.type === 'number') {
        val = parseFloat(val);
        if (isNaN(val)) return;
      }
      if (f.type === 'textarea' && typeof val === 'string') {
        // Store textarea values as-is (could be comma-separated for participants etc.)
        val = val;
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
            Edit {card.type?.replace(/_/g, ' ').replace(' preview', '') || 'Action'}
          </span>
          <button
            onClick={onCancel}
            className="p-1 text-muted-foreground hover:text-navy transition-colors"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Form */}
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
            Save
          </button>
        </div>
      </div>
    </div>
  );
};

export default ActionEditModal;