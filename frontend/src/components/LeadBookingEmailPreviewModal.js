/**
 * LeadBookingEmailPreviewModal.js — designed preview of the note-derived
 * booking email, opened from the lead detail dialog. 2026-09-15 (Jeff,
 * #trustoffice-main): "when I click send booking email I actually get to
 * preview the email before it goes... not HTML code, a very easy UI —
 * what I see is how it would be displayed to them."
 *
 * Flow: "Send Booking Email" click -> GET /admin/notifications/{lead_id}/booking-draft
 *       -> designed preview (email-client styled, WYSIWYG) -> POST send-booking-email
 *
 * 2026-09-15 (Jeff, same thread): + CC — "it'd be nice if I could add an
 * additional email address to it so that if anybody needs to be included
 * in that... I can do so." CC chips (comma/semicolon lists accepted),
 * editable subject, click-to-edit body. Body edits keep the inline
 * paragraph styles that survive Outlook.
 *
 * The body_html is rendered exactly as Postmark delivers it: inline-styled
 * paragraphs on a white card. Raw HTML is only shown in the edit toggle.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { Send, Loader2, RefreshCw, Mail, Calendar, X, Pencil, Eye } from 'lucide-react';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function LeadBookingEmailPreviewModal({ lead, open, onClose, onSent }) {
  const [draft, setDraft] = useState(null);
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [ccList, setCcList] = useState([]);      // array of validated addresses
  const [ccInput, setCcInput] = useState('');
  const [editingBody, setEditingBody] = useState(false);
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
      setDraft(null);
      setCcList([]);
      setCcInput('');
      setEditingBody(false);
      buildDraft(lead.lead_id);
    }
  }, [open, lead?.lead_id, buildDraft]);

  const addCc = () => {
    const parts = ccInput.split(/[,;]/).map((p) => p.trim()).filter(Boolean);
    if (!parts.length) return;
    const bad = parts.find((p) => !EMAIL_RE.test(p));
    if (bad) {
      toast.error(`Not a valid email address: ${bad}`);
      return;
    }
    const next = [...ccList];
    parts.forEach((p) => { if (!next.includes(p.toLowerCase())) next.push(p.toLowerCase()); });
    setCcList(next);
    setCcInput('');
  };

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
        body: JSON.stringify({
          subject: subject.trim(),
          body_html: bodyHtml.trim(),
          cc_email: ccList.length ? ccList.join(', ') : null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to send');
      }
      toast.success(
        ccList.length
          ? `Booking email sent to ${lead.email} (cc: ${ccList.join(', ')})`
          : `Booking email sent to ${lead.email}`
      );
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

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="w-5 h-5 text-navy dark:text-white" />
            Booking email — {lead?.name || lead?.email}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            <span className="ml-3 text-sm text-slate-500">Building the email from your notes…</span>
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
            {/* What the notes derived — context chips */}
            <div className="flex flex-wrap items-center gap-1.5">
              {draft?.signal_label && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-navy/5 text-navy/80 dark:bg-white/10 dark:text-white/80">
                  {draft.signal_label}
                </span>
              )}
              {(draft?.topics || []).map((t) => (
                <span key={t} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600">
                  {t}
                </span>
              ))}
              {draft?.objection && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-800">
                  cost objection addressed
                </span>
              )}
            </div>

            {/* Email-client preview — this is what the lead receives */}
            <div className="rounded-lg border border-slate-200 bg-slate-100 p-3 sm:p-4">
              <div className="rounded-md bg-white shadow-sm overflow-hidden">
                {/* Email client header band */}
                <div className="px-4 py-3 border-b border-slate-100 space-y-1.5">
                  <div className="flex items-baseline gap-2 text-sm">
                    <span className="text-slate-400 w-14 shrink-0 text-xs">To</span>
                    <span className="text-slate-700 truncate">{lead?.email}</span>
                  </div>
                  <div className="flex items-baseline gap-2 text-sm">
                    <span className="text-slate-400 w-14 shrink-0 text-xs">Subject</span>
                    <Input
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      className="h-8 border-none px-1 shadow-none focus-visible:ring-0 font-medium text-slate-900"
                      aria-label="Email subject"
                    />
                  </div>
                </div>
                {/* Rendered body — identical markup to what Postmark sends */}
                {!editingBody ? (
                  <div className="px-5 py-4">
                    <div
                      className="max-w-[560px] mx-auto text-slate-900"
                      style={{ fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif' }}
                      dangerouslySetInnerHTML={{ __html: bodyHtml }}
                    />
                    <div className="mt-3 flex items-center justify-center gap-3">
                      <button
                        type="button"
                        onClick={() => setEditingBody(true)}
                        className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
                      >
                        <Pencil className="w-3 h-3" /> Edit text
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="px-4 py-3">
                    <textarea
                      value={bodyHtml}
                      onChange={(e) => setBodyHtml(e.target.value)}
                      rows={12}
                      spellCheck={false}
                      className="w-full text-xs font-mono text-slate-700 border border-slate-200 rounded p-2 focus:outline-none focus:ring-1 focus:ring-navy/30 resize-y"
                      aria-label="Email body (advanced edit)"
                    />
                    <p className="mt-1 text-[11px] text-slate-400">
                      Paragraphs keep their inline spacing — keep the <code>&lt;p style=…&gt;</code> tags so spacing survives Outlook.
                    </p>
                    <div className="mt-2 flex justify-end">
                      <Button variant="outline" size="sm" onClick={() => setEditingBody(false)}>
                        <Eye className="w-3.5 h-3.5 mr-1.5" /> Back to preview
                      </Button>
                    </div>
                  </div>
                )}
              </div>
              <p className="mt-2 text-xs text-slate-400 text-center">
                This is exactly how the email will appear in their inbox.
              </p>
            </div>

            {/* CC — include anyone else on this send */}
            <div className="rounded-lg border border-navy/10 dark:border-white/10 p-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-slate-500 shrink-0 w-24">Add others (CC)</span>
                <Input
                  value={ccInput}
                  onChange={(e) => setCcInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCc(); } }}
                  placeholder="email@example.com — comma-separate for several"
                  className="h-8 text-sm"
                  aria-label="CC email addresses"
                />
                <Button size="sm" variant="outline" className="h-8 shrink-0" onClick={addCc} disabled={!ccInput.trim()}>
                  Add
                </Button>
              </div>
              {ccList.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ccList.map((c) => (
                    <span key={c} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-navy/5 text-navy/80 dark:bg-white/10 dark:text-white/80">
                      {c}
                      <button
                        type="button"
                        onClick={() => setCcList(ccList.filter((x) => x !== c))}
                        className="text-navy/40 hover:text-navy dark:text-white/40 dark:hover:text-white"
                        aria-label={`Remove ${c}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={sending}>Cancel</Button>
          <Button onClick={handleSend} disabled={sending || loading || !!error || !draft}>
            {sending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Sending…
              </>
            ) : (
              <>
                <Calendar className="w-4 h-4 mr-2" />
                Send email
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}