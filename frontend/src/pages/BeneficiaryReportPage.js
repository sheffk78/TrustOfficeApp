import { useState, useEffect, useCallback } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import PageHelpButton from '@/components/PageHelpButton';
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

  const handleDelete = async (report) => {
    if (!window.confirm('Are you sure you want to delete this report? This action cannot be undone.')) {
      return;
    }
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
    <div className="main-layout" data-testid="beneficiary-report-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Beneficiary Reports</h1>
              <p className="page-subtitle">
                Generate and manage beneficiary summary reports for{' '}
                {selectedTrust?.trust_name || 'your trust'}
              </p>
            </div>
            <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
              <PageHelpButton
                items={[
                  { text: 'Generate a PDF report summarizing all beneficiaries' },
                  { text: 'Download previously generated reports' },
                  { text: 'Delete old reports to keep your records tidy' },
                ]}
                taPrompt="How do I generate a beneficiary report for my trust?"
              />
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
            </div>
          </div>

          {!selectedTrust ? (
            <div className="card-trust p-8 text-center text-muted-foreground">
              <Shield className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>Select a trust to manage beneficiary reports.</p>
            </div>
          ) : loading ? (
            <div className="card-trust">
              <div className="skeleton h-64 w-full"></div>
            </div>
          ) : reports.length === 0 ? (
            <div className="card-trust p-8 text-center text-muted-foreground">
              <Users className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>No reports generated yet. Click &apos;Generate Report&apos; to create your first beneficiary report.</p>
            </div>
          ) : (
            <div className="card-trust">
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
                          Generated {safeFormatDate(report.generated_at, 'MMM d, yyyy h:mm a')}
                          {report.beneficiary_count != null && (
                            <> &middot; {report.beneficiary_count} beneficiar{report.beneficiary_count === 1 ? 'y' : 'ies'}</>
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
                        onClick={() => handleDelete(report)}
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
  );
}
