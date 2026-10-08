import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Plus, UsersRound, Trash2, Info, ChevronDown, Check, Pencil,
} from 'lucide-react';
import { EDUCATION_SECTIONS, EMPTY_ROSTER_TEXT } from './constants';

const MEMBER_STATUS_OPTIONS = ['inactive', 'deceased', 'removed'];

// Status chip follows the brand palette — grey for non-pooling states, navy
// tint for deceased (a permanent record, not an error). No traffic lights.
function memberStatusChipClass(status) {
  switch (status) {
    case 'inactive':
    case 'removed':
      return 'bg-muted text-muted-foreground';
    case 'deceased':
      return 'bg-navy/10 text-navy dark:bg-gold/10 dark:text-gold';
    default:
      return 'bg-muted text-muted-foreground';
  }
}

// Live-computed per-member share (derived from the members endpoint, never
// stored per member). Rendered as a 4-decimal display value.
function formatSharePct(pct) {
  return `${Number(pct ?? 0)}%`;
}

// ========== MEMBER ROW ==========
function ClassMemberRow({ member, onRename, onStatusChange }) {
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(member.name);
  const [statusOpen, setStatusOpen] = useState(false);
  const [nextStatus, setNextStatus] = useState(null);
  const [reason, setReason] = useState('');

  const isRenamed = (member.name_history || []).length > 0;
  const isActive = (member.member_status || 'active') === 'active';

  const startRename = () => {
    setNameDraft(member.name);
    setRenaming(true);
  };

  const submitRename = () => {
    const trimmed = nameDraft.trim();
    if (!trimmed || trimmed === member.name) {
      setRenaming(false);
      return;
    }
    onRename(member.class_member_id, trimmed);
    setRenaming(false);
  };

  // Restore path: active members get the exclusion options; excluded members
  // get a single "Restore to active" action. Reason is mandatory either way.
  const openStatusDialog = (status) => {
    setNextStatus(status);
    setReason('');
    setStatusOpen(true);
  };

  const reasonValid = reason.trim().length > 0 && reason.trim().length <= 1000;
  const statusLabels = {
    inactive: 'Mark Inactive', deceased: 'Mark Deceased', removed: 'Mark Removed', active: 'Restore to Active',
  };

  return (
    <div className="py-2 flex items-center gap-3 text-sm" data-testid={`member-row-${member.class_member_id}`}>
      {renaming ? (
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Input
            value={nameDraft}
            onChange={(e) => setNameDraft(e.target.value)}
            className="h-8 max-w-xs"
            data-testid="member-rename-input"
            autoFocus
          />
          <Button size="sm" variant="outline" onClick={submitRename} data-testid="member-rename-save">Save</Button>
          <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="font-mono text-xs text-muted-foreground w-6 flex-shrink-0">{member.member_order}</span>
            <span className="truncate text-navy dark:text-foreground">{member.name}</span>
            {!isActive && (
              <span
                className={`px-2 py-0.5 text-[10px] font-mono uppercase ${memberStatusChipClass(member.member_status)}`}
                data-testid={`member-status-chip-${member.class_member_id}`}
              >
                {member.member_status}
              </span>
            )}
            {isRenamed && (
              <span
                className="px-1.5 py-0.5 text-[10px] font-mono uppercase bg-muted text-muted-foreground"
                title={(member.name_history || [])
                  .map((h) => `was: ${h.previous_name}`)
                  .join('; ')}
                data-testid={`member-renamed-${member.class_member_id}`}
              >
                renamed
              </span>
            )}
          </div>
          <div className="text-right flex-shrink-0">
            <span className="font-mono text-xs" data-testid={`member-share-${member.class_member_id}`}>
              {formatSharePct(member.member_share_percent)}
            </span>
            <span className="text-[10px] text-muted-foreground ml-1 font-mono">of pool</span>
          </div>
        </>
      )}

      {!renaming && (
        <div className="flex items-center gap-1 flex-shrink-0">
          {(member.date_of_birth || member.notes) && (
            <span
              className="w-6 h-6 flex items-center justify-center text-muted-foreground"
              title={[member.date_of_birth ? `DOB: ${member.date_of_birth}` : null, member.notes || null].filter(Boolean).join(' — ')}
            >
              <Info className="w-3.5 h-3.5" />
            </span>
          )}
          <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={startRename} title="Rename member" data-testid={`member-rename-${member.class_member_id}`}>
            <Pencil className="w-3.5 h-3.5" />
          </Button>
          {isActive ? (
            <Button
              size="sm" variant="ghost"
              className="h-6 w-6 p-0 text-muted-foreground"
              title="Change status (reason required)"
              onClick={() => openStatusDialog(MEMBER_STATUS_OPTIONS[0])}
              data-testid={`member-status-${member.class_member_id}`}
            >
              <UsersRound className="w-3.5 h-3.5" />
            </Button>
          ) : (
            <Button
              size="sm" variant="ghost"
              className="h-6 w-6 p-0 text-muted-foreground"
              title="Restore to active (reason required)"
              onClick={() => openStatusDialog('active')}
              data-testid={`member-restore-${member.class_member_id}`}
            >
              <Check className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      )}

      {/* Status-change panel: the API requires a reason (1-1000 chars). Inline
          field, empty by default, submit disabled until non-empty. */}
      {statusOpen && (
        <div className="w-full mt-2 p-3 bg-muted/30 border border-border rounded" data-testid={`member-status-panel-${member.class_member_id}`}>
          <p className="font-mono text-xs uppercase tracking-widest text-navy mb-2">
            {statusLabels[nextStatus]}
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground font-mono">set status to:</span>
              {MEMBER_STATUS_OPTIONS.map((s) => (
                <Button
                  key={s} size="sm" variant="outline" className="font-mono text-xs"
                  aria-pressed={nextStatus === s}
                  onClick={() => setNextStatus(s)}
                >
                  {s}
                </Button>
              ))}
              {nextStatus !== 'active' && (
                <Button
                  size="sm" variant="outline" className="font-mono text-xs"
                  aria-pressed="true"
                  onClick={() => setNextStatus('active')}
                >
                  active
                </Button>
              )}
            </div>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason (required)"
              className="h-8"
              data-testid={`member-reason-input-${member.class_member_id}`}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                className="btn-primary"
                disabled={!reasonValid}
                onClick={() => {
                  onStatusChange(member.class_member_id, nextStatus, reason);
                  setStatusOpen(false);
                }}
                data-testid={`member-status-submit-${member.class_member_id}`}
              >
                Confirm
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStatusOpen(false)}>Cancel</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ========== EXPANDED CLASS CARD PANEL ==========
function ClassMemberPanel({ cb, membersState, onLoadMembers, onAddMember, onRenameMember, onStatusChange }) {
  const data = membersState.membersByClass?.[cb.class_beneficiary_id];
  const loading = membersState.loadingClassId === cb.class_beneficiary_id;
  const mutating = membersState.mutatingClassId === cb.class_beneficiary_id;

  const [showAddRow, setShowAddRow] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDob, setNewDob] = useState('');

  useEffect(() => {
    onLoadMembers(cb.class_beneficiary_id);
  }, [cb.class_beneficiary_id, onLoadMembers]);

  const submitAddMember = async () => {
    const ok = await onAddMember(cb.class_beneficiary_id, { name: newName.trim(), date_of_birth: newDob || undefined });
    if (ok) {
      setNewName('');
      setNewDob('');
      setShowAddRow(false);
    }
  };

  const roster = data?.items || [];
  const activeCount = data?.active_member_count ?? 0;
  // Human-readable mismatch line (Jeff UX feedback 2026-10-08): total of the
  // live per-member shares, shown in plain numbers instead of Σ shorthand.
  const sumOfShares = data?.per_member_share_percent
    ? Object.values(data.per_member_share_percent).reduce((a, b) => a + (Number(b) || 0), 0)
    : 0;

  return (
    <div className="pt-3 border-t border-border" data-testid={`class-panel-${cb.class_beneficiary_id}`}>
      {/* Pool band */}
      <div className="flex flex-wrap items-center gap-2 mb-1">
        {data && activeCount > 0 && (
          <span className="text-xs font-mono text-muted-foreground" data-testid={`split-ways-${cb.class_beneficiary_id}`}>
            {`split ${activeCount} ${activeCount === 1 ? 'way' : 'ways'}`}
          </span>
        )}
        {data && data.per_member_share_percent && activeCount > 0 && (
          <span className="text-xs font-mono text-navy dark:text-gold" data-testid={`pool-split-${cb.class_beneficiary_id}`}>
            {Object.entries(data.per_member_share_percent)
              .map(([mid, pct]) => {
                const m = roster.find((r) => r.class_member_id === mid);
                return `${m ? m.name : mid}: ${formatSharePct(pct)}`;
              })
              .join(' · ')}
          </span>
        )}
        {data && activeCount > 0 && (
          data.sum_check ? (
            <span
              className="text-xs text-muted-foreground"
              title={`Member shares sum to the pool (${formatSharePct(sumOfShares)} = ${formatSharePct(cb.percentage)})`}
              data-testid={`sum-check-${cb.class_beneficiary_id}`}
            >
              Shares add up ✓
            </span>
          ) : (
            <span
              data-testid={`sum-check-${cb.class_beneficiary_id}`}
              title={`Member shares total ${formatSharePct(sumOfShares)} vs pool ${formatSharePct(cb.percentage)}`}
              className="text-xs text-error dark:text-error"
            >
              Shares ({formatSharePct(sumOfShares)}) don't add up to the pool ({formatSharePct(cb.percentage)})
            </span>
          )
        )}
      </div>
      <p className="text-xs text-muted-foreground mb-3">
        The class percentage is a computed pool split live across members, not an issued certificate.
      </p>

      {/* Roster */}
      {loading && !data ? (
        <p className="text-sm text-muted-foreground py-2" data-testid={`roster-loading-${cb.class_beneficiary_id}`}>Loading members...</p>
      ) : roster.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2" data-testid={`empty-roster-${cb.class_beneficiary_id}`}>
          {EMPTY_ROSTER_TEXT}
        </p>
      ) : (
        <div className="divide-y divide-border/50 mb-2" data-testid={`roster-${cb.class_beneficiary_id}`}>
          {roster.map((m) => (
            <ClassMemberRow
              key={m.class_member_id}
              member={m}
              onRename={(mid, name) => onRenameMember(cb.class_beneficiary_id, mid, name)}
              onStatusChange={(mid, status, reason) => onStatusChange(cb.class_beneficiary_id, mid, status, reason)}
            />
          ))}
        </div>
      )}

      {/* Add member */}
      {showAddRow ? (
        <div className="mt-2 p-3 bg-muted/30 border border-border rounded" data-testid={`add-member-row-${cb.class_beneficiary_id}`}>
          <div className="flex flex-col md:flex-row md:items-end gap-2">
            <div className="flex-1">
              <Label className="label-trust">Name *</Label>
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Full legal name"
                className="mt-1 h-8"
                data-testid={`add-member-name-${cb.class_beneficiary_id}`}
              />
            </div>
            <div className="w-full md:w-40">
              <Label className="label-trust">Date of Birth</Label>
              <Input
                type="date"
                value={newDob}
                onChange={(e) => setNewDob(e.target.value)}
                className="mt-1 h-8"
                data-testid={`add-member-dob-${cb.class_beneficiary_id}`}
              />
            </div>
            <Button
              size="sm" className="btn-primary"
              disabled={!newName.trim() || mutating}
              onClick={submitAddMember}
              data-testid={`add-member-save-${cb.class_beneficiary_id}`}
            >
              Add Member
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowAddRow(false); setNewName(''); setNewDob(''); }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <Button
          size="sm" variant="outline" className="font-mono text-xs mt-1"
          onClick={() => setShowAddRow(true)}
          data-testid={`add-member-btn-${cb.class_beneficiary_id}`}
        >
          <Plus className="w-3.5 h-3.5 mr-1" /> Add Member
        </Button>
      )}
    </div>
  );
}

// ========== CLASS BENEFICIARIES TAB ==========
export function ClassBeneficiariesTab({
  overviewData,
  setShowClassBeneficiaryModal,
  setDeleteConfirmClass,
  membersState,
  onLoadMembers,
  onAddMember,
  onRenameMember,
  onStatusChange,
}) {
  // Class cards start expanded (Jeff UX feedback 2026-10-08): the roster and
  // Add Member button are visible on load — nothing hidden behind a chevron.
  // Collapsing still works per-card; newly loaded classes auto-open.
  const [expandedIds, setExpandedIds] = useState(
    () => new Set((overviewData?.class_beneficiaries || []).map((c) => c.class_beneficiary_id))
  );

  useEffect(() => {
    const ids = (overviewData?.class_beneficiaries || []).map((c) => c.class_beneficiary_id);
    setExpandedIds((prev) => {
      const missing = ids.filter((id) => !prev.has(id));
      if (!missing.length) return prev;
      const next = new Set(prev);
      missing.forEach((id) => next.add(id));
      return next;
    });
  }, [overviewData?.class_beneficiaries]);

  const toggleClass = (classId) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(classId)) next.delete(classId);
      else next.add(classId);
      return next;
    });
  };

  return (
    <>
      <div className="card-trust p-4 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Class Beneficiaries are groups defined by relationship rather than named individuals
            </p>
          </div>
          <Button className="btn-primary" onClick={() => setShowClassBeneficiaryModal(true)} data-testid="add-class-beneficiary-btn">
            <Plus className="w-4 h-4 mr-2" />
            Add Class
          </Button>
        </div>
      </div>

      {/* Education */}
      <div className="mb-6 space-y-4">
        <div className="p-3 bg-muted/30 border border-border rounded text-sm text-muted-foreground">
          <p className="font-mono text-[10px] uppercase tracking-widest text-navy mb-2">
            <Info className="w-3.5 h-3.5 inline mr-1" />
            {EDUCATION_SECTIONS.classBeneficiaries.title}
          </p>
          <p className="text-xs whitespace-pre-line">{EDUCATION_SECTIONS.classBeneficiaries.content}</p>
        </div>
        <div className="p-3 bg-muted/30 border border-border rounded text-sm text-muted-foreground">
          <p className="font-mono text-[10px] uppercase tracking-widest text-navy mb-2">
            <Info className="w-3.5 h-3.5 inline mr-1" />
            {EDUCATION_SECTIONS.distributionConventions.title}
          </p>
          <p className="text-xs whitespace-pre-line">{EDUCATION_SECTIONS.distributionConventions.content}</p>
        </div>
      </div>

      <div className="card-trust overflow-hidden">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <UsersRound className="w-4 h-4 text-navy dark:text-gold" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Class Beneficiaries</h2>
          <span className="ml-auto text-xs text-muted-foreground">{overviewData?.class_beneficiaries?.length || 0} classes</span>
        </div>

        {!overviewData?.class_beneficiaries?.length ? (
          <div className="p-8 text-center">
            <UsersRound className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
            <p className="text-muted-foreground mb-2">No Class Beneficiaries defined</p>
            <p className="text-sm text-muted-foreground mb-4">
              Add a class like "Children" or "Descendants" to designate beneficiaries by relationship
            </p>
            <Button className="btn-primary" onClick={() => setShowClassBeneficiaryModal(true)}>
              <Plus className="w-4 h-4 mr-2" /> Add Class Beneficiary
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {overviewData.class_beneficiaries.map((cb) => (
              <div key={cb.class_beneficiary_id} className="p-4 hover:bg-muted/20 transition-colors">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-4 min-w-0">
                    <button
                      type="button"
                      className="flex items-center gap-4 text-left min-w-0 flex-1"
                      onClick={() => toggleClass(cb.class_beneficiary_id)}
                      data-testid={`class-toggle-${cb.class_beneficiary_id}`}
                      aria-expanded={expandedIds.has(cb.class_beneficiary_id)}
                    >
                      <div className="w-12 h-12 bg-navy/10 dark:bg-gold/10 flex items-center justify-center flex-shrink-0">
                        <UsersRound className="w-6 h-6 text-navy dark:text-gold" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-navy dark:text-foreground truncate">{cb.class_type_label}</p>
                          {cb.percentage > 0 && (
                            <span className="px-2 py-0.5 text-xs font-mono bg-gold/10 text-gold">
                              {cb.percentage}% of trust
                            </span>
                          )}
                        </div>
                        {cb.description && (
                          <p className="text-sm text-muted-foreground truncate">{cb.description}</p>
                        )}
                        {cb.notes && (
                          <p className="text-xs text-muted-foreground mt-1 truncate">{cb.notes}</p>
                        )}
                        <p className="text-[11px] text-navy/70 dark:text-gold/70 mt-1" data-testid={`class-hint-${cb.class_beneficiary_id}`}>
                          {expandedIds.has(cb.class_beneficiary_id)
                            ? ((cb.member_count ?? 0) === 0
                                ? 'Add each person below — click to collapse'
                                : `${cb.member_count} member${cb.member_count === 1 ? '' : 's'} listed — click to collapse`)
                            : 'Click to view members and add a person'}
                        </p>
                      </div>
                      <ChevronDown
                        className={`w-4 h-4 flex-shrink-0 text-muted-foreground transition-transform ${expandedIds.has(cb.class_beneficiary_id) ? 'rotate-180' : ''}`}
                      />
                    </button>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-error hover:text-error hover:bg-error/10 dark:hover:bg-error/20 flex-shrink-0"
                    onClick={() => setDeleteConfirmClass(cb)}
                    data-testid={`delete-class-${cb.class_beneficiary_id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>

                {expandedIds.has(cb.class_beneficiary_id) && membersState && (
                  <ClassMemberPanel
                    cb={cb}
                    membersState={membersState}
                    onLoadMembers={onLoadMembers}
                    onAddMember={onAddMember}
                    onRenameMember={onRenameMember}
                    onStatusChange={onStatusChange}
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default ClassBeneficiariesTab;