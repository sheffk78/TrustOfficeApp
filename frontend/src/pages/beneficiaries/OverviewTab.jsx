import { Button } from '@/components/ui/button';
import {
  PieChart, Award, FileCheck, Users, Plus,
  ChevronDown, ChevronUp, Bot, Pencil,
} from 'lucide-react';
import { OwnershipPieChart } from './OwnershipPieChart';
import { beneficiaryKey, formatDate } from './constants';

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

function HolderRow({ ben, index, expandedHolder, setExpandedHolder, openEditModal, formatDateFn, overviewData }) {
  const key = beneficiaryKey(ben);
  const isExpanded = expandedHolder === key;

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
            <p className="font-mono text-lg text-navy dark:text-foreground">{ben.total_units}</p>
            <p className="text-xs text-muted-foreground">{overviewData.unit_label}s</p>
          </div>
          <div className="text-right min-w-[80px]">
            <p className="font-mono text-lg text-gold">{ben.percentage.toFixed(2)}%</p>
            <p className="text-xs text-muted-foreground">ownership</p>
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
            {ben.certificates.map((cert) => (
              <div key={cert.certificate_id} className="flex items-center justify-between p-3 bg-background border border-border">
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-navy dark:text-gold">{cert.certificate_number}</span>
                  <span className="text-sm text-muted-foreground">{cert.units} units</span>
                </div>
                <div className="flex items-center gap-3">
                  <Button variant="ghost" size="sm" onClick={() => openEditModal(cert)} data-testid={`edit-cert-${cert.certificate_id}`}>
                    <Pencil className="w-3.5 h-3.5" />
                    <span className="ml-1 text-xs">Edit</span>
                  </Button>
                  <span className="text-xs text-muted-foreground font-mono">Issued {formatDateFn(cert.issue_date)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function OverviewTab({
  overviewData,
  loading,
  expandedHolder,
  setExpandedHolder,
  openEditModal,
  setActiveTab,
  handleOpenCertificateModal,
  formatDateFn,
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
          value={overviewData.beneficiaries.length}
        />
      </div>

      {/* Pie Chart & Holder List */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card-trust p-6" data-testid="ownership-chart">
          <div className="flex items-center gap-2 mb-6">
            <PieChart className="w-4 h-4 text-navy dark:text-gold" />
            <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Ownership Distribution</h2>
          </div>
          {overviewData.beneficiaries.length > 0 ? (
            <OwnershipPieChart beneficiaries={overviewData.beneficiaries} totalAuthorized={overviewData.total_authorized_units} />
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Users className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
              <p>No certificates issued yet</p>
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
          </div>

          {overviewData.beneficiaries.length === 0 ? (
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
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default OverviewTab;