import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import { Send, Loader2 } from 'lucide-react';

export default function LeadFollowUpModal({ lead, open, onClose, onSent }) {
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);

  // Load templates when modal opens
  useEffect(() => {
    if (open && lead) {
      loadTemplates();
    }
  }, [open, lead]);

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth('/admin/notifications/templates');
      if (res.ok) {
        const data = await res.json();
        setTemplates(data.templates || []);
      }
    } catch (e) {
      console.error('Failed to load templates:', e);
    }
    setLoading(false);
  };

  const handleTemplateSelect = (tpl) => {
    setSelectedTemplate(tpl);
    // Fill in subject and body with variable substitution
    let filledSubject = (tpl.subject || '').replace(/{name}/g, lead?.name || '');
    let filledBody = (tpl.body || '')
      .replace(/{name}/g, lead?.name || '')
      .replace(/{email}/g, lead?.email || '')
      .replace(/{source}/g, lead?.source || '')
      .replace(/{course_url}/g, 'https://trustoffice.app/trustee-101')
      .replace(/{app_url}/g, 'https://app.trustoffice.app');
    setSubject(filledSubject);
    setBody(filledBody);
  };

  const handleSend = async () => {
    if (!selectedTemplate || !subject.trim() || !body.trim()) {
      toast.error('Please select a template and fill in the subject and body');
      return;
    }
    setSending(true);
    try {
      const res = await fetchWithAuth(
        `/admin/notifications/${lead.lead_id}/send-email`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: selectedTemplate.template_id,
            custom_subject: subject,
            custom_body: body,
          }),
        }
      );
      if (res.ok) {
        toast.success(`Email sent to ${lead.name || lead.email}`);
        onClose();
        if (onSent) onSent();
      } else {
        const data = await res.json();
        toast.error(data.detail || 'Failed to send email');
      }
    } catch (e) {
      toast.error('Failed to send email');
    }
    setSending(false);
  };

  // Suggest template based on lead stage
  const getSuggestedTemplateId = () => {
    if (!lead?.stage) return null;
    const stageMap = {
      new: 'tpl_welcome_followup',
      engaged: 'tpl_course_nudge',
      warm: 'tpl_value_pitch',
      lost: 'tpl_win_back',
    };
    // For booked calls, suggest call prep
    if (lead.booked_call) return 'tpl_call_prep';
    return stageMap[lead.stage] || null;
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="w-4 h-4" />
            Follow up with {lead?.name || 'Lead'}
          </DialogTitle>
          <p className="text-sm text-muted-foreground">{lead?.email}</p>
        </DialogHeader>

        <div className="space-y-4">
          {/* Template selector */}
          <div>
            <label className="label-trust block mb-2">Choose Template</label>
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="w-4 h-4 animate-spin" />
                Loading templates...
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {templates.map((tpl) => {
                  const isSuggested = tpl.template_id === getSuggestedTemplateId();
                  return (
                    <button
                      key={tpl.template_id}
                      onClick={() => handleTemplateSelect(tpl)}
                      className={`text-left p-2.5 border text-sm transition-colors ${
                        selectedTemplate?.template_id === tpl.template_id
                          ? 'border-gold bg-gold/5'
                          : 'border-navy/10 hover:border-navy/30'
                      } ${isSuggested ? 'ring-1 ring-gold/30' : ''}`}
                    >
                      <span className="font-medium text-navy text-xs block">{tpl.name}</span>
                      <span className="text-[10px] text-navy/50 font-mono block mt-0.5">
                        {tpl.trigger_stage ? `For: ${tpl.trigger_stage}` : 'General'}
                      </span>
                      {isSuggested && (
                        <span className="text-[9px] text-gold font-mono uppercase tracking-wider mt-1 block">
                          Recommended
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Subject */}
          <div>
            <label className="label-trust block mb-1">Subject</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-3 py-2 border border-navy/10 bg-transparent text-sm text-navy focus:outline-none focus:border-gold"
              placeholder="Email subject..."
            />
          </div>

          {/* Body */}
          <div>
            <label className="label-trust block mb-1">Message</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full px-3 py-2 border border-navy/10 bg-transparent text-sm text-navy focus:outline-none focus:border-gold min-h-[200px]"
              placeholder="Write your message..."
              rows={10}
            />
          </div>
        </div>

        <DialogFooter className="flex items-center justify-between">
          <p className="text-[10px] text-navy/40 font-mono">
            Sent via Postmark · Logged to lead activity
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSend}
              disabled={sending || !selectedTemplate}
              className="bg-gold text-navy hover:bg-gold/90"
            >
              {sending ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 mr-2" />
                  Send Email
                </>
              )}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
