import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Users, Plus, Pencil, AlertCircle, Settings, Info } from 'lucide-react';
import { extractRelationship } from './constants';
import { EDUCATION_SECTIONS } from './constants';

// ========== EDUCATION BANNER COMPONENT ==========
function EducationBanner({ title, content }) {
  return (
    <div className="mb-4 p-3 bg-muted/30 border border-border rounded-md text-sm text-muted-foreground">
      <p className="font-mono text-[10px] uppercase tracking-widest text-navy mb-2">
        <Info className="w-3.5 h-3.5 inline mr-1" />
        {title}
      </p>
      <p className="text-xs">{content}</p>
    </div>
  );
}

// ========== BENEFICIARIES TAB ==========
export function BeneficiaryListTab({
  overviewData,
  loading,
  handleOpenPersonModal,
  openEditModal,
  summary,
  setShowSettingsModal,
}) {
  const unitLabel = summary?.settings?.unit_label || 'Unit';

  return (
    <>
      {/* Fully Allocated Warning */}
      {summary && summary.remaining_units === 0 && (
        <div className="mb-6 p-4 border-2 border-gold/40 bg-gold/5 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-mono text-xs font-medium text-navy mb-1">All {(summary.settings?.total_authorized_units || 100)} {(summary.settings?.unit_label || 'Unit')}s are allocated</p>
            <p className="text-sm text-muted-foreground mb-2">To add another beneficiary, increase the authorized units or cancel an existing certificate.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowSettingsModal?.(true)} className="font-mono text-xs">
                <Settings className="w-3.5 h-3.5 mr-1" /> Increase Authorized Units
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Primary CTA */}
      <div className="card-trust p-4 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Add the people or organizations you want to benefit from this trust
            </p>
          </div>
          <Button className="btn-primary" onClick={handleOpenPersonModal} disabled={summary && summary.remaining_units === 0} data-testid="add-beneficiary-btn">
            <Plus className="w-4 h-4 mr-2" />
            Add Beneficiary
          </Button>
        </div>
      </div>

      {/* Education Banner */}
      <div className="mb-6">
        <EducationBanner
          title={EDUCATION_SECTIONS.allocationModes.title}
          content={EDUCATION_SECTIONS.allocationModes.content}
        />
      </div>

      {/* Beneficiary List */}
      <div className="card-trust overflow-hidden">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Users className="w-4 h-4 text-navy dark:text-gold" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Beneficiaries</h2>
          <span className="ml-auto text-xs text-muted-foreground">{overviewData?.beneficiaries?.length || 0} beneficiaries</span>
        </div>

        {loading ? (
          <div className="p-8 text-center">
            <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
          </div>
        ) : !overviewData?.beneficiaries?.length ? (
          <div className="p-8 text-center">
            <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
            <p className="text-muted-foreground mb-2">No beneficiaries yet</p>
            <p className="text-sm text-muted-foreground mb-4">
              Add a person, organization, or other beneficiary — then choose what share of the trust they receive.
            </p>
            <Button className="btn-primary" onClick={handleOpenPersonModal} disabled={summary && summary.remaining_units === 0} data-testid="empty-add-beneficiary-btn">
              <Plus className="w-4 h-4 mr-2" /> Add Your First Beneficiary
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {overviewData.beneficiaries.map((ben, index) => {
              const relationship = extractRelationship(ben);
              return (
                <div key={`${ben.holder_name}-${ben.holder_identifier || ''}-${ben.holder_type || 'individual'}`} className="p-4 flex items-center justify-between gap-4 hover:bg-muted/20 transition-colors" data-testid={`person-row-${index}`}>
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                      <Users className="w-6 h-6 text-navy dark:text-gold" />
                    </div>
                    <div>
                      <p className="font-medium text-navy dark:text-foreground">{ben.holder_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {relationship ? (
                          <span>{relationship} to grantor</span>
                        ) : (
                          <span>{ben.holder_type || 'Individual'}</span>
                        )}
                      </p>
                      {ben.email && (
                        <p className="text-xs text-muted-foreground">{ben.email}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <p className="font-mono text-lg text-navy dark:text-foreground">{ben.total_units} <span className="text-xs text-muted-foreground">{unitLabel}{ben.total_units !== 1 ? 's' : ''}</span></p>
                    </div>
                    <div className="text-right min-w-[70px]">
                      <p className="font-mono text-lg text-gold">{ben.percentage.toFixed(2)}%</p>
                      <p className="text-xs text-muted-foreground">share</p>
                    </div>
                    {ben.certificates?.[0] && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => openEditModal?.(ben.certificates[0])}
                        data-testid={`edit-beneficiary-${index}`}
                        aria-label={`Edit ${ben.holder_name}`}
                      >
                        <Pencil className="w-3.5 h-3.5 mr-1" />
                        Edit
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}

export default BeneficiaryListTab;