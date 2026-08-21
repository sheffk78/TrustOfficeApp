import { Button } from '@/components/ui/button';
import { Plus, UsersRound, Trash2, Info } from 'lucide-react';
import { EDUCATION_SECTIONS } from './constants';

// ========== CLASS BENEFICIARIES TAB ==========
export function ClassBeneficiariesTab({
  overviewData,
  setShowClassBeneficiaryModal,
  setDeleteConfirmClass,
}) {
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
              <div key={cb.class_beneficiary_id} className="p-4 flex items-center justify-between hover:bg-muted/20 transition-colors">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
                    <UsersRound className="w-6 h-6 text-navy dark:text-gold" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-navy dark:text-foreground">{cb.class_type_label}</p>
                      {cb.percentage > 0 && (
                        <span className="px-2 py-0.5 text-xs font-mono bg-gold/10 text-gold">
                          {cb.percentage}%
                        </span>
                      )}
                    </div>
                    {cb.description && (
                      <p className="text-sm text-muted-foreground">{cb.description}</p>
                    )}
                    {cb.notes && (
                      <p className="text-xs text-muted-foreground mt-1">{cb.notes}</p>
                    )}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-error hover:text-error hover:bg-error/10 dark:hover:bg-error/20"
                  onClick={() => setDeleteConfirmClass(cb)}
                  data-testid={`delete-class-${cb.class_beneficiary_id}`}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default ClassBeneficiariesTab;