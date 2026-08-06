import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Award, Plus, ArrowRightLeft, MoreVertical, FileText, Pencil, XCircle,
  AlertCircle, Settings,
} from 'lucide-react';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  STATUS_FILTER_OPTIONS,
  filterCertificatesByStatus,
  statusBadgeClass,
  formatDate,
} from './constants';

function CertRow({ cert, summary, handleViewPDF, openEditModal, setTransferForm, setShowTransferModal, setShowRevokeModal, transferForm }) {
  return (
    <div key={cert.certificate_id} className={`p-4 flex items-center justify-between ${cert.status !== 'active' ? 'opacity-60 bg-muted/30' : ''}`} data-testid={`cert-${cert.certificate_id}`}>
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 bg-navy/10 dark:bg-gold/10 flex items-center justify-center">
          <Award className={`w-6 h-6 ${cert.status === 'active' ? 'text-navy dark:text-gold' : 'text-muted-foreground'}`} />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-medium text-navy dark:text-foreground">{cert.holder_name}</p>
            {cert.holder_type && cert.holder_type !== 'individual' && (
              <span className="px-2 py-0.5 text-xs font-mono bg-navy/10 dark:bg-gold/10 text-navy dark:text-gold rounded">
                {cert.holder_type}
              </span>
            )}
            <span className={`px-2 py-0.5 text-xs font-mono ${statusBadgeClass(cert.status)}`}>
              {cert.status}
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            {cert.certificate_number} • {cert.units} {summary?.settings?.unit_label || 'Unit'}s ({cert.percentage.toFixed(2)}%)
          </p>
          <p className="text-xs text-muted-foreground font-mono">Issued {formatDate(cert.issue_date)}</p>
          {cert.email && (
            <p className="text-xs text-muted-foreground">{cert.email}</p>
          )}
          {cert.phone && (
            <p className="text-xs text-muted-foreground">{cert.phone}</p>
          )}
        </div>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" data-testid={`cert-menu-${cert.certificate_id}`}>
            <MoreVertical className="w-4 h-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => handleViewPDF(cert)}>
            <FileText className="w-4 h-4 mr-2" />
            View Certificate PDF
          </DropdownMenuItem>
          {cert.status === 'active' && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => openEditModal(cert)}>
                <Pencil className="w-4 h-4 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => { setTransferForm({ ...transferForm, from_certificate_id: cert.certificate_id, to_certificate_id: '', to_holder_name: '', to_holder_identifier: '' }); setShowTransferModal(true); }}>
                <ArrowRightLeft className="w-4 h-4 mr-2" />
                Transfer Units
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => setShowRevokeModal(cert)} className="text-error">
                <XCircle className="w-4 h-4 mr-2" />
                Revoke
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

// ========== CERTIFICATES TAB ==========
export function CertificatesTab({
  summary,
  loading,
  statusFilter,
  setStatusFilter,
  filteredCertificates,
  handleOpenTransferModal,
  resetCertificateForm,
  handleOpenCertificateModal,
  handleViewPDF,
  openEditModal,
  setTransferForm,
  setShowTransferModal,
  setShowRevokeModal,
  transferForm,
  setShowSettingsModal,
}) {
  return (
    <>
      {/* Actions Bar */}
      <div className="card-trust p-4 mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[150px]" data-testid="status-filter">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUS_FILTER_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {summary && (
              <div className="text-sm">
                <span className="text-muted-foreground">Available: </span>
                <span className="font-mono font-medium text-navy dark:text-gold">{summary.remaining_units} units</span>
                <span className="text-muted-foreground"> of {summary.settings?.total_authorized_units}</span>
              </div>
            )}
          </div>

          <div className="flex gap-2">
            <Button variant="outline" onClick={() => handleOpenTransferModal(summary?.certificates?.find(c => c.status === 'active'))} disabled={!summary?.certificates?.filter(c => c.status === 'active').length} data-testid="transfer-btn">
              <ArrowRightLeft className="w-4 h-4 mr-2" />
              Transfer
            </Button>
            <Button className="btn-primary" onClick={() => { resetCertificateForm(); handleOpenCertificateModal(); }} data-testid="issue-units-btn">
              <Plus className="w-4 h-4 mr-2" />
              Add Shares
            </Button>
          </div>
        </div>
      </div>

      {/* Fully Allocated Warning */}
      {summary && summary.remaining_units === 0 && (
        <div className="mb-4 p-4 border-2 border-gold/40 bg-gold/5 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-gold flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-mono text-xs font-medium text-navy mb-1">All {summary.settings?.total_authorized_units || 100} units are allocated</p>
            <p className="text-sm text-muted-foreground mb-2">To add another beneficiary, increase the authorized units or cancel an existing certificate.</p>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setShowSettingsModal(true)} className="font-mono text-xs">
                <Settings className="w-3.5 h-3.5 mr-1" /> Increase Authorized Units
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Certificates List */}
      <div className="card-trust overflow-hidden">
        <div className="p-4 border-b border-border flex items-center gap-2">
          <Award className="w-4 h-4 text-navy dark:text-gold" />
          <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Ownership Shares</h2>
          <span className="ml-auto text-xs text-muted-foreground">{filteredCertificates.length} records</span>
        </div>

        {loading ? (
          <div className="p-8 text-center">
            <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin mx-auto mb-4"></div>
            <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Loading...</p>
          </div>
        ) : filteredCertificates.length === 0 ? (
          <div className="p-8 text-center">
            <Award className="w-12 h-12 mx-auto mb-4 text-muted-foreground/30" />
            <p className="text-muted-foreground mb-4">No certificates found</p>
            <Button className="btn-primary" onClick={() => { resetCertificateForm(); handleOpenCertificateModal(); }}>
              <Plus className="w-4 h-4 mr-2" /> Add First Ownership Share
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredCertificates.map((cert) => (
              <CertRow
                key={cert.certificate_id}
                cert={cert}
                summary={summary}
                handleViewPDF={handleViewPDF}
                openEditModal={openEditModal}
                setTransferForm={setTransferForm}
                setShowTransferModal={setShowTransferModal}
                setShowRevokeModal={setShowRevokeModal}
                transferForm={transferForm}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default CertificatesTab;