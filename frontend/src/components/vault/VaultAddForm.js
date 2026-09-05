import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Upload, Link2, File, X, CloudUpload } from 'lucide-react';
import {
  ACCEPTED_TYPES,
  STORAGE_PROVIDERS,
} from './vaultConstants';

/**
 * The Add Document form for the Vault page.
 * Renders either an Upload File or Link External tab depending on addMode.
 */
export default function VaultAddForm({
  addMode, setAddMode,
  form, setForm,
  uploadFile, handleFileSelect, clearUploadFile,
  handleUpload, addDocument,
  uploading, uploadProgress,
  uploadError,
  resetForm,
  fileInputRef,
  categories,
}) {
  const isUpload = addMode === 'upload';
  const submitHandler = isUpload ? handleUpload : addDocument;
  const submitDisabled = isUpload ? uploading || !uploadFile : !form.title;

  const tabClass = (active) =>
    `flex items-center gap-2 px-5 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
      active
        ? 'border-navy text-navy'
        : 'border-transparent text-muted-foreground hover:text-foreground'
    }`;

  return (
    <Card className="mb-6 border-border">
      <CardContent className="p-4">
        {/* Mode Toggle */}
        <div className="flex border-b border-border mb-4">
          <button onClick={() => setAddMode('upload')} className={tabClass(addMode === 'upload')}>
            <Upload className="w-4 h-4" /> Upload File
          </button>
          <button onClick={() => setAddMode('link')} className={tabClass(addMode === 'link')}>
            <Link2 className="w-4 h-4" /> Link External
          </button>
        </div>

        <h3 className="font-semibold text-navy mb-3">
          {isUpload ? 'Upload a Document' : 'Add Document Reference'}
        </h3>

        {/* Upload Drop Zone */}
        {isUpload && (
          <div className="mb-4">
            {!uploadFile ? (
              <label
                htmlFor="vault-file-upload"
                className="flex flex-col items-center justify-center border-2 border-dashed border-navy/20 rounded p-8 cursor-pointer hover:border-navy hover:bg-subtle-bg transition-colors"
              >
                <CloudUpload className="w-10 h-10 text-muted-foreground/40 mb-2" />
                <p className="text-sm font-medium text-foreground">Click to upload or drag and drop</p>
                <p className="text-xs text-muted-foreground mt-1">PDF, images, Word, Excel — up to 50MB (PDFs auto-compressed)</p>
                <input
                  id="vault-file-upload"
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_TYPES}
                  className="hidden"
                  onChange={handleFileSelect}
                />
              </label>
            ) : (
              <div className="flex items-center gap-3 bg-subtle-bg border border-navy/10 rounded p-3">
                <File className="w-8 h-8 text-navy" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{uploadFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(uploadFile.size / 1024).toFixed(1)} KB
                    {uploadFile.size > 1024 * 1024 && ` (${(uploadFile.size / (1024 * 1024)).toFixed(1)} MB)`}
                  </p>
                </div>
                <button onClick={clearUploadFile} className="text-muted-foreground hover:text-rust">
                  <X className="w-5 h-5" />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Common Fields */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
          <Input placeholder="Document title *" value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
          <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} className="input-trust text-sm">
            {Object.entries(categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <Input type="date" placeholder="Document date" value={form.date} onChange={e => setForm({ ...form, date: e.target.value })} />
          <Input placeholder="Tags (comma-separated)" value={form.tags} onChange={e => setForm({ ...form, tags: e.target.value })} />
        </div>

        {/* Link-specific fields */}
        {addMode === 'link' && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
              <select value={form.storage_provider} onChange={e => setForm({ ...form, storage_provider: e.target.value })} className="input-trust text-sm">
                {STORAGE_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
              <Input placeholder="File name" value={form.file_name} onChange={e => setForm({ ...form, file_name: e.target.value })} />
            </div>
            <div className="mb-3">
              <Input placeholder="Storage URL or path (paste Google Drive link, Dropbox link, etc.)" value={form.storage_url} onChange={e => setForm({ ...form, storage_url: e.target.value })} />
            </div>
          </>
        )}

        <textarea placeholder="Description..." value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="input-trust w-full text-sm mb-3" rows={2} />
        {/* Expiration / Renewal */}
        <div className="mb-3">
          <label className="text-sm font-medium text-foreground block mb-1.5">Expiration / Renewal Date (optional)</label>
          <p className="text-xs text-muted-foreground mb-2">
            For documents that have an expiration or renewal date, such as insurance policies, certifications, or licenses. Trust instruments and most legal documents do not expire, so you can skip this.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Input type="date" placeholder="Expires on" value={form.expiration_date} onChange={e => setForm({ ...form, expiration_date: e.target.value })} />
            <div className="flex items-center gap-2">
              <input type="checkbox" checked={form.needs_renewal} onChange={e => setForm({ ...form, needs_renewal: e.target.checked })} id="renew" />
              <label htmlFor="renew" className="text-sm text-muted-foreground">Remind me to renew before this date</label>
            </div>
          </div>
          {form.needs_renewal && form.expiration_date && (
            <p className="text-xs text-success bg-success/10 rounded px-2 py-1.5 mb-3">
              You will receive a reminder email 30 days before this document expires.
            </p>
          )}
        </div>

        {/* Upload progress */}
        {uploadProgress && (
          <p className="text-sm text-warning mb-2">{uploadProgress}</p>
        )}

        {/* Persistent upload error — inline, stays visible until user fixes it or picks a new file */}
        {uploadError && (
          <div
            className="mb-3 p-3 rounded border border-rust/30 bg-rust/5 flex items-start gap-2"
            role="alert"
            aria-live="assertive"
          >
            <X className="w-4 h-4 text-rust flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="text-sm">
              <p className="font-medium text-rust">Upload failed</p>
              <p className="text-foreground/90 mt-0.5">{uploadError}</p>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Button className="btn-primary" onClick={submitHandler} disabled={submitDisabled}>
            {isUpload ? (
              <>
                <Upload className="w-4 h-4 mr-2" />
                {uploading ? 'Uploading...' : 'Upload to Vault'}
              </>
            ) : (
              'Save to Vault'
            )}
          </Button>
          <Button variant="outline" onClick={resetForm} className="btn-secondary">Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}
