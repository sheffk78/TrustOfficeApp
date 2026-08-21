import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Target, Activity, RefreshCw, MessageSquare, Crown, BarChart3, Building2, FileText, DollarSign, LogIn, Gift, XCircle, Trash2, AlertTriangle, CheckCircle } from 'lucide-react';
import { getStatusBadgeClass, getLeadStageBadgeClass, getRatioColorClass, formatStageLabel, formatDate, LEAD_STAGES } from './helpers';

// ─── Lead Detail Dialog ────────────────────────────────────────────
export function LeadDetailDialog({
  selectedLead, leadDetailLoading,
  onClose, onUpdateLeadStage, onAddNote, onNoteChange, leadNoteText,
}) {
  return (
    <Dialog open={!!selectedLead} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
            <Target className="w-5 h-5 text-gold" />
            {selectedLead?.name || 'Lead Details'}
          </DialogTitle>
          <DialogDescription>{selectedLead?.email}</DialogDescription>
        </DialogHeader>

        {leadDetailLoading ? (
          <div className="flex items-center justify-center py-12">
            <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
          </div>
        ) : selectedLead ? (
          <div className="space-y-4 py-4">
            {/* Status Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                <p className="text-xs text-muted-foreground mb-1">Stage</p>
                <Badge className={getLeadStageBadgeClass(selectedLead.stage)}>
                  {selectedLead.stage_label || selectedLead.stage}
                </Badge>
              </div>
              <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                <p className="text-xs text-muted-foreground mb-1">Score</p>
                <p className="text-lg font-bold text-navy dark:text-white">{selectedLead.score || 0}</p>
              </div>
              <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                <p className="text-xs text-muted-foreground mb-1">Plan</p>
                <p className="text-sm font-medium text-navy dark:text-white capitalize">{selectedLead.plan_type}</p>
              </div>
              <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
                <p className="text-xs text-muted-foreground mb-1">Lessons</p>
                <p className="text-lg font-bold text-navy dark:text-white">{selectedLead.lessons_watched || 0}/9</p>
              </div>
            </div>

            {/* Discovery Call Booked */}
            {selectedLead.booked_call && (
              <div className="p-3 border border-gold/30 bg-gold/5 rounded">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-base">📞</span>
                  <span className="text-sm font-medium text-navy dark:text-white">Discovery Call Scheduled</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {selectedLead.booked_call_at
                    ? new Date(selectedLead.booked_call_at).toLocaleString(undefined, {
                        weekday: 'short',
                        month: 'short',
                        day: 'numeric',
                        hour: 'numeric',
                        minute: '2-digit',
                        timeZoneName: 'short'
                      })
                    : 'Date not available'}
                </p>
              </div>
            )}

            {/* Score Breakdown */}
            {selectedLead.score_breakdown && (
              <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
                <h3 className="text-sm font-medium text-navy dark:text-white mb-3 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-gold" />
                  Score Breakdown
                </h3>
                <div className="space-y-2">
                  {Object.entries(selectedLead.score_breakdown).map(([key, item]) => (
                    <div key={key} className="flex items-center gap-3">
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-xs text-muted-foreground capitalize">
                            {key.replace(/_/g, ' ')}
                          </span>
                          <span className="text-xs font-mono text-navy dark:text-white">
                            {item.score}/{item.max}
                          </span>
                        </div>
                        <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${getRatioColorClass(item.score / item.max)}`}
                            style={{ width: `${(item.score / item.max) * 100}%` }}
                          />
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{item.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Next Action */}
            <div className="p-3 border border-gold/30 bg-gold/5 rounded">
              <div className="flex items-center gap-2 mb-1">
                <Activity className="w-4 h-4 text-gold" />
                <span className="text-sm font-medium text-navy dark:text-white">Next Action</span>
              </div>
              <p className="text-sm text-muted-foreground">{selectedLead.next_action || 'Monitor — no action needed'}</p>
            </div>

            {/* Stage changer */}
            <div>
              <label className="text-sm font-medium text-navy dark:text-white block mb-2">Change Stage</label>
              <div className="flex flex-wrap gap-2">
                {LEAD_STAGES.map((s) => (
                  <button
                    key={s}
                    onClick={() => onUpdateLeadStage(selectedLead.lead_id, s)}
                    className={`px-3 py-1.5 text-sm transition-colors ${
                      selectedLead.stage === s
                        ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                        : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                    }`}
                  >
                    {formatStageLabel(s)}
                  </button>
                ))}
              </div>
            </div>

            {/* Add Note */}
            <div>
              <label className="text-sm font-medium text-navy dark:text-white block mb-2">
                <MessageSquare className="w-4 h-4 inline mr-1" />
                Add Note
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={leadNoteText}
                  onChange={(e) => onNoteChange(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') onAddNote(selectedLead.lead_id); }}
                  placeholder="Type a note about this lead..."
                  className="flex-1 px-3 py-2 border border-navy/10 dark:border-white/10 bg-transparent text-navy dark:text-white text-sm focus:outline-none focus:border-gold"
                />
                <Button onClick={() => onAddNote(selectedLead.lead_id)} disabled={!leadNoteText.trim()}>
                  Add
                </Button>
              </div>
            </div>

            {/* Activity Log */}
            {selectedLead.activities && selectedLead.activities.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-navy dark:text-white mb-3">Activity Log</h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {selectedLead.activities.map((act, i) => (
                    <div key={act.activity_id || i} className="flex items-start gap-3 p-2 border-b border-navy/5 dark:border-white/5 last:border-0">
                      <div className="w-2 h-2 mt-1.5 rounded-full bg-gold shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-navy dark:text-white">{act.content}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {act.action_type} · {act.created_at ? new Date(act.created_at).toLocaleString() : '—'}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

// ─── Bulk Lead Stage Change Dialog ─────────────────────────────────
export function BulkLeadStageDialog({
  show, selectedCount, bulkLeadStage, bulkLeadActionLoading,
  onClose, onStageSelect, onConfirm,
}) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
            <Activity className="w-5 h-5 text-gold" />
            Change {selectedCount} Lead{selectedCount !== 1 ? 's' : ''} Stage
          </DialogTitle>
          <DialogDescription>
            Select the new stage for all selected leads.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="flex flex-wrap gap-2">
            {LEAD_STAGES.map((s) => (
              <button
                key={s}
                onClick={() => onStageSelect(s)}
                className={`px-4 py-2 text-sm transition-colors ${
                  bulkLeadStage === s
                    ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                    : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                }`}
              >
                {formatStageLabel(s)}
              </button>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={bulkLeadActionLoading}>
            Cancel
          </Button>
          <Button
            className="btn-primary"
            onClick={onConfirm}
            disabled={bulkLeadActionLoading}
          >
            {bulkLeadActionLoading ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Updating...
              </>
            ) : (
              `Move to ${formatStageLabel(bulkLeadStage)}`
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Customer Detail Sidebar ───────────────────────────────────────
export function CustomerDetailDialog({
  customerDetail,
  onClose, onImpersonate, onGrantAccess, onMakeAdmin, onRemoveAdmin,
  onGrantStats, onRevokeStats, onDelete,
}) {
  if (!customerDetail) return null;
  const isPrimaryAdmin = customerDetail.email === 'contact@trustoffice.app';
  const canDelete = !isPrimaryAdmin && !customerDetail.is_admin;

  const sub = customerDetail.subscription || {};
  const planType = sub.plan_type || 'free';
  const isForeverFree = planType === 'forever_free' || /forever free/i.test(sub.tier_display_name || '');
  const isGifted = sub.gifted === true || (typeof planType === 'string' && planType.startsWith('gifted_'));
  const billingPeriod = sub.billing_period
    ? sub.billing_period.charAt(0).toUpperCase() + sub.billing_period.slice(1)
    : null;
  const PLAN_LABELS = {
    forever_free: 'Forever Free',
    gifted_14day: 'Gifted Trial',
    gifted_monthly: 'Gifted Monthly',
    gifted_annual: 'Gifted Annual',
    gifted_trustee: 'Gifted Trustee',
    gifted_estate: 'Gifted Estate',
    gifted_advisor: 'Gifted Advisor',
    monthly: 'Monthly',
    annual: 'Annual',
    trial: 'Trial',
    free: 'Free',
  };
  const planLabel = PLAN_LABELS[planType] || sub.tier_display_name || planType.replace(/_/g, ' ') || 'Free';
  const memberSince = customerDetail.created_at ? formatDate(customerDetail.created_at) : null;
  let accessEndLabel = null;
  let accessExpired = false;
  if (!isForeverFree && (sub.trial_end || sub.gifted_at)) {
    const endRaw = sub.trial_end || sub.gifted_at;
    const endDate = new Date(endRaw);
    if (!isNaN(endDate.getTime())) {
      accessExpired = endDate < new Date();
      accessEndLabel = `${formatDate(endRaw)}${accessExpired ? ' — expired' : ''}`;
    }
  }

  return (
    <Dialog open={!!customerDetail} onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white flex items-center gap-2">
            {customerDetail.name}
            {customerDetail.is_admin && <Crown className="w-5 h-5 text-gold" />}
          </DialogTitle>
          <DialogDescription>{customerDetail.email}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Account State */}
          <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
            <h3 className="font-medium text-navy dark:text-white mb-2">Account State</h3>
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={getStatusBadgeClass(sub.status)}>
                {sub.status || 'none'}
              </Badge>
              {isForeverFree && (
                <Badge className="bg-success/10 text-success">
                  <CheckCircle className="w-3 h-3 mr-1" />
                  Forever Free
                </Badge>
              )}
              {isGifted && !isForeverFree && (
                <Badge className="bg-gold/20 text-gold">
                  <Gift className="w-3 h-3 mr-1" />
                  Gifted
                </Badge>
              )}
              {billingPeriod && (
                <Badge variant="outline">{billingPeriod}</Badge>
              )}
              {customerDetail.is_stats_user && (
                <Badge className="bg-gold/20 text-gold">
                  <BarChart3 className="w-3 h-3 mr-1" />
                  Stats Access
                </Badge>
              )}
            </div>
            <dl className="mt-3 grid gap-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Package</dt>
                <dd className="font-medium text-navy dark:text-white">{planLabel}</dd>
              </div>
              {memberSince && (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Member since</dt>
                  <dd className="font-medium text-navy dark:text-white">{memberSince}</dd>
                </div>
              )}
              {accessEndLabel && (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">Access ends</dt>
                  <dd className={`font-medium ${accessExpired ? 'text-red-500' : 'text-navy dark:text-white'}`}>
                    {accessEndLabel}
                  </dd>
                </div>
              )}
            </dl>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
              <Building2 className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
              <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.trusts}</p>
              <p className="text-xs text-muted-foreground">Trusts</p>
            </div>
            <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
              <FileText className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
              <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.minutes}</p>
              <p className="text-xs text-muted-foreground">Minutes</p>
            </div>
            <div className="p-3 border border-navy/10 dark:border-white/10 rounded text-center">
              <DollarSign className="w-5 h-5 mx-auto mb-1 text-muted-foreground" />
              <p className="text-lg font-bold text-navy dark:text-white">{customerDetail.stats?.distributions}</p>
              <p className="text-xs text-muted-foreground">Distributions</p>
            </div>
          </div>

          {/* Referral Info */}
          {customerDetail.referral_info && (
            <div className="p-4 border border-navy/10 dark:border-white/10 rounded">
              <h3 className="font-medium text-navy dark:text-white mb-2">Referral Info</h3>
              {customerDetail.referral_info.referral_code && (
                <p className="text-sm text-muted-foreground">
                  Code: <span className="font-mono">{customerDetail.referral_info.referral_code}</span>
                </p>
              )}
              {customerDetail.referral_info.referred_by && (
                <p className="text-sm text-muted-foreground">Referred by another user</p>
              )}
              <p className="text-sm text-muted-foreground">
                Successful referrals: {customerDetail.referral_info.successful_referrals}
              </p>
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-4 border-t border-navy/10 dark:border-white/10">
            {!customerDetail.is_admin && (
              <Button
                size="sm"
                className="bg-orange-500 hover:bg-orange-600 text-white"
                onClick={onImpersonate}
              >
                <LogIn className="w-4 h-4 mr-2" />
                Login as User
              </Button>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={onGrantAccess}
            >
              <Gift className="w-4 h-4 mr-2" />
              Grant Access
            </Button>

            {!customerDetail.is_admin ? (
              <Button
                variant="outline"
                size="sm"
                onClick={onMakeAdmin}
              >
                <Crown className="w-4 h-4 mr-2" />
                Make Admin
              </Button>
            ) : !isPrimaryAdmin && (
              <Button
                variant="outline"
                size="sm"
                onClick={onRemoveAdmin}
              >
                <XCircle className="w-4 h-4 mr-2" />
                Remove Admin
              </Button>
            )}

            {customerDetail.is_stats_user ? (
              <Button
                variant="outline"
                size="sm"
                className="text-rust hover:text-rust"
                onClick={onRevokeStats}
              >
                <BarChart3 className="w-4 h-4 mr-2" />
                Revoke Stats
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={onGrantStats}
              >
                <BarChart3 className="w-4 h-4 mr-2" />
                Grant Stats
              </Button>
            )}

            {canDelete && (
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:text-red-600"
                onClick={onDelete}
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Grant Access Dialog ───────────────────────────────────────────
export function GrantAccessDialog({
  show, selectedCustomerEmail, grantAccessForm,
  onClose, onFormChange, onConfirm,
}) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white">Gift Access</DialogTitle>
          <DialogDescription>
            Gift subscription access to {selectedCustomerEmail}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Plan Type</Label>
            <Select
              value={grantAccessForm.plan_type}
              onValueChange={(v) => onFormChange({ ...grantAccessForm, plan_type: v })}
            >
              <SelectTrigger className="mt-1 input-trust">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gifted_14day">Gift 14 Days</SelectItem>
                <SelectItem value="gifted_monthly">Gift 1 Month</SelectItem>
                <SelectItem value="gifted_annual">Gift 1 Year</SelectItem>
                <SelectItem value="forever_free">Forever Free</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {grantAccessForm.plan_type === 'gifted_14day' && (
            <div>
              <Label className="label-trust">Gift Days</Label>
              <Input
                type="number"
                value={grantAccessForm.days}
                onChange={(e) => onFormChange({ ...grantAccessForm, days: parseInt(e.target.value) })}
                className="mt-1 input-trust"
                min={1}
                max={365}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="btn-primary" onClick={onConfirm}>Grant Access</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Delete Confirmation Dialog ────────────────────────────────────
export function DeleteDialog({ show, selectedCustomerEmail, onClose, onConfirm }) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-red-600 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            Delete Customer
          </DialogTitle>
          <DialogDescription>
            This will permanently delete {selectedCustomerEmail} and ALL their data including trusts, minutes, distributions, and settings.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <p className="text-red-500 font-medium">This action cannot be undone!</p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button className="bg-red-600 hover:bg-red-700 text-white" onClick={onConfirm}>
            Delete Forever
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Create Admin Dialog ───────────────────────────────────────────
export function CreateAdminDialog({ show, createAdminForm, onClose, onFormChange, onConfirm }) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white">Create Admin User</DialogTitle>
          <DialogDescription>
            Create a new admin account with full TrustOffice access.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Email *</Label>
            <Input
              type="email"
              value={createAdminForm.email}
              onChange={(e) => onFormChange({ ...createAdminForm, email: e.target.value })}
              className="mt-1 input-trust"
              placeholder="admin@example.com"
            />
          </div>
          <div>
            <Label className="label-trust">Name *</Label>
            <Input
              value={createAdminForm.name}
              onChange={(e) => onFormChange({ ...createAdminForm, name: e.target.value })}
              className="mt-1 input-trust"
              placeholder="Admin Name"
            />
          </div>
          <div>
            <Label className="label-trust">Password (optional)</Label>
            <Input
              type="password"
              value={createAdminForm.password}
              onChange={(e) => onFormChange({ ...createAdminForm, password: e.target.value })}
              className="mt-1 input-trust"
              placeholder="Leave blank for OAuth-only"
            />
            <p className="text-xs text-muted-foreground mt-1">
              If no password is set, the user can only log in via Google OAuth.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            className="btn-primary"
            onClick={onConfirm}
            disabled={!createAdminForm.email || !createAdminForm.name}
          >
            Create Admin
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Create User Dialog ───────────────────────────────────────────
export function CreateUserDialog({ show, createUserForm, createUserLoading, onClose, onFormChange, onConfirm }) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white">Add New User</DialogTitle>
          <DialogDescription>
            Create a user account. They will receive a welcome email with a link to set their password.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Name *</Label>
            <Input
              value={createUserForm.name}
              onChange={(e) => onFormChange({ ...createUserForm, name: e.target.value })}
              className="mt-1 input-trust"
              placeholder="John Smith"
            />
          </div>
          <div>
            <Label className="label-trust">Email *</Label>
            <Input
              type="email"
              value={createUserForm.email}
              onChange={(e) => onFormChange({ ...createUserForm, email: e.target.value })}
              className="mt-1 input-trust"
              placeholder="user@example.com"
            />
          </div>
          <div>
            <Label className="label-trust">Gift Tier *</Label>
            <Select
              value={createUserForm.gifted_tier}
              onValueChange={(v) => onFormChange({ ...createUserForm, gifted_tier: v })}
            >
              <SelectTrigger className="mt-1 input-trust">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="14day">Gift 14 Days</SelectItem>
                <SelectItem value="monthly">Gift 1 Month</SelectItem>
                <SelectItem value="annual">Gift 1 Year</SelectItem>
                <SelectItem value="forever_free">Forever Free</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-1">
              This user will receive gifted access on the selected tier.
            </p>
          </div>
          <p className="text-xs text-muted-foreground">
            An email will be sent to this address with a link to set their password. The link expires in 24 hours.
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            className="btn-primary"
            onClick={onConfirm}
            disabled={!createUserForm.email.trim() || !createUserForm.name.trim() || createUserLoading}
          >
            {createUserLoading ? 'Creating...' : 'Add User'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Fix Referral Dialog ───────────────────────────────────────────
export function FixReferralDialog({ show, fixReferralForm, onClose, onFormChange, onConfirm }) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy dark:text-white">Fix Referral</DialogTitle>
          <DialogDescription>
            Create, delete, or update a referral relationship.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Action</Label>
            <Select
              value={fixReferralForm.action}
              onValueChange={(v) => onFormChange({ ...fixReferralForm, action: v })}
            >
              <SelectTrigger className="mt-1 input-trust">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="create">Create Referral</SelectItem>
                <SelectItem value="delete">Delete Referral</SelectItem>
                <SelectItem value="update_status">Update Status</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="label-trust">Referrer Email</Label>
            <Input
              type="email"
              value={fixReferralForm.referrer_email}
              onChange={(e) => onFormChange({ ...fixReferralForm, referrer_email: e.target.value })}
              className="mt-1 input-trust"
              placeholder="referrer@example.com"
            />
          </div>
          <div>
            <Label className="label-trust">Referee Email</Label>
            <Input
              type="email"
              value={fixReferralForm.referee_email}
              onChange={(e) => onFormChange({ ...fixReferralForm, referee_email: e.target.value })}
              className="mt-1 input-trust"
              placeholder="referee@example.com"
            />
          </div>
          {fixReferralForm.action === 'update_status' && (
            <div>
              <Label className="label-trust">New Status</Label>
              <Select
                value={fixReferralForm.status}
                onValueChange={(v) => onFormChange({ ...fixReferralForm, status: v })}
              >
                <SelectTrigger className="mt-1 input-trust">
                  <SelectValue placeholder="Select status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="converted">Converted</SelectItem>
                  <SelectItem value="expired">Expired</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button
            className="btn-primary"
            onClick={onConfirm}
            disabled={!fixReferralForm.referrer_email || !fixReferralForm.referee_email}
          >
            Apply Fix
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Bulk Delete Confirmation Dialog ────────────────────────────────
export function BulkDeleteDialog({ show, selectedCustomerIds, customers, bulkActionLoading, onClose, onConfirm }) {
  const selectedCustomers = customers.filter(c => selectedCustomerIds.has(c.user_id));
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-red-600 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            Delete {selectedCustomerIds.size} Account{selectedCustomerIds.size !== 1 ? 's' : ''}
          </DialogTitle>
          <DialogDescription>
            This will permanently delete the selected accounts and ALL their data including trusts, minutes, distributions, and settings.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <p className="text-red-500 font-medium mb-3">This action cannot be undone!</p>
          <div className="max-h-40 overflow-y-auto bg-muted/50 rounded p-3">
            <p className="text-sm text-muted-foreground mb-2">Accounts to be deleted:</p>
            <ul className="text-sm space-y-1">
              {selectedCustomers.map(c => (
                <li key={c.user_id} className="text-navy dark:text-white">
                  • {c.email}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={bulkActionLoading}>
            Cancel
          </Button>
          <Button
            className="bg-red-600 hover:bg-red-700 text-white"
            onClick={onConfirm}
            disabled={bulkActionLoading}
          >
            {bulkActionLoading ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Deleting...
              </>
            ) : (
              <>
                <Trash2 className="w-4 h-4 mr-2" />
                Delete Forever
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─── Impersonate User Confirmation Dialog ──────────────────────────
export function ImpersonateDialog({ show, selectedCustomer, impersonateLoading, onClose, onConfirm }) {
  return (
    <Dialog open={show} onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-orange-600 flex items-center gap-2">
            <LogIn className="w-5 h-5" />
            Login as User
          </DialogTitle>
          <DialogDescription>
            You will be able to see and interact with the app exactly as this user sees it.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded p-4 mb-4">
            <p className="text-sm text-orange-800 dark:text-orange-200 mb-2">
              <strong>You are about to view as:</strong>
            </p>
            <p className="font-medium text-navy dark:text-white">
              {selectedCustomer?.name}
            </p>
            <p className="text-sm text-muted-foreground">
              {selectedCustomer?.email}
            </p>
          </div>

          <ul className="text-sm text-muted-foreground space-y-2">
            <li className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-success mt-0.5 shrink-0" />
              You'll see their dashboard, trusts, and all data
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-success mt-0.5 shrink-0" />
              An orange banner will remind you that you're impersonating
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle className="w-4 h-4 text-success mt-0.5 shrink-0" />
              Click "Exit Impersonation" to return to admin
            </li>
            <li className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-warning mt-0.5 shrink-0" />
              This action is logged for audit purposes
            </li>
          </ul>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={impersonateLoading}>
            Cancel
          </Button>
          <Button
            className="bg-orange-500 hover:bg-orange-600 text-white"
            onClick={onConfirm}
            disabled={impersonateLoading}
          >
            {impersonateLoading ? (
              <>
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                Switching...
              </>
            ) : (
              <>
                <LogIn className="w-4 h-4 mr-2" />
                Login as User
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
