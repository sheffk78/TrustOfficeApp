/**
 * LeadBookingEmailModal.js — note-aware booking-link email, opened from the
 * lead detail dialog. 2026-09-15 (Jeff, #trustoffice-main).
 *
 * Flow: button click -> GET /admin/notifications/{lead_id}/booking-draft
 *       -> editable preview (subject + body) -> POST .../send-booking-email
 *
 * The backend derives the draft from the lead's notes (voicemail / call recap /
 * topics) and adds source attribution + booking link. Admin can edit before
 * sending. Raw note text is never auto-included - only whitelisted topics.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { Send, Loader2, RefreshCw, Mail } from 'lucide-react';

const SIGNAL_BADGES = {
  voicemail: { label: 'Voicemail follow-up', cls: 'bg-amber-100 text-amber-800' },
  call: { label: 'Call recap follow-up', cls: 'bg-blue-100 text-blue-800' },
  general: { label: 'General follow-up', cls: 'bg-slate-100 text-slate-700' },
};

export default function LeadBookingEmailModal({ lead, open, onClose, onSent }) {
  const [draft, setDraft] = useState(null);
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

  const buildDraft = useCallback(async (leadId) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchWithAuth(`/admin/notifications/${leadId}/booking-draft`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || 'Failed to build draft');
      }
      const data = await res.json();
      setDraft(data);
      setSubject(data.subject || '');
      setBodyHtml(data.body_html || '');
    } catch (e) {
      console.error('Failed to build booking draft:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && lead?.lead_id) {
      buildDraft(lead.lead_id);
    }
  }, [open, lead?.lead_id, buildDraft]);

  const handleSend = async () => {
    if (!subject.trim() || !bodyHtml.trim()) {
      toast.error('Subject and body are required');
      return;
    }
    setSending(true);
    try {
      const res = await fetchWithAuth(`/admin/notifications/${lead.lead_id}/send-booking-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject: subject.trim(), body_html: bodyHtml.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to send');
      }
      toast.success(`Booking email sent to ${lead.email}`);
      onSent?.();
      onClose();
    } catch (e) {
      console.error('Failed to send booking email:', e);
      toast.error(e.message || 'Failed to send');
    } finally {
      setSending(false);
    }
  };

  if (!open) return null;

  const badge = SIGNAL_BADGES[draft?.signal] || SIGNAL_BADGES.general;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-navy-800" />
            Booking email to {lead?.name || lead?.email}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            <span className="ml-3 text-sm text-slate-500">Deriving draft from notes…</span>
          </div>
        ) : error ? (
          <div className="py-6 text-center">
            <p className="text-sm text-red-600 mb-4">{error}</p>
            <Button variant="outline" size="sm" onClick={() => buildDraft(lead.lead_id)}>
              <RefreshCw className="w-4 h-4 mr-2" /> Retry
            </Button>
          </div>
        ) : (
          <>
            {/* Signal + topics summary */}
            <div className="flex flex-wrap items-center gap-2">
              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${badge.cls}`}>
                {badge.label}
              </span>
              {(draft?.topics || []).map((t) => (
                <span key={t} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">
                  {t}
                </span>
              ))}
              {draft?.objection && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700">
                  objection addressed
                </span>
              )}
            </div>

            {/* Editable subject */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-navy-500"
              />
            </div>

            {/* Editable body (HTML source, renders preview below) */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Body</label>
              <textarea
                value={bodyHtml}
                onChange={(e) => setBodyHtml(e.target.value)}
                rows={12}
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-navy-500"
              />
            </div>

            {/* Live preview */}
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Preview</label>
              <div
                className="border border-slate-200 rounded-md p-4 bg-slate-50 text-sm prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: bodyHtml }}
              />
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={sending}>Cancel</Button>
          <Button onClick={handleSend} disabled={sending || loading || !!error}>
            {sending ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Send className="w-4 h-4 mr-2" />}
            Send email
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}