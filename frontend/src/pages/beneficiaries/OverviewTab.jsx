import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import {
  PieChart, Award, FileCheck, Users, Plus,
  ChevronDown, ChevronUp, Bot, Pencil, AlertCircle, Settings, UsersRound,
  Percent, Hash,
} from 'lucide-react';
import { OwnershipPieChart } from './OwnershipPieChart';
import { beneficiaryKey, formatDate } from './constants';
import { DISCLAIMER_TEXT, EDUCATION_SECTIONS } from './constants';
import { formatAllocation } from './hooks';

// ========== OVERVIEW TAB ==========

function SummaryCard({ dataTestId, bgClass, icon, label, value }) {
  return (
    <div className="card-trust p-4" data-testid={dataTestId}>
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 ${bgClass} flex items-center justify-center`}>
          {icon}
        </div>
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
          <p className="font-serif text-2xl text-navy dark:text-foreground">{value}</p>
        </div>
      </div>
    </div>
  );
}

function HolderRow({ ben, index, expandedHolder, setExpandedHolder, openEditModal, formatDateFn, overviewData, allocationMode }) {
  const key = beneficiaryKey(ben);
  const isExpanded = expandedHolder === key;
  const unitLabel = overviewData.unit_label || 'Unit';
  const totalAuthorized = overviewData.total_authorized_units || 100;
  const alloc = formatAllocation(allocationMode, ben.total_units, ben.percentage, totalAuthorized, unitLabel);

  return (
    <div key={key} data-testid={`beneficiary-row-${index}`}>
      <button
        onClick={() => setExpandedHolder(isExpanded ? null : key)}
        className="w-full p-4 flex items-center justify-between hover:bg-muted/20 transition-colors"
      >
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-navy/10 dark:bg-gold/10 flex items-center justify-center font-serif text-navy dark:text-gold">
            {index + 1}
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <p className="font-medium text-navy dark:text-foreground">{ben.holder_name}</p>
              {ben.holder_type && ben.holder_type !== 'individual' && (
                <span className="px-2 py-0.5 text-xs font-mono bg-navy/10 dark:bg-gold/10 text-navy dark:text-gold rounded">
                  {ben.holder_type}
                </span>
              )}
            </div>
            {ben.holder_identifier && (
              <p className="text-xs text-muted-foreground font-mono">{ben.holder_identifier}</p>
            )}
            {ben.email && (
              <p className="text-xs text-muted-foreground">{ben.email}</p>
            )}
            {ben.phone && (
              <p className="text-xs text-muted-foreground">{ben.phone}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-right">
            <p className="font-mono text-lg text-navy dark:text-foreground">{alloc.primary}</p>
            <p className="text-xs text-muted-foreground">{alloc.primaryLabel}</p>
          </div>
          <div className="text-right min-w-[80px]">
            <p className="font-mono text-lg text-gold">{alloc.secondary}</p>
            <p className="text-xs text-muted-foreground">{alloc.secondaryLabel}</p>
          </div>
          {isExpanded ? <ChevronUp className="w-5 h-5 text-muted-foreground" /> : <ChevronDown className="w-5 h-5 text-muted-foreground" />}
        </div>
      </button>

      {isExpanded && (
        <div className="bg-muted/30 p-4 border-t border-border">
          <div className="flex items-center justify-between mb-3">
            <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {ben.certificate_count} Certificate{ben.certificate_count !== 1 ? 's' : ''}
            </p>
            <Link
              to={`/trust-assistant?prompt=${encodeURIComponent(`Draft meeting minutes to add ${ben.holder_name} as a beneficiary.`)}`}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs text-gold hover:bg-gold/10 transition-colors"
              title="Ask Trust Assistant to draft minutes"
              data-testid={`ta-add-beneficiary-${index}`}
            >
              <Bot className="w-3.5 h-3.5" />
              Draft Minutes
            </Link>
          </div>
          <div className="space-y-2">
            {ben.certificates.map((cert) => {
              const certAlloc = formatAllocation(allocationMode, cert.units, cert.percentage || (cert.units / totalAuthorized * 100), totalAuthorized, unitLabel);
              return (
                <div key={cert.certificate_id} className="flex items-center justify-between p-3 bg-background border border-border">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-sm text-navy dark:text-gold">{cert.certificate_number}</span>
                    <span className="text-sm text-muted-foreground">{certAlloc.primary} ({certAlloc.secondary})</span>
                    {cert.status && cert.status !== 'active' && (
                      <span className="px-1.5 py-0.5 text-[10px] font-mono bg-muted text-muted-foreground rounded">
                        {cert.status}
                      </span>
                    )}
                    {cert.version && cert.version > 1 && (
                      <span className="px-1.5 py-0.5 text-[10px] font-mono bg-navy/5 text-muted-foreground rounded">
                        v{cert.version}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {cert.status !== 'replaced' && cert.status !== 'superseded' && (
                      <Button variant="ghost" size="sm" onClick={() => openEditModal(cert)} data-testid={`edit-cert-${cert.certificate_id}`}>
                        <Pencil className="w-3.5 h-3.5" />
                        <span className="ml-1 text-xs">Edit</span>
                      </Button>
                    )}
                    <span className="text-xs text-muted-foreground font-mono">Issued {formatDateFn(cert.issue_date)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function ClassHolderRow({ cb, index, setActiveTab }) {
  return (
    <div
      key={cb.class_beneficiary_id}
      data-testid={`class-beneficiary-row-${index}`}
      className="p-4 flex items-center justify-between hover:bg-muted/20 transition-colors"
    >
      <div className="flex items-center gap-4">
        <div className="w-10 h-10 bg-gold/10 dark:bg-gold/20 flex items-center justify-center">
          <UsersRound className="w-5 h-5 text-gold" />
        </div>
        <div className="text-left">
          <div className="flex items-center gap-2">
            <p className="font-medium text-navy dark:text-foreground">{cb.class_type_label}</p>
            <span className="px-2 py-0.5 text-xs font-mono bg-gold/10 text-gold rounded">
              Class
            </span>
            {cb.distribution_convention && (
              <span className="px-2 py-0.5 text-xs font-mono bg-muted text-muted-foreground rounded">
                {cb.distribution_convention === 'per_stirpes' ? 'Per Stirpes' : 'Per Capita'}
              </span>
            )}
          </div>
          {cb.description && (
            <p className="text-sm text-muted-foreground">{cb.description}</p>
          )}
          {cb.member_count > 0 && (
            <p className="text-xs text-muted-foreground mt-0.5">{cb.member_count} confirmed member{cb.member_count !== 1 ? 's' : ''}</p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-6">
        <div className="text-right">
          <p className="font-mono text-lg text-gold">{cb.percentage.toFixed(2)}%</p>
          <p className="text-xs text-muted-foreground">reserved pool</p>
        </div>
      </div>
    </div>
  );
}

export function OverviewTab({
  overviewData,
  loading,
  summary,
  expandedHolder,
  setExpandedHolder,
  openEditModal,
  setActiveTab,
  handleOpenCertificateModal,
  formatDateFn,
  allocationMode,
}) {
  if (loading) {
    return (
      <div className="card-trust p-8 text-center">
        <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
        <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (!overviewData) {
    return (
      <div className="card-trust p-8 text-center">
        <p className="text-muted-foreground">No data available</p>
      </div>
    );
  }

  const classBens = overviewData.class_beneficiaries || [];
  const totalBeneficiaries = overviewData.beneficiaries.length + classBens.length;
  const totalAllocatedPct = overviewData.total_allocated_percentage ?? 0;

  return (
    <>
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <SummaryCard
          dataTestId="total-authorized-card"
          bgClass="bg-navy/10 dark:bg-gold/10"
          icon={<Award className="w-5 h-5 text-navy dark:text-gold" />}
          label="Total Available"
          value={overviewData.total_authorized_units}
        />
        <SummaryCard
          dataTestId="issued-units-card"
          bgClass="bg-success/10 dark:bg-success/20"
          icon={<FileCheck className="w-5 h-5 text-success dark:text-success" />}
          label="Issued"
          value={overviewData.total_issued_units}
        />
        <SummaryCard
          dataTestId="remaining-units-card"
          bgClass="bg-gold/10 dark:bg-gold/20"
          icon={<PieChart className="w-5 h-5 text-gold" />}
          label="Remaining"
          value={overviewData.remaining_units}
        />
        <SummaryCard
          dataTestId="beneficiaries-count-card"
          bgClass="bg-warning/10 dark:bg-warning/20"
          icon={<Users className="w-5 h-5 text-warning dark:text-warning" />}
          label="Beneficiaries"
          value={totalBeneficiaries}
        />
      </div>

      {/* Allocation Mode Indicator */}
      {summary?.settings && (
        <div className="mb-4 flex items-center gap-2">
          {allocationMode === 'units' ? (
            <Hash className="w-4 h-4 text-navy dark:text-gold" />
          ) : (
            <Percent className="w-4 h-4 text-navy dark:text-gold" />
          )}
          <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
            {allocationMode === 'units' ? 'Unit Mode' : 'Percentage Mode'}
          </span>
          <span className="text-xs text-muted-foreground">
            {allocationMode === 'units'
              ? `Raw units tracked (ceiling: ${summary.settings.unlimited_units ? 'unlimited' : (summary.settings.authorized_units_ceiling ?? 'N/A')})`
              : '100% cap — units derived from percentage'
            }
          </span>
        </div>
      )}

      {/* Allocation Layer Summary */}
      {classBens.length > 0 && (
        <div className="mb-6 p-4 border border-border bg-muted/20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <PieChart className="w-4 h-4 text-navy dark:text-gold" />
            <div>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Allocation Layers</p>
              <p className="font-serif text-lg text-navy dark:text-foreground">
                {(overviewData.certificate_percentage_total ?? totalAllocatedPct).toFixed(2)}%
                <span className="text-sm text-muted-foreground"> issued</span>
                <span className="text-sm text-muted-foreground ml-2">
                  + {(overviewData.class_beneficiary_percentage_total?.toFixed(2) || 0)}% reserved to classes
                </span>
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Class pools are contingent reservations and may overlap certificate holders.
              </p>
            </div>
          </div>
          {(overviewData.certificate_percentage_total ?? 0) > 100 && (
            <div className="flex items-center gap-2 text-error">
              <AlertCircle className="w-4 h-4" />
              <span className="text-xs font-mono">Issued shares exceed 100%</span>
            </div>
          )}
        </div>
      )}

      {/* Fully Allocated Warning */}
      {overviewData.remaining_units === 0 && (
        <div className="mb-6 p-4 border-2 border-gold/40 bg-gold/5 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-mono text-xs font-medium text-navy mb-1">All {overviewData.total_authorized_units || 100} {overviewData.unit_label || 'Unit'}s are allocated</p>
            <p className="text-sm text-muted-foreground mb-2">To add another beneficiary, increase the authorized units or cancel an existing certificate.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setActiveTab('certificates')} className="font-mono text-xs">
                <Settings className="w-3.5 h-3.5 mr-1" /> Go to Shares
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Pie Chart & Holder List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-trust p-6" data-testid="ownership-chart">
          <div className="flex items-center gap-2 mb-6">
            <PieChart className="w-4 h-4 text-navy dark:text-gold" />
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Ownership Distribution</h2>
          </div>
          {totalBeneficiaries > 0 ? (
            <OwnershipPieChart
              beneficiaries={overviewData.beneficiaries}
              totalAuthorized={overviewData.total_authorized_units}
              classBeneficiaries={classBens}
            />
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
              <p>No beneficiaries yet</p>
              <Button className="btn-primary mt-4" onClick={() => { setActiveTab('certificates'); handleOpenCertificateModal(); }}>
                <Plus className="w-4 h-4 mr-2" /> Add First Ownership Share
              </Button>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 card-trust overflow-hidden">
          <div className="p-4 border-b border-border flex items-center gap-2">
            <Users className="w-4 h-4 text-navy dark:text-gold" />
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Share Holders</h2>
            {classBens.length > 0 && (
              <span className="ml-auto text-xs text-muted-foreground">
                {overviewData.beneficiaries.length} named + {classBens.length} class
              </span>
            )}
          </div>

          {totalBeneficiaries === 0 ? (
            <div className="p-8 text-center">
              <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
              <p className="text-muted-foreground">No beneficiaries yet</p>
            </div>
          ) : (
            <div className="divide-y divide-border max-h-[500px] overflow-y-auto">
              {overviewData.beneficiaries.map((ben, index) => (
                <HolderRow
                  key={beneficiaryKey(ben)}
                  ben={ben}
                  index={index}
                  expandedHolder={expandedHolder}
                  setExpandedHolder={setExpandedHolder}
                  openEditModal={openEditModal}
                  formatDateFn={formatDateFn}
                  overviewData={overviewData}
                  allocationMode={allocationMode}
                />
              ))}
              {/* Class beneficiaries inline in the holder list */}
              {classBens.map((cb, index) => (
                <ClassHolderRow
                  key={cb.class_beneficiary_id}
                  cb={cb}
                  index={overviewData.beneficiaries.length + index}
                  setActiveTab={setActiveTab}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      {/* Education & Disclaimer */}
      <div className="mt-8 border-t border-border pt-6">
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground mb-3">Understanding Trust Allocations</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.beneficiaryTypes.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.beneficiaryTypes.content}</p>
          </div>
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.whatAreUnits.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.whatAreUnits.content}</p>
          </div>
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.unitsVsPercentage.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.unitsVsPercentage.content}</p>
          </div>
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.allocationModes.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.allocationModes.content}</p>
          </div>
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.classBeneficiaries.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.classBeneficiaries.content}</p>
          </div>
          <div className="p-3 bg-muted/30 border border-border rounded">
            <p className="font-medium text-navy dark:text-foreground mb-1">{EDUCATION_SECTIONS.distributionConventions.title}</p>
            <p className="text-muted-foreground text-xs whitespace-pre-line">{EDUCATION_SECTIONS.distributionConventions.content}</p>
          </div>
        </div>
        <div className="mt-4 p-3 bg-warning/10 border border-warning/30 rounded text-xs text-warning-foreground">
          <strong>Disclaimer:</strong> {DISCLAIMER_TEXT.noLegalAdvice}
        </div>
      </div>
    </>
  );
}

export default OverviewTab;