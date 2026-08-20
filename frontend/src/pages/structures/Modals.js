import { Loader2 } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { ENTITY_TYPES, RELATIONSHIP_TYPES } from './constants';

/**
 * Normalise a trust's `trustees` value into a display string.
 * Trustees may be stored as a comma-separated string or an array.
 */
function formatTrustees(trustees) {
  if (!trustees) return '';
  if (Array.isArray(trustees)) return trustees.filter(Boolean).join(', ');
  return String(trustees);
}

export function EntityModal({ show, onClose, newEntity, setNewEntity, entityModalTrustId, setEntityModalTrustId, viewMode, trusts, selectedTrust, onSubmit, formLoading }) {
  // Resolve the currently-selected trust object: in all-trusts mode it's the
  // one picked in the dropdown; in per-trust mode it's the globally selected trust.
  const activeTrust = useMemo(() => {
    if (viewMode === 'all-trusts') {
      if (!entityModalTrustId || !trusts) return null;
      return trusts.find(t => t.trust_id === entityModalTrustId) || null;
    }
    return selectedTrust || null;
  }, [viewMode, entityModalTrustId, trusts, selectedTrust]);

  // Track whether each inheritable field has been manually edited by the user,
  // so we don't clobber their edits when the trust selection changes.
  const userEdited = useMemo(
    () => ({ trustee_names: !!newEntity.trustee_names, governing_law: !!newEntity.governing_law, ein: !!newEntity.ein }),
    // Intentionally only recompute when the trust changes, not on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeTrust]
  );

  // Auto-fill inheritable fields from the selected trust's Settings data.
  // Runs when the modal opens or when the trust selection changes, and only
  // overwrites a field if the user hasn't already typed into it.
  useEffect(() => {
    if (!show) return;
    setNewEntity(prev => {
      const updates = {};
      const trusteesStr = formatTrustees(activeTrust?.trustees);
      if (trusteesStr && !userEdited.trustee_names) updates.trustee_names = trusteesStr;
      const stateCode = activeTrust?.state_code || '';
      if (stateCode && !userEdited.governing_law) updates.governing_law = stateCode;
      const ein = activeTrust?.ein || '';
      if (ein && !userEdited.ein) updates.ein = ein;
      if (Object.keys(updates).length === 0) return prev;
      return { ...prev, ...updates };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [show, activeTrust]);

  // Inherited-from-Settings badge — shown next to a field label when its value
  // matches what we'd derive from the active trust.
  const inherited = (fieldName) => {
    if (!activeTrust) return false;
    if (fieldName === 'trustee_names') return formatTrustees(activeTrust.trustees) && newEntity.trustee_names === formatTrustees(activeTrust.trustees);
    if (fieldName === 'governing_law') return activeTrust.state_code && newEntity.governing_law === activeTrust.state_code;
    if (fieldName === 'ein') return activeTrust.ein && newEntity.ein === activeTrust.ein;
    return false;
  };

  return (
    <Dialog open={show} onOpenChange={(open) => {
      onClose(open);
      if (!open) setEntityModalTrustId('');
    }}>
      <DialogContent className="sm:max-w-md" data-testid="entity-modal">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy">Create New Entity</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {viewMode === 'all-trusts' && (
            <div>
              <Label className="label-trust">Trust *</Label>
              <Select value={entityModalTrustId} onValueChange={setEntityModalTrustId}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue placeholder="Select a trust" />
                </SelectTrigger>
                <SelectContent>
                  {trusts.map(t => (
                    <SelectItem key={t.trust_id} value={t.trust_id}>
                      {t.trust_name || t.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          <div>
            <Label className="label-trust">Entity Name *</Label>
            <Input
              value={newEntity.name}
              onChange={(e) => setNewEntity({ ...newEntity, name: e.target.value })}
              placeholder="e.g., Smith Family Trust"
              className="input-trust mt-1"
              data-testid="entity-name"
            />
          </div>
          <div>
            <Label className="label-trust">Entity Type</Label>
            <Select value={newEntity.entity_type} onValueChange={(v) => setNewEntity({ ...newEntity, entity_type: v })}>
              <SelectTrigger className="input-trust mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ENTITY_TYPES.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Label className="label-trust">Trustee Name(s)</Label>
              {inherited('trustee_names') && (
                <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5" data-testid="trustee-inherited-badge">
                  Inherited from Settings
                </span>
              )}
            </div>
            <Input
              value={newEntity.trustee_names}
              onChange={(e) => setNewEntity({ ...newEntity, trustee_names: e.target.value })}
              placeholder="e.g., John Smith, Jane Smith"
              className="input-trust mt-1"
              data-testid="entity-trustee-names"
            />
          </div>
          <div>
            <Label className="label-trust">Legal Name (Optional)</Label>
            <Input
              value={newEntity.legal_name}
              onChange={(e) => setNewEntity({ ...newEntity, legal_name: e.target.value })}
              placeholder="Full legal name if different"
              className="input-trust mt-1"
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Label className="label-trust">Governing Law / Jurisdiction</Label>
              {inherited('governing_law') && (
                <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5" data-testid="governing-law-inherited-badge">
                  Inherited from Settings
                </span>
              )}
            </div>
            <Input
              value={newEntity.governing_law}
              onChange={(e) => setNewEntity({ ...newEntity, governing_law: e.target.value })}
              placeholder="e.g., Delaware, California"
              className="input-trust mt-1"
              data-testid="entity-governing-law"
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <Label className="label-trust">EIN (Optional)</Label>
              {inherited('ein') && (
                <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-1.5 py-0.5" data-testid="ein-inherited-badge">
                  Inherited from Settings
                </span>
              )}
            </div>
            <Input
              value={newEntity.ein}
              onChange={(e) => setNewEntity({ ...newEntity, ein: e.target.value })}
              placeholder="e.g., 12-3456789"
              className="input-trust mt-1"
              data-testid="entity-ein"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} className="btn-secondary">Cancel</Button>
          <Button onClick={onSubmit} disabled={formLoading} className="btn-primary" data-testid="submit-entity-btn">
            {formLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Create Entity
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function RelationshipModal({
  show, onClose, newRelationship, setNewRelationship,
  relModalTrustFilter, setRelModalTrustFilter,
  isTrustToTrust, setIsTrustToTrust,
  viewMode, trusts, entities, getTrustName, onSubmit, formLoading,
}) {
  const handleTrustToTrustToggle = (checked) => {
    setIsTrustToTrust(checked);
    setNewRelationship(prev => ({ ...prev, parent_entity_id: '', child_entity_id: '' }));
    if (checked) {
      setNewRelationship(prev => ({ ...prev, relationship_type: 'receives_distributions_from' }));
    } else {
      setNewRelationship(prev => ({ ...prev, relationship_type: 'owns' }));
    }
  };

  const handleTrustFilterChange = (v) => {
    setRelModalTrustFilter(v);
    setNewRelationship(prev => ({ ...prev, parent_entity_id: '', child_entity_id: '' }));
  };

  const filterEntity = (e, excludeId) => {
    if (excludeId && e.entity_id === excludeId) return false;
    if (viewMode === 'all-trusts') {
      if (isTrustToTrust) return e.entity_type === 'Trust';
      return relModalTrustFilter ? e.trust_id === relModalTrustFilter : false;
    }
    return true;
  };

  const entityLabel = (e) =>
    isTrustToTrust ? `${getTrustName(e.trust_id)} — ${e.name} (Trust)` : `${e.name} (${e.entity_type})`;

  return (
    <Dialog open={show} onOpenChange={(open) => {
      onClose(open);
      if (!open) {
        setRelModalTrustFilter('');
        setIsTrustToTrust(false);
        setNewRelationship({ parent_entity_id: '', child_entity_id: '', relationship_type: 'owns', ownership_percentage: '', notes: '' });
      }
    }}>
      <DialogContent className="w-[calc(100vw-2rem)] max-w-md max-h-[90vh] overflow-y-auto" data-testid="relationship-modal">
        <DialogHeader>
          <DialogTitle className="font-serif text-xl text-navy">Add Relationship</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {/* Trust-to-Trust toggle */}
          {viewMode === 'all-trusts' && (
            <div className="border border-purple-200 bg-purple-50/50 p-3" data-testid="trust-to-trust-toggle-section">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isTrustToTrust}
                  onChange={(e) => handleTrustToTrustToggle(e.target.checked)}
                  className="w-4 h-4 accent-purple-600"
                  data-testid="trust-to-trust-checkbox"
                />
                <span className="text-sm font-medium text-navy">Trust-to-Trust Relationship</span>
              </label>
              <p className="text-xs text-muted-foreground mt-1 ml-6">
                {isTrustToTrust
                  ? 'Select trust-type entities from any trust. Relationship type defaults to "Receives Distributions From".'
                  : 'Enable to create cross-trust relationships between trust entities (e.g., beneficiary distributions).'}
              </p>
            </div>
          )}

          {/* Trust filter */}
          {viewMode === 'all-trusts' && !isTrustToTrust && (
            <div>
              <Label className="label-trust">Trust (filter entities) *</Label>
              <Select value={relModalTrustFilter} onValueChange={handleTrustFilterChange}>
                <SelectTrigger className="input-trust mt-1">
                  <SelectValue placeholder="Select a trust to filter entities" />
                </SelectTrigger>
                <SelectContent>
                  {trusts.map(t => (
                    <SelectItem key={t.trust_id} value={t.trust_id}>{t.trust_name || t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">Parent and child entities must be from the same trust</p>
            </div>
          )}

          {viewMode === 'all-trusts' && isTrustToTrust && (
            <p className="text-xs text-purple-600 font-medium">
              Trust-to-Trust mode: showing all trust-type entities across all trusts
            </p>
          )}

          {/* Parent Entity */}
          <div>
            <Label className="label-trust">Parent Entity *</Label>
            <Select value={newRelationship.parent_entity_id} onValueChange={(v) => setNewRelationship({ ...newRelationship, parent_entity_id: v })}>
              <SelectTrigger className="input-trust mt-1"><SelectValue placeholder="Select parent entity" /></SelectTrigger>
              <SelectContent>
                {entities.filter(e => filterEntity(e)).map(e => (
                  <SelectItem key={e.entity_id} value={e.entity_id}>{entityLabel(e)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Relationship Type */}
          <div>
            <Label className="label-trust">Relationship Type</Label>
            <Select value={newRelationship.relationship_type} onValueChange={(v) => setNewRelationship({ ...newRelationship, relationship_type: v })}>
              <SelectTrigger className="input-trust mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                {RELATIONSHIP_TYPES.map(t => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Child Entity */}
          <div>
            <Label className="label-trust">Child Entity *</Label>
            <Select value={newRelationship.child_entity_id} onValueChange={(v) => setNewRelationship({ ...newRelationship, child_entity_id: v })}>
              <SelectTrigger className="input-trust mt-1"><SelectValue placeholder="Select child entity" /></SelectTrigger>
              <SelectContent>
                {entities.filter(e => filterEntity(e, newRelationship.parent_entity_id)).map(e => (
                  <SelectItem key={e.entity_id} value={e.entity_id}>{entityLabel(e)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Ownership Percentage */}
          <div>
            <Label className="label-trust">Ownership Percentage (Optional)</Label>
            <Input
              type="number"
              value={newRelationship.ownership_percentage}
              onChange={(e) => setNewRelationship({ ...newRelationship, ownership_percentage: e.target.value })}
              placeholder="e.g., 100"
              className="input-trust mt-1"
              min="0" max="100"
            />
          </div>

          {/* Notes */}
          <div>
            <Label className="label-trust">Notes (Optional)</Label>
            <Textarea
              value={newRelationship.notes}
              onChange={(e) => setNewRelationship({ ...newRelationship, notes: e.target.value })}
              placeholder="Any additional notes..."
              className="input-trust mt-1"
              rows={2}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onClose(false)} className="btn-secondary">Cancel</Button>
          <Button onClick={onSubmit} disabled={formLoading} className="btn-primary" data-testid="submit-relationship-btn">
            {formLoading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
            Add Relationship
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}