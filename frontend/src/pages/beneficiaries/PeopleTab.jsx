import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Users, Plus, Bot } from 'lucide-react';
import { extractRelationship } from './constants';

// ========== PEOPLE TAB ==========
export function PeopleTab({
  overviewData,
  loading,
  handleOpenPersonModal,
}) {
  return (
    <>
      {/* Primary CTA */}
      <div className="card-trust p-4 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Add the people you want to benefit from this trust
            </p>
          </div>
          <Button className="btn-primary" onClick={handleOpenPersonModal} data-testid="add-beneficiary-btn">
            <Plus className="w-4 h-4 mr-2" />
            Add Beneficiary
          </Button>
        </div>
      </div>

      {/* People List */}
      <div className="card-trust overflow-hidden">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Users className="w-4 h-4 text-navy dark:text-gold" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Beneficiaries</h2>
          <span className="ml-auto text-xs text-muted-foreground">{overviewData?.beneficiaries?.length || 0} people</span>
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
              Add a person — like a spouse, child, or charity — and choose what share of the trust they receive.
            </p>
            <Button className="btn-primary" onClick={handleOpenPersonModal} data-testid="empty-add-beneficiary-btn">
              <Plus className="w-4 h-4 mr-2" /> Add Your First Beneficiary
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {overviewData.beneficiaries.map((ben, index) => {
              const relationship = extractRelationship(ben);
              return (
                <div key={`${ben.holder_name}-${ben.holder_identifier || ''}-${ben.holder_type || 'individual'}`} className="p-4 flex items-center justify-between hover:bg-muted/20 transition-colors" data-testid={`person-row-${index}`}>
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
                  <div className="text-right">
                    <p className="font-mono text-lg text-gold">{ben.percentage.toFixed(2)}%</p>
                    <p className="text-xs text-muted-foreground">share</p>
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

export default PeopleTab;