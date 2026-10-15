import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import PageHeader from '@/components/PageHeader';
import { toast } from 'sonner';
import { showError } from '../utils/errors';
import { format, parseISO } from 'date-fns';
import { safeFormatDate } from '@/utils/safeDate';
import {
  FileText,
  Download,
  Trash2,
  RefreshCw,
  Users,
  Shield,
  AlertTriangle,
} from 'lucide-react';

export default function BeneficiaryReportPage() {
  const { selectedTrust } = useAuth();
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
    const [pendingDelete, setPendingDelete] = useState(null);
  
const [deletingId, setDeletingId] = useState(null);

  const loadReports = useCallback(async () => {
    if (!selectedTrust) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetchWithAuth(`/beneficiary-reports/${selectedTrust.trust_id}`);
      if (res.ok) {
        const data = await res.json();
        setReports(data.reports || data || []);
      } else {
        setReports([]);
      }
    } catch (error) {
      showError(toast, error, { operation: 'load_reports', page: 'BeneficiaryReports' });
    } finally {
      setLoading(false);
    }
  }, [selectedTrust]);

  useEffect(() => {
    loadReports();
  }, [loadReports]);

  const handleGenerate = async () => {
    if (!selectedTrust) return;
    setGenerating(true);
    try {
      const res = await fetchWithAuth(`/beneficiary-reports/${selectedTrust.trust_id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        toast.success('Beneficiary report generated successfully');
        await loadReports();
      } else {
        const data = await res.json().catch(() => ({}));
        showError(toast, new Error(data.detail || 'Failed to generate report'), {
          operation: 'generate_report',
          page: 'BeneficiaryReports',
        });
      }
    } catch (error) {
      showError(toast, error, { operation: 'generate_report', page: 'BeneficiaryReports' });
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = async (report) => {
    if (!selectedTrust) return;
    try {
      const res = await fetchWithAuth(
        `/beneficiary-reports/${selectedTrust.trust_id}/${report.report_id}/download`
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Download failed');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `beneficiary-report-${selectedTrust.trust_name || selectedTrust.trust_id}-${format(
        parseISO(report.generated_at),
        'yyyy-MM-dd'
      )}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      showError(toast, error, { operation: 'download_report', page: 'BeneficiaryReports' });
    }
  };

  const performDelete = async (report) => {
    setDeletingId(report.report_id);
    try {
      const res = await fetchWithAuth(`/beneficiary-reports/${report.report_id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        toast.success('Report deleted');
        setReports((prev) => prev.filter((r) => r.report_id !== report.report_id));
      } else {
        const data = await res.json().catch(() => ({}));
        showError(toast, new Error(data.detail || 'Failed to delete report'), {
          operation: 'delete_report',
          page: 'BeneficiaryReports',
        });
      }
    } catch (error) {
      showError(toast, error, { operation: 'delete_report', page: 'BeneficiaryReports' });
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
    <div className="main-layout" data-testid="beneficiary-report-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <PageHeader
            title="Beneficiary Reports"
            subtitle={`Generate and manage beneficiary summary reports for ${
              selectedTrust?.trust_name || 'your trust'
            }`}
            help={{
              items: [
                { text: 'Generate a PDF report summarizing all beneficiaries' },
                { text: 'Download previously generated reports' },
                { text: 'Delete old reports to keep your records tidy' },
                { text: 'Deleting a report is permanent and cannot be undone' },
              ],
              taPrompt: 'How do beneficiary reports work?',
            }}
            actions={
              <>
                <Button
                  onClick={loadReports}
                  variant="outline"
                  className="btn-secondary"
                  disabled={loading}
                  data-testid="refresh-reports-btn"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
                <Button
                  onClick={handleGenerate}
                  disabled={!selectedTrust || generating}
                  className="btn-primary"
                  data-testid="generate-report-btn"
                >
                  {generating ? (
                    <>
                      <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                      Generating...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 mr-2" />
                      Generate Report
                    </>
                  )}
                </Button>
              </>
            }
          />

          {!selectedTrust ? (
            <div className="card-trust corner-mark p-8 text-center text-muted-foreground">
              <Shield className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Select a trust to manage beneficiary reports.</p>
            </div>
          ) : loading ? (
            <div className="card-trust corner-mark">
              <div className="skeleton h-64 w-full"></div>
            </div>
          ) : reports.length === 0 ? (
            <div className="card-trust corner-mark p-8 text-center text-muted-foreground">
              <Users className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>No reports generated yet. Click &apos;Generate Report&apos; to create your first beneficiary report.</p>
            </div>
          ) : (
            <div className="card-trust corner-mark">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-serif text-lg text-navy">Generated Reports</h3>
                <Badge variant="outline" className="font-mono">
                  {reports.length}
                </Badge>
              </div>
              <div className="space-y-3">
                {reports.map((report) => (
                  <div
                    key={report.report_id}
                    className="flex items-center justify-between p-4 border border-navy/10"
                    data-testid={`report-${report.report_id}`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-navy/10 flex items-center justify-center">
                        <FileText className="w-5 h-5 text-navy" />
                      </div>
                      <div>
                        <p className="font-medium text-sm text-navy">
                          {report.trust_name || selectedTrust?.trust_name || 'Trust Report'}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Generated{' '}
                          <span className="font-mono">
                            {safeFormatDate(report.generated_at, 'MMM d, yyyy h:mm a')}
                          </span>
                          {report.beneficiary_count != null && (
                            <>
                              {' '}
                              &middot;{' '}
                              <span className="font-mono">{report.beneficiary_count}</span>{' '}
                              beneficiar{report.beneficiary_count === 1 ? 'y' : 'ies'}
                            </>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <Button
                        onClick={() => handleDownload(report)}
                        size="sm"
                        variant="outline"
                        className="btn-secondary"
                        data-testid={`download-report-${report.report_id}`}
                      >
                        <Download className="w-3 h-3 mr-1" />
                        Download
                      </Button>
                      <Button
                        onClick={() => setPendingDelete(report)}
                        size="sm"
                        variant="outline"
                        className="btn-secondary text-error border-error/20 hover:bg-error/10"
                        disabled={deletingId === report.report_id}
                        data-testid={`delete-report-${report.report_id}`}
                      >
                        {deletingId === report.report_id ? (
                          <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                        ) : (
                          <Trash2 className="w-3 h-3 mr-1" />
                        )}
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
    {/* Delete confirmation (AlertDialog per standard — no confirm()) */}
    <AlertDialog
      open={!!pendingDelete}
      onOpenChange={(open) => { if (!open) setPendingDelete(null); }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Report</AlertDialogTitle>
          <AlertDialogDescription>
            Delete this report? This action cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="report-delete-cancel">Cancel</AlertDialogCancel>
          <AlertDialogAction
            data-testid="report-delete-confirm"
            className="bg-error text-error-foreground hover:bg-error/90"
            onClick={(e) => {
              e.preventDefault();
              const target = pendingDelete;
              setPendingDelete(null);
              if (target) performDelete(target);
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    </>
  );
}
