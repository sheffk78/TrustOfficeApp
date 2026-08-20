import { useState, useEffect, useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { AlertCircle, Info, XCircle } from 'lucide-react';
import PDFPreviewModal from '@/components/PDFPreviewModal';
import {
  CLASS_BENEFICIARY_OPTIONS,
  RELATIONSHIP_OPTIONS,
  HOLDER_TYPE_OPTIONS,
} from './constants';

// ========== CERTIFICATE MODAL ==========
export function CertificateModal({
  showCertificateModal,
  setShowCertificateModal,
  editingCertificate,
  certificateForm,
  setCertificateForm,
  resetCertificateForm,
  handleIssueCertificate,
  summary,
  trusts,
  selectedTrust,
}) {
  return (
    <Dialog open={showCertificateModal} onOpenChange={(open) => { if (!open) resetCertificateForm(); setShowCertificateModal(open); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editingCertificate ? 'Edit Certificate' : 'Issue New Certificate'}</DialogTitle>
          <DialogDescription>
            {editingCertificate ? 'Update certificate details' : `Issue beneficial interest units. ${summary?.remaining_units || 0} units available.`}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {certificateForm.holder_type === 'trust' && trusts && trusts.length > 0 ? (
            <div>
              <Label className="label-trust">Select Trust *</Label>
              <Select
                value={certificateForm.holder_trust_id}
                onValueChange={(v) => {
                  const trust = trusts.find(t => t.trust_id === v);
                  const trustName = trust ? (trust.trust_name || trust.name || 'Unknown Trust') : '';
                  setCertificateForm({ ...certificateForm, holder_trust_id: v, holder_name: trustName });
                }}
              >
                <SelectTrigger className="mt-1" data-testid="holder-trust-select">
                  <SelectValue placeholder="Choose a trust..." />
                </SelectTrigger>
                <SelectContent>
                  {trusts.filter(t => t.trust_id !== selectedTrust?.trust_id).map(t => (
                    <SelectItem key={t.trust_id} value={t.trust_id}>
                      {t.trust_name || t.name || 'Unknown Trust'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1.5">
                <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                <span>Selecting a trust will automatically create a beneficiary relationship in the Structures hierarchy. The trust's name auto-fills the holder name for display.</span>
              </p>
            </div>
          ) : (
            <div>
              <Label className="label-trust">Holder Name *</Label>
              <Input
                value={certificateForm.holder_name}
                onChange={(e) => setCertificateForm({ ...certificateForm, holder_name: e.target.value })}
                placeholder="John Smith or Smith Family Trust"
                className="mt-1"
                data-testid="holder-name-input"
              />
            </div>
          )}
          <div>
            <Label className="label-trust">Holder Type</Label>
            <Select
              value={certificateForm.holder_type}
              onValueChange={(v) => {
                const updates = { holder_type: v };
                if (v === 'trust' && trusts && trusts.length === 1 && trusts[0].trust_id === selectedTrust?.trust_id) {
                  updates.holder_trust_id = '';
                  updates.holder_name = '';
                } else if (v === 'trust' && trusts && trusts.length === 2) {
                  const otherTrust = trusts.find(t => t.trust_id !== selectedTrust?.trust_id);
                  if (otherTrust) {
                    updates.holder_trust_id = otherTrust.trust_id;
                    updates.holder_name = otherTrust.trust_name || otherTrust.name || 'Unknown Trust';
                  }
                }
                setCertificateForm({ ...certificateForm, ...updates });
              }}
            >
              <SelectTrigger className="mt-1" data-testid="holder-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HOLDER_TYPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {certificateForm.holder_type === 'trust' && trusts && trusts.length <= 1 && (
              <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1.5">
                <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
                <span>You need at least two trusts to make one a beneficiary of another. Create another trust first, or use "Other Entity" with a free-text name.</span>
              </p>
            )}
          </div>
          <div>
            <Label className="label-trust">Holder Identifier (Optional)</Label>
            <Input
              value={certificateForm.holder_identifier}
              onChange={(e) => setCertificateForm({ ...certificateForm, holder_identifier: e.target.value })}
              placeholder="SSN last 4, EIN, etc."
              className="mt-1"
            />
          </div>
          <div>
            <Label className="label-trust">Email</Label>
            <Input
              type="email"
              value={certificateForm.email}
              onChange={(e) => setCertificateForm({ ...certificateForm, email: e.target.value })}
              placeholder="beneficiary@email.com"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="label-trust">Phone</Label>
            <Input
              type="tel"
              value={certificateForm.phone}
              onChange={(e) => setCertificateForm({ ...certificateForm, phone: e.target.value })}
              placeholder="(555) 123-4567"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="label-trust">Units *</Label>
            <Input
              type="number"
              step="any"
              min="0"
              value={certificateForm.units}
              onChange={(e) => setCertificateForm({ ...certificateForm, units: e.target.value })}
              placeholder="25"
              required
              className="mt-1"
              data-testid="units-input"
            />
            {summary && (
              <div className="mt-2 space-y-1">
                {certificateForm.units && parseFloat(certificateForm.units) > 0 && (
                  <p className="text-xs text-muted-foreground font-mono">
                    = {((parseFloat(certificateForm.units) / summary.settings.total_authorized_units) * 100).toFixed(2)}% ownership
                  </p>
                )}
                {certificateForm.units && parseFloat(certificateForm.units) > summary.remaining_units && !editingCertificate && (
                  <p className="text-xs text-error dark:text-error font-medium flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    Exceeds available units ({summary.remaining_units} remaining)
                  </p>
                )}
              </div>
            )}
          </div>
          <div>
            <Label className="label-trust">Issue Date</Label>
            <Input
              type="date"
              value={certificateForm.issue_date}
              onChange={(e) => setCertificateForm({ ...certificateForm, issue_date: e.target.value })}
              className="mt-1"
            />
          </div>
          <div>
            <Label className="label-trust">Notes (Optional)</Label>
            <Textarea
              value={certificateForm.notes}
              onChange={(e) => setCertificateForm({ ...certificateForm, notes: e.target.value })}
              placeholder="Additional notes..."
              className="mt-1"
              rows={2}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { setShowCertificateModal(false); resetCertificateForm(); }}>Cancel</Button>
          <Button className="btn-primary" onClick={handleIssueCertificate} data-testid="save-certificate-btn">
            {editingCertificate ? 'Update' : 'Issue Certificate'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== TRANSFER MODAL ==========
export function TransferModal({
  showTransferModal,
  setShowTransferModal,
  transferForm,
  setTransferForm,
  handleTransfer,
  summary,
}) {
  return (
    <Dialog open={showTransferModal} onOpenChange={setShowTransferModal}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Transfer Units</DialogTitle>
          <DialogDescription>Transfer units from one certificate holder to another</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">From Certificate *</Label>
            <Select
              value={transferForm.from_certificate_id}
              onValueChange={(v) => {
                const shouldClearTo = transferForm.to_certificate_id === v;
                setTransferForm({
                  ...transferForm,
                  from_certificate_id: v,
                  to_certificate_id: shouldClearTo ? '' : transferForm.to_certificate_id,
                  to_holder_name: shouldClearTo ? '' : transferForm.to_holder_name,
                  to_holder_identifier: shouldClearTo ? '' : transferForm.to_holder_identifier
                });
              }}
            >
              <SelectTrigger className="mt-1" data-testid="from-cert-select">
                <SelectValue placeholder="Select source certificate" />
              </SelectTrigger>
              <SelectContent>
                {summary?.certificates?.filter(c => c.status === 'active').map((cert) => (
                  <SelectItem key={cert.certificate_id} value={cert.certificate_id}>
                    {cert.holder_name} - {cert.units} units ({cert.certificate_number})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="label-trust">To Beneficiary *</Label>
            <Select
              value={transferForm.to_certificate_id}
              onValueChange={(v) => {
                const selectedCert = summary?.certificates?.find(c => c.certificate_id === v);
                setTransferForm({
                  ...transferForm,
                  to_certificate_id: v,
                  to_holder_name: selectedCert?.holder_name || '',
                  to_holder_identifier: selectedCert?.holder_identifier || ''
                });
              }}
            >
              <SelectTrigger className="mt-1" data-testid="to-holder-select">
                <SelectValue placeholder="Select destination beneficiary" />
              </SelectTrigger>
              <SelectContent>
                {(() => {
                  return summary?.certificates?.filter(c => c.status === 'active' && c.certificate_id !== transferForm.from_certificate_id).map((cert) => (
                    <SelectItem key={cert.certificate_id} value={cert.certificate_id}>
                      {cert.holder_name} - {cert.units} units ({cert.certificate_number})
                    </SelectItem>
                  ));
                })()}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="label-trust">Units to Transfer *</Label>
            <Input
              type="number"
              step="any"
              min="0"
              value={transferForm.units}
              onChange={(e) => setTransferForm({ ...transferForm, units: e.target.value })}
              required
              className="mt-1"
              data-testid="transfer-units-input"
            />
          </div>
          <div>
            <Label className="label-trust">Reason (Optional)</Label>
            <Input
              value={transferForm.reason}
              onChange={(e) => setTransferForm({ ...transferForm, reason: e.target.value })}
              placeholder="Gift, sale, etc."
              className="mt-1"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowTransferModal(false)}>Cancel</Button>
          <Button className="btn-primary" onClick={handleTransfer} data-testid="confirm-transfer-btn">Complete Transfer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== REVOKE MODAL ==========
export function RevokeModal({
  showRevokeModal,
  setShowRevokeModal,
  revokeReason,
  setRevokeReason,
  handleRevoke,
}) {
  return (
    <Dialog open={!!showRevokeModal} onOpenChange={() => setShowRevokeModal(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-error">Revoke Certificate</DialogTitle>
          <DialogDescription>
            Are you sure you want to revoke certificate {showRevokeModal?.certificate_number}?
            This will return {showRevokeModal?.units} units to the available pool.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <Label className="label-trust">Reason (Optional)</Label>
          <Input
            value={revokeReason}
            onChange={(e) => setRevokeReason(e.target.value)}
            placeholder="e.g., Beneficiary removed by trustee resolution"
            className="mt-1"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { setShowRevokeModal(null); setRevokeReason(''); }}>Cancel</Button>
          <Button variant="destructive" onClick={() => handleRevoke(showRevokeModal)} data-testid="confirm-revoke-btn">Revoke Certificate</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== SETTINGS MODAL ==========
export function SettingsModal({
  showSettingsModal,
  setShowSettingsModal,
  settingsForm,
  setSettingsForm,
  handleSaveSettings,
  summary,
}) {
  return (
    <Dialog open={showSettingsModal} onOpenChange={setShowSettingsModal}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Unit Settings</DialogTitle>
          <DialogDescription>Configure trust unit parameters</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Allocation Mode</Label>
            <Select value={settingsForm.allocation_mode} onValueChange={(v) => setSettingsForm({ ...settingsForm, allocation_mode: v })}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="percentage">Percentage Allocation (100% cap)</SelectItem>
                <SelectItem value="units">Unit Allocation</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-1">Percentage mode uses a 100% cap. Unit mode tracks raw units separately.</p>
          </div>
          {settingsForm.allocation_mode === 'units' && <div>
            <Label className="label-trust">Authorized Unit Ceiling</Label>
            <Input type="number" min="0" value={settingsForm.authorized_units_ceiling} onChange={(e) => setSettingsForm({ ...settingsForm, authorized_units_ceiling: parseInt(e.target.value, 10) || 0 })} className="mt-1" />
            <div className="flex items-center justify-between mt-2 p-3 bg-muted/30 border border-border">
              <Label className="label-trust">Allow unlimited units</Label>
              <Switch checked={settingsForm.unlimited_units} onCheckedChange={(checked) => setSettingsForm({ ...settingsForm, unlimited_units: checked })} />
            </div>
          </div>}
          <div>
            <Label className="label-trust">Total Authorized Units</Label>
            <Input
              type="number"
              value={settingsForm.total_authorized_units}
              onChange={(e) => setSettingsForm({ ...settingsForm, total_authorized_units: parseInt(e.target.value) || 0 })}
              className="mt-1"
              data-testid="total-units-input"
            />
            <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              This is the maximum number of units that can be issued. Cannot be less than currently issued units ({summary?.total_issued_units || 0} currently issued).
            </p>
          </div>
          <div>
            <Label className="label-trust">Unit Label</Label>
            <Input
              value={settingsForm.unit_label}
              onChange={(e) => setSettingsForm({ ...settingsForm, unit_label: e.target.value })}
              placeholder="Unit, Share, Interest"
              className="mt-1"
            />
          </div>
          <div className="flex items-center justify-between p-3 bg-muted/30 border border-border">
            <div>
              <Label className="label-trust">Allow Fractional Units</Label>
              <p className="text-xs text-muted-foreground">Enable decimals (e.g., 12.5 units)</p>
            </div>
            <Switch
              checked={settingsForm.allow_fractional}
              onCheckedChange={(checked) => setSettingsForm({ ...settingsForm, allow_fractional: checked })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setShowSettingsModal(false)}>Cancel</Button>
          <Button className="btn-primary" onClick={handleSaveSettings} data-testid="save-settings-btn">Save Settings</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== DELETE CLASS BENEFICIARY MODAL ==========
export function DeleteClassModal({
  deleteConfirmClass,
  setDeleteConfirmClass,
  handleDeleteClassBeneficiary,
}) {
  return (
    <Dialog open={!!deleteConfirmClass} onOpenChange={() => setDeleteConfirmClass(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="text-error">Remove Class Beneficiary</DialogTitle>
          <DialogDescription>
            Are you sure you want to remove "{deleteConfirmClass?.class_type_label}"?
            This will remove the class designation from this trust.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setDeleteConfirmClass(null)}>Cancel</Button>
          <Button variant="destructive" onClick={() => { handleDeleteClassBeneficiary(deleteConfirmClass?.class_beneficiary_id); setDeleteConfirmClass(null); }} data-testid="confirm-delete-class-btn">
            Remove Class
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== ADD CLASS BENEFICIARY MODAL ==========
export function AddClassBeneficiaryModal({
  showClassBeneficiaryModal,
  setShowClassBeneficiaryModal,
  classBeneficiaryForm,
  setClassBeneficiaryForm,
  handleAddClassBeneficiary,
}) {
  return (
    <Dialog open={showClassBeneficiaryModal} onOpenChange={(open) => { if (!open) setClassBeneficiaryForm({ class_type: 'children', description: '', percentage: '', notes: '' }); setShowClassBeneficiaryModal(open); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Class Beneficiary</DialogTitle>
          <DialogDescription>
            Designate a class of beneficiaries defined by relationship rather than naming individuals
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Class Type *</Label>
            <Select
              value={classBeneficiaryForm.class_type}
              onValueChange={(v) => setClassBeneficiaryForm({ ...classBeneficiaryForm, class_type: v })}
            >
              <SelectTrigger className="mt-1" data-testid="class-type-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLASS_BENEFICIARY_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="label-trust">Description (Optional)</Label>
            <Input
              value={classBeneficiaryForm.description}
              onChange={(e) => setClassBeneficiaryForm({ ...classBeneficiaryForm, description: e.target.value })}
              placeholder="e.g., All children of the grantor, including after-born"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="label-trust">Allocation Percentage (Optional)</Label>
            <Input
              type="number"
              step="0.01"
              min="0"
              max="100"
              value={classBeneficiaryForm.percentage}
              onChange={(e) => setClassBeneficiaryForm({ ...classBeneficiaryForm, percentage: e.target.value })}
              placeholder="e.g., 50"
              className="mt-1"
            />
            <p className="text-xs text-muted-foreground mt-1">Percentage of trust allocated to this class pool.</p>
          </div>
          <div>
            <Label className="label-trust">Distribution Convention</Label>
            <Select value={classBeneficiaryForm.distribution_convention} onValueChange={(v) => setClassBeneficiaryForm({ ...classBeneficiaryForm, distribution_convention: v })}>
              <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="per_capita">Per Capita (equal shares by head)</SelectItem>
                <SelectItem value="per_stirpes">Per Stirpes (by family branch)</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground mt-1">TrustOffice records this convention; it does not determine legal eligibility.</p>
          </div>
          <div>
            <Label className="label-trust">Class Member Count</Label>
            <p className="text-xs text-muted-foreground mt-1">Members are recorded separately after the class is created. Confirming a member divides the reserved pool; it does not infer legal eligibility.</p>
          </div>
          <div>
            <Label className="label-trust">Notes (Optional)</Label>
            <Textarea
              value={classBeneficiaryForm.notes}
              onChange={(e) => setClassBeneficiaryForm({ ...classBeneficiaryForm, notes: e.target.value })}
              placeholder="Additional context about this class designation..."
              className="mt-1"
              rows={2}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { setShowClassBeneficiaryModal(false); setClassBeneficiaryForm({ class_type: 'children', description: '', percentage: '', notes: '' }); }}>Cancel</Button>
          <Button className="btn-primary" onClick={handleAddClassBeneficiary} data-testid="save-class-beneficiary-btn">Add Class</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== ADD PERSON MODAL ==========
export function AddPersonModal({
  showPersonModal,
  setShowPersonModal,
  personForm,
  setPersonForm,
  resetPersonForm,
  handleAddPerson,
  summary,
  allocationMode = 'percentage',
  allocationModeHelp,
  totalAuthorizedUnits = 100,
  unitLabel = 'Unit',
}) {
  return (
    <Dialog open={showPersonModal} onOpenChange={(open) => { if (!open) resetPersonForm(); setShowPersonModal(open); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add Beneficiary</DialogTitle>
          <DialogDescription>
            Add a person to benefit from this trust and choose their share.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div>
            <Label className="label-trust">Name *</Label>
            <Input
              value={personForm.name}
              onChange={(e) => setPersonForm({ ...personForm, name: e.target.value })}
              placeholder="e.g., Jane Smith"
              className="mt-1"
              data-testid="person-name-input"
            />
          </div>
          <div>
            <Label className="label-trust">Relationship to Grantor</Label>
            <Select
              value={personForm.relationship}
              onValueChange={(v) => setPersonForm({ ...personForm, relationship: v })}
            >
              <SelectTrigger className="mt-1" data-testid="person-relationship-select">
                <SelectValue placeholder="Select relationship (optional)" />
              </SelectTrigger>
              <SelectContent>
                {RELATIONSHIP_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="label-trust">
              {allocationMode === 'units' ? `${unitLabel} Allocation *` : 'Share Percentage *'}
            </Label>
            <Input
              type="number"
              step="any"
              min="0"
              max={allocationMode === 'units' ? undefined : 100}
              value={allocationMode === 'units' ? personForm.shareUnits : personForm.sharePercentage}
              onChange={(e) => setPersonForm({
                ...personForm,
                ...(allocationMode === 'units' ? { shareUnits: e.target.value } : { sharePercentage: e.target.value }),
              })}
              placeholder={allocationMode === 'units' ? 'e.g., 25' : 'e.g., 50'}
              className="mt-1"
              data-testid="person-share-input"
            />
            <p className="text-xs text-muted-foreground mt-1 flex items-start gap-1">
              <Info className="w-3 h-3 mt-0.5 flex-shrink-0" />
              {allocationModeHelp?.description || 'This automatically creates an ownership share record.'}
              {allocationModeHelp?.example && <span className="ml-1">{allocationModeHelp.example}.</span>}
              {summary && (
                <span className="ml-1 font-mono">
                  {summary.remaining_units} {unitLabel}{summary.remaining_units !== 1 ? 's' : ''} available ({((summary.remaining_units / totalAuthorizedUnits) * 100).toFixed(1)}%).
                </span>
              )}
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => { setShowPersonModal(false); resetPersonForm(); }}>Cancel</Button>
          <Button className="btn-primary" onClick={handleAddPerson} data-testid="save-beneficiary-btn">
            Add Beneficiary
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ========== ALL MODALS WRAPPER ==========
export function BeneficiariesModals({
  showCertificateModal,
  setShowCertificateModal,
  editingCertificate,
  certificateForm,
  setCertificateForm,
  resetCertificateForm,
  handleIssueCertificate,
  summary,
  trusts,
  selectedTrust,
  showTransferModal,
  setShowTransferModal,
  transferForm,
  setTransferForm,
  handleTransfer,
  showRevokeModal,
  setShowRevokeModal,
  revokeReason,
  setRevokeReason,
  handleRevoke,
  showSettingsModal,
  setShowSettingsModal,
  settingsForm,
  setSettingsForm,
  handleSaveSettings,
  deleteConfirmClass,
  setDeleteConfirmClass,
  handleDeleteClassBeneficiary,
  showClassBeneficiaryModal,
  setShowClassBeneficiaryModal,
  classBeneficiaryForm,
  setClassBeneficiaryForm,
  handleAddClassBeneficiary,
  showPersonModal,
  setShowPersonModal,
  personForm,
  setPersonForm,
  resetPersonForm,
  handleAddPerson,
  allocationMode = 'percentage',
  allocationModeHelp,
  totalAuthorizedUnits = 100,
  unitLabel = 'Unit',
  pdfPreview,
  setPdfPreview,
}) {
  return (
    <>
      <CertificateModal
        showCertificateModal={showCertificateModal}
        setShowCertificateModal={setShowCertificateModal}
        editingCertificate={editingCertificate}
        certificateForm={certificateForm}
        setCertificateForm={setCertificateForm}
        resetCertificateForm={resetCertificateForm}
        handleIssueCertificate={handleIssueCertificate}
        summary={summary}
        trusts={trusts}
        selectedTrust={selectedTrust}
      />

      <TransferModal
        showTransferModal={showTransferModal}
        setShowTransferModal={setShowTransferModal}
        transferForm={transferForm}
        setTransferForm={setTransferForm}
        handleTransfer={handleTransfer}
        summary={summary}
      />

      <RevokeModal
        showRevokeModal={showRevokeModal}
        setShowRevokeModal={setShowRevokeModal}
        revokeReason={revokeReason}
        setRevokeReason={setRevokeReason}
        handleRevoke={handleRevoke}
      />

      <SettingsModal
        showSettingsModal={showSettingsModal}
        setShowSettingsModal={setShowSettingsModal}
        settingsForm={settingsForm}
        setSettingsForm={setSettingsForm}
        handleSaveSettings={handleSaveSettings}
        summary={summary}
      />

      <DeleteClassModal
        deleteConfirmClass={deleteConfirmClass}
        setDeleteConfirmClass={setDeleteConfirmClass}
        handleDeleteClassBeneficiary={handleDeleteClassBeneficiary}
      />

      <AddClassBeneficiaryModal
        showClassBeneficiaryModal={showClassBeneficiaryModal}
        setShowClassBeneficiaryModal={setShowClassBeneficiaryModal}
        classBeneficiaryForm={classBeneficiaryForm}
        setClassBeneficiaryForm={setClassBeneficiaryForm}
        handleAddClassBeneficiary={handleAddClassBeneficiary}
      />

      <AddPersonModal
        showPersonModal={showPersonModal}
        setShowPersonModal={setShowPersonModal}
        personForm={personForm}
        setPersonForm={setPersonForm}
        resetPersonForm={resetPersonForm}
        handleAddPerson={handleAddPerson}
        summary={summary}
        allocationMode={allocationMode}
        allocationModeHelp={allocationModeHelp}
        totalAuthorizedUnits={totalAuthorizedUnits}
        unitLabel={unitLabel}
      />

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        open={pdfPreview.show}
        onOpenChange={(isOpen) => !isOpen && setPdfPreview({ show: false, loading: false, data: null, filename: '' })}
        pdfBase64={pdfPreview.data}
        filename={pdfPreview.filename}
        title="Unit Certificate"
      />
    </>
  );
}