/**
 * CSV import dialog — multi-step (upload → map → review).
 *
 * The parent owns all import state (csvData, csvHeaders, csvMapping, importEntity,
 * importStep, importing, fileInputRef). This component renders the steps and
 * forwards file uploads and submit actions back to the parent.
 */
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Upload, Loader2 } from 'lucide-react';

export default function CsvImportDialog({
  open,
  onOpenChange,
  step,
  entities,
  importEntity,
  onImportEntityChange,
  csvData,
  csvHeaders,
  csvMapping,
  onCsvMappingChange,
  importing,
  fileInputRef,
  onFileUpload,
  onImport,
  onBack,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Bank Statement CSV</DialogTitle>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4 mt-2">
            <div>
              <Label className="label-trust">Entity *</Label>
              <Select value={importEntity} onValueChange={onImportEntityChange}>
                <SelectTrigger data-testid="import-entity-select"><SelectValue placeholder="Select entity" /></SelectTrigger>
                <SelectContent>
                  {entities.map((e) => <SelectItem key={e.entity_id} value={e.entity_id}>{e.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div
              className="border-2 border-dashed border-border p-8 text-center cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">Click to upload a CSV file</p>
              <p className="text-xs text-muted-foreground/60 mt-1">Common bank statement format (date, description, amount)</p>
              <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={onFileUpload} data-testid="csv-file-input" />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4 mt-2">
            <p className="text-sm text-muted-foreground">
              Map your CSV columns to TrustOffice fields. Found <strong>{csvData.length}</strong> rows.
            </p>
            <div className="grid grid-cols-1 gap-3">
              {['date', 'amount', 'description'].map((field) => (
                <div key={field}>
                  <Label className="capitalize label-trust">{field} Column *</Label>
                  <Select value={csvMapping[field]} onValueChange={(v) => onCsvMappingChange({ [field]: v })}>
                    <SelectTrigger data-testid={`map-${field}-select`}><SelectValue placeholder={`Select ${field} column`} /></SelectTrigger>
                    <SelectContent>
                      {csvHeaders.map((h) => <SelectItem key={h} value={h}>{h}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              ))}
            </div>

            {csvData.length > 0 && csvMapping.date && csvMapping.amount && (
              <div className="border border-border overflow-hidden">
                <p className="text-xs font-medium p-2 bg-muted/50">Preview (first 5 rows)</p>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="p-2 text-left">Date</th>
                      <th className="p-2 text-right">Amount</th>
                      <th className="p-2 text-left">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {csvData.slice(0, 5).map((row, i) => (
                      <tr key={i} className="border-b border-border/30">
                        <td className="p-2">{row[csvMapping.date]}</td>
                        <td className="p-2 text-right">{row[csvMapping.amount]}</td>
                        <td className="p-2 truncate max-w-[200px]">{row[csvMapping.description]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex gap-2">
              <Button variant="outline" onClick={onBack}>Back</Button>
              <Button className="flex-1 btn-primary" onClick={onImport} disabled={importing} data-testid="import-submit-btn">
                {importing ? (
                  <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Importing...</>
                ) : (
                  `Import ${csvData.length} Transactions`
                )}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Imported transactions default to &quot;Other&quot; classification. Use bulk-classify to tag them efficiently.
            </p>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}