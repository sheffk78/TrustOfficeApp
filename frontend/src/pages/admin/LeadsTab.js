import { Target, FileText, RefreshCw, Search, CheckSquare, Eye, ChevronLeft, ChevronRight, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import LeadTriageView from '@/components/LeadTriageView';
import { LEAD_STAGE_FILTERS, getLeadStageBadgeClass, getScoreColorClass } from './helpers';

export function LeadsTab({
  leads, leadsLoading, leadsTotal, leadsPage, leadsSearch, leadsStageFilter,
  leadsStageCounts, selectedLeadIds, showTriageView,
  onToggleTriage, onExportCsv, onRefresh,
  onStageFilterChange, onSearchChange, onSearchSubmit,
  onClearSelection, onBulkExport, onBulkStageChange,
  onSelectAll, onSelectLead, onViewLead,
  onTriageViewLead, onTriageFollowUp,
  onUpdateLeadStage, onPrevPage, onNextPage,
}) {
  return (
    <div className="card-trust">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-serif text-xl text-navy dark:text-white">Leads</h2>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={onToggleTriage}
            title={showTriageView ? 'Switch to table view' : 'Switch to triage view'}
          >
            <Target className="w-4 h-4 mr-2" />
            {showTriageView ? 'Table View' : 'Triage View'}
          </Button>
          <Button variant="outline" onClick={onExportCsv} title="Export all leads as CSV">
            <FileText className="w-4 h-4 mr-2" />
            Export
          </Button>
          <Button variant="outline" onClick={onRefresh}>
            <RefreshCw className={`w-4 h-4 ${leadsLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {showTriageView ? (
        <LeadTriageView
          onViewLead={onTriageViewLead}
          onFollowUp={onTriageFollowUp}
        />
      ) : (
        <div>
          <div className="flex flex-wrap gap-2 mb-4">
            {LEAD_STAGE_FILTERS.map((s) => (
              <button
                key={s.key}
                onClick={() => onStageFilterChange(s.key)}
                className={`px-3 py-1.5 text-sm transition-colors ${
                  leadsStageFilter === s.key
                    ? 'bg-navy text-white dark:bg-gold dark:text-navy'
                    : 'bg-navy/5 dark:bg-white/5 text-navy dark:text-white hover:bg-navy/10 dark:hover:bg-white/10'
                }`}
              >
                {s.label}
                {leadsStageCounts[s.key] !== undefined && (
                  <span className="ml-1.5 text-xs opacity-70">({leadsStageCounts[s.key]})</span>
                )}
              </button>
            ))}
          </div>

          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search leads by name or email..."
              value={leadsSearch}
              onChange={(e) => onSearchChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') onSearchSubmit(); }}
              className="w-full pl-10 pr-4 py-2 border border-navy/10 dark:border-white/10 bg-transparent text-navy dark:text-white text-sm focus:outline-none focus:border-gold"
            />
          </div>

          {leadsLoading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="w-8 h-8 animate-spin text-navy dark:text-white" />
            </div>
          ) : leads.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">No leads found</p>
          ) : (
            <div>
              {selectedLeadIds.size > 0 && (
                <div className="flex items-center justify-between p-3 mb-4 bg-navy/5 dark:bg-white/5 rounded border border-navy/10 dark:border-white/10">
                  <div className="flex items-center gap-3">
                    <CheckSquare className="w-5 h-5 text-navy dark:text-white" />
                    <span className="font-medium text-navy dark:text-white">
                      {selectedLeadIds.size} lead{selectedLeadIds.size !== 1 ? 's' : ''} selected
                    </span>
                    <Button variant="ghost" size="sm" onClick={onClearSelection}>
                      Clear
                    </Button>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={onBulkExport}>
                      <FileText className="w-4 h-4 mr-1" />
                      Export
                    </Button>
                    <Button variant="outline" size="sm" onClick={onBulkStageChange}>
                      <Activity className="w-4 h-4 mr-1" />
                      Change Stage
                    </Button>
                  </div>
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full min-w-[1000px]">
                  <thead>
                    <tr className="border-b border-navy/10 dark:border-white/10">
                      <th className="w-8 py-3 px-2">
                        <Checkbox
                          checked={leads.length > 0 && selectedLeadIds.size === leads.length}
                          onCheckedChange={onSelectAll}
                          aria-label="Select all leads"
                        />
                      </th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Name</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Email</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Stage</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Score</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Next Action</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Source</th>
                      <th className="text-left py-3 px-3 text-sm font-medium text-muted-foreground whitespace-nowrap">Created</th>
                      <th className="sticky right-0 py-3 px-3 text-left text-sm font-medium text-muted-foreground whitespace-nowrap bg-white dark:bg-slate-800 shadow-[-8px_0_8px_-6px_rgba(0,0,0,0.15)]">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leads.map((lead) => (
                      <tr key={lead.lead_id} className={`border-b border-navy/5 dark:border-white/5 hover:bg-navy/5 dark:hover:bg-white/5 ${selectedLeadIds.has(lead.lead_id) ? 'bg-navy/10 dark:bg-white/10' : ''}`}>
                        <td className="py-3 px-2">
                          <Checkbox
                            checked={selectedLeadIds.has(lead.lead_id)}
                            onCheckedChange={() => onSelectLead(lead.lead_id)}
                            aria-label={`Select ${lead.name || lead.email}`}
                          />
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5">
                            <p className="font-medium text-navy dark:text-white whitespace-nowrap">{lead.name || '—'}</p>
                            {lead.booked_call && (
                              <span title={`Discovery call scheduled${lead.booked_call_at ? ': ' + new Date(lead.booked_call_at).toLocaleString() : ''}`} className="inline-flex items-center gap-0.5 text-[10px] font-medium text-gold bg-gold/10 px-1.5 py-0.5 rounded-full whitespace-nowrap">
                                📞 Call
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-3 text-sm text-muted-foreground whitespace-nowrap max-w-[200px] truncate">{lead.email}</td>
                        <td className="py-3 px-3">
                          <Badge className={getLeadStageBadgeClass(lead.stage)}>
                            {lead.stage_label || lead.stage}
                          </Badge>
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-2">
                            <div className="w-14 h-2 bg-gray-200 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${getScoreColorClass(lead.score)}`}
                                style={{ width: `${lead.score}%` }}
                              />
                            </div>
                            <span className="text-xs text-muted-foreground">{lead.score}</span>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">
                          {lead.next_action || '—'}
                        </td>
                        <td className="py-3 px-3 text-sm text-muted-foreground whitespace-nowrap">
                          {lead.origin_source || lead.source || '—'}
                          {lead.source && (lead.origin_source !== lead.source) && (
                            <span className="ml-1 text-[10px] text-muted-foreground/60">({lead.source})</span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-sm text-muted-foreground whitespace-nowrap">
                          {lead.created_at ? new Date(lead.created_at).toLocaleDateString() : '—'}
                        </td>
                        <td className="sticky right-0 py-3 px-3 bg-white dark:bg-slate-800 shadow-[-8px_0_8px_-6px_rgba(0,0,0,0.15)]">
                          <div className="flex gap-1">
                            <button
                              onClick={() => onViewLead(lead.lead_id)}
                              className="p-1.5 text-muted-foreground hover:text-navy dark:hover:text-white transition-colors"
                              title="View details"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <select
                              value={lead.stage}
                              onChange={(e) => onUpdateLeadStage(lead.lead_id, e.target.value)}
                              className="text-xs border border-navy/20 dark:border-white/20 bg-transparent rounded px-1 py-0.5"
                              title="Change stage"
                            >
                              <option value="new">New</option>
                              <option value="engaged">Engaged</option>
                              <option value="warm">Warm</option>
                              <option value="converted">Converted</option>
                              <option value="lost">Lost</option>
                            </select>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {leadsTotal > 20 && (
                <div className="flex items-center justify-between mt-4">
                  <p className="text-sm text-muted-foreground">
                    Showing {((leadsPage - 1) * 20) + 1}-{Math.min(leadsPage * 20, leadsTotal)} of {leadsTotal}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => onPrevPage()}
                      disabled={leadsPage === 1}
                      className="p-2 text-muted-foreground hover:text-navy dark:hover:text-white disabled:opacity-30"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => onNextPage()}
                      disabled={leadsPage * 20 >= leadsTotal}
                      className="p-2 text-muted-foreground hover:text-navy dark:hover:text-white disabled:opacity-30"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
