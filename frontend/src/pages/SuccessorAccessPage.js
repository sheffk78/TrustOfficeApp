import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertCircle, BookOpen, Building2, Calendar, CheckCircle2, ClipboardList,
  FileText, KeyRound, Landmark, Shield, Upload, Users,
} from 'lucide-react';
import { API } from '@/utils/api';
import { formatEIN } from '@/utils/formatters';

const fmtDate = (value) => {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('en-US', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
};

const display = (value) => {
  if (value === null || value === undefined || value === '') return 'Not specified';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
};

const MONO_TABLE_KEYS = new Set(['units', 'last_four', 'date', 'due_date']);

const InfoRow = ({ label, value, valueMono = false }) => (
  <div className="flex flex-col gap-1 border-b border-navy/10 py-3 sm:flex-row sm:gap-4">
    <div className="w-full flex-shrink-0 text-sm text-muted-foreground sm:w-44">{label}</div>
    <div className={`whitespace-pre-wrap break-words text-sm font-medium text-navy${valueMono ? ' font-mono' : ''}`}>{display(value)}</div>
  </div>
);

const SectionTitle = ({ icon: Icon, title }) => (
  <div className="mb-4 flex items-center gap-2">
    <Icon className="h-5 w-5 text-gold" aria-hidden="true" />
    <h2 className="text-lg font-bold text-navy">{title}</h2>
  </div>
);

const EmptyState = ({ children = 'No information was provided for this section.' }) => (
  <p className="text-sm italic text-muted-foreground/60">{children}</p>
);

const DataTable = ({ columns, rows, emptyText }) => {
  if (!rows.length) return <EmptyState>{emptyText}</EmptyState>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] border-collapse">
        <thead>
          <tr className="border-b-2 border-navy/20">
            {columns.map(({ label }) => (
              <th key={label} className="px-2 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={row.id || index} className="border-b border-navy/10 last:border-0">
              {columns.map(({ key, format }) => (
                <td key={key} className={`px-2 py-3 text-sm text-foreground${MONO_TABLE_KEYS.has(key) ? ' font-mono' : ''}`}>{display(format ? format(row[key], row) : row[key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

const SuccessorAccessPage = () => {
  const { token } = useParams();
  const [packet, setPacket] = useState(null);
  const [status, setStatus] = useState('loading');
  const [errorStatus, setErrorStatus] = useState(null);

  // Jeff 2026-10-16 — no token in the URL: the successor lands on the entry form.
  // Access code (default) or death-certificate claim, per the method the trustee chose.
  const [mode, setMode] = useState(token ? 'packet' : 'entry'); // 'entry' | 'packet' | 'claim'
  const [code, setCode] = useState('');
  const [codeError, setCodeError] = useState('');
  const [claimBusy, setClaimBusy] = useState(false);
  const [claimDone, setClaimDone] = useState(false);
  const [claimError, setClaimError] = useState('');
  const [claimForm, setClaimForm] = useState({
    trust_token: token || '',
    claimant_name: '',
    claimant_email: '',
    claimant_phone: '',
    notes: '',
  });
  const [claimFile, setClaimFile] = useState(null);

  const loadPacketWithCode = async (enteredCode) => {
    setClaimBusy(true);
    setCodeError('');
    try {
      const response = await fetch(`${API}/successor-access/claim-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: enteredCode }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setCodeError(data.detail || 'That access code isn\'t valid.');
        return;
      }
      const data = await response.json();
      setPacket(data);
      setStatus('success');
      setMode('packet');
    } catch {
      setCodeError('We couldn\'t reach the server. Please try again in a moment.');
    } finally {
      setClaimBusy(false);
    }
  };

  const submitClaim = async (event) => {
    event.preventDefault();
    if (!claimFile) {
      setClaimError('Attach the death certificate (PDF or photo) to submit.');
      return;
    }
    setClaimBusy(true);
    setClaimError('');
    try {
      const form = new FormData();
      form.append('file', claimFile);
      Object.entries(claimForm).forEach(([key, value]) => form.append(key, value));
      const response = await fetch(`${API}/successor-access/claim-verification`, {
        method: 'POST',
        body: form,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setClaimError(data.detail || 'We couldn\'t submit that. Please check the form and try again.');
        return;
      }
      setClaimDone(true);
    } catch {
      setClaimError('We couldn\'t reach the server. Please try again in a moment.');
    } finally {
      setClaimBusy(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadPacket = async () => {
      try {
        const response = await fetch(`${API}/successor-access/${encodeURIComponent(token || '')}`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
          if (!cancelled) {
            setErrorStatus(response.status);
            setStatus('error');
          }
          return;
        }
        const data = await response.json();
        if (!cancelled) {
          setPacket(data);
          setStatus('success');
        }
      } catch {
        if (!cancelled) {
          setErrorStatus('network');
          setStatus('error');
        }
      }
    };
    loadPacket();
    return () => { cancelled = true; };
  }, [token]);

  // ------- Entry form (no token in URL): access code or death-certificate claim -------
  if (mode === 'entry' || mode === 'claim') {
    if (claimDone) {
      return (
        <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-navy">
          <div className="w-full max-w-lg card-trust corner-mark text-center">
            <CheckCircle2 className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
            <h1 className="mb-3 text-2xl font-bold">Request received</h1>
            <p className="text-sm leading-6 text-muted-foreground">
              Thank you. Our team reviews every request personally — you&apos;ll hear from us by email
              once it&apos;s approved. If we need anything else, we&apos;ll contact you at
              {' '}{claimForm.claimant_email || 'the email you provided'}.
            </p>
          </div>
        </div>
      );
    }
    return (
      <div className="min-h-screen bg-subtle-bg px-4 py-10 text-navy sm:px-6 sm:py-16">
        <main className="mx-auto max-w-xl">
          <header className="mb-8 text-center">
            <div className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-gold">TrustOffice</div>
            <h1 className="mt-3 font-serif font-semibold tracking-tight text-navy text-3xl">
              {mode === 'entry' ? 'Successor Access' : 'Request Access'}
            </h1>
            {mode === 'entry' ? (
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                Enter the access code the trustee shared with you to open the successor packet.
              </p>
            ) : (
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted-foreground">
                Submit your request with the death certificate. Our team reviews each request
                personally and emails you once it&apos;s approved.
              </p>
            )}
          </header>

          {mode === 'entry' ? (
            <form
              className="card-trust corner-mark p-6 sm:p-8"
              onSubmit={(event) => { event.preventDefault(); loadPacketWithCode(code); }}
            >
              <label htmlFor="successor-code" className="mb-2 block text-sm font-medium text-navy">Access code</label>
              <input
                id="successor-code"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                placeholder="XXXX-XXXX-XXXX-XXXX"
                autoComplete="off"
                autoFocus
                className="w-full rounded border border-navy/30 bg-white px-4 py-3 text-center font-mono text-lg tracking-[0.25em] text-navy outline-none focus:border-gold"
              />
              {codeError && (
                <p className="mt-3 border border-warning/30 bg-warning/5 p-3 text-sm text-warning" role="alert">{codeError}</p>
              )}
              <button
                type="submit"
                disabled={claimBusy || !code.trim()}
                className="mt-5 w-full rounded bg-navy px-4 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {claimBusy ? 'Opening…' : 'Open the packet'}
              </button>
              <button
                type="button"
                className="mt-5 w-full text-center text-xs text-muted-foreground underline decoration-navy/20 underline-offset-4 hover:text-navy"
                onClick={() => setMode('claim')}
              >
                No access code? Request access with a death certificate instead →
              </button>
            </form>
          ) : (
            <form className="card-trust corner-mark p-6 sm:p-8" onSubmit={submitClaim}>
              <div className="mb-4 space-y-3">
                <input
                  required
                  value={claimForm.claimant_name}
                  onChange={(event) => setClaimForm({ ...claimForm, claimant_name: event.target.value })}
                  placeholder="Your full name"
                  className="w-full rounded border border-navy/30 bg-white px-4 py-2.5 text-sm text-navy outline-none focus:border-gold"
                />
                <input
                  required
                  type="email"
                  value={claimForm.claimant_email}
                  onChange={(event) => setClaimForm({ ...claimForm, claimant_email: event.target.value })}
                  placeholder="Your email"
                  className="w-full rounded border border-navy/30 bg-white px-4 py-2.5 text-sm text-navy outline-none focus:border-gold"
                />
                <input
                  value={claimForm.claimant_phone}
                  onChange={(event) => setClaimForm({ ...claimForm, claimant_phone: event.target.value })}
                  placeholder="Your phone (optional)"
                  className="w-full rounded border border-navy/30 bg-white px-4 py-2.5 text-sm text-navy outline-none focus:border-gold"
                />
              </div>
              <label className="mb-2 block text-sm font-medium text-navy">Death certificate (PDF or photo)</label>
              <label
                htmlFor="successor-claim-file"
                className="flex cursor-pointer items-center justify-center gap-2 rounded border border-dashed border-navy/30 bg-white px-4 py-6 text-sm text-muted-foreground hover:border-gold"
              >
                <Upload className="h-4 w-4 text-gold" aria-hidden="true" />
                {claimFile ? claimFile.name : 'Choose a file — PDF, JPG, or PNG (max 10 MB)'}
              </label>
              <input
                id="successor-claim-file"
                type="file"
                accept="application/pdf,image/*"
                className="sr-only"
                onChange={(event) => setClaimFile(event.target.files?.[0] || null)}
              />
              <textarea
                value={claimForm.notes}
                onChange={(event) => setClaimForm({ ...claimForm, notes: event.target.value })}
                placeholder="Anything our review team should know (optional)"
                rows={3}
                className="mt-3 w-full rounded border border-navy/30 bg-white px-4 py-2.5 text-sm text-navy outline-none focus:border-gold"
              />
              {claimError && (
                <p className="mt-3 border border-warning/30 bg-warning/5 p-3 text-sm text-warning" role="alert">{claimError}</p>
              )}
              <button
                type="submit"
                disabled={claimBusy}
                className="mt-5 w-full rounded bg-navy px-4 py-3 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {claimBusy ? 'Submitting…' : 'Submit request'}
              </button>
              <p className="mt-4 text-center text-xs leading-5 text-muted-foreground">
                Nothing about the trust is shown until your request is approved.
              </p>
            </form>
          )}

          <p className="mx-auto mt-8 max-w-md text-center text-xs leading-5 text-muted-foreground/70">
            This is operational information, not legal advice. Please consult qualified legal and tax
            professionals about your responsibilities as successor trustee.
          </p>
        </main>
      </div>
    );
  }

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-subtle-bg px-6 py-16 text-navy">
        <div className="mx-auto max-w-3xl animate-pulse space-y-6">
          <div className="h-8 w-2/3 rounded bg-muted" />
          <div className="h-4 w-1/2 rounded bg-muted" />
          <div className="h-52 bg-white border border-navy/20" />
          <div className="h-52 bg-white border border-navy/20" />
        </div>
      </div>
    );
  }

  if (status === 'error') {
    const invalidLink = errorStatus === 404 || errorStatus === 410;
    return (
      <div className="flex min-h-screen items-center justify-center bg-subtle-bg px-6 py-12 text-navy">
        <div className="w-full max-w-lg card-trust corner-mark text-center">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-gold" aria-hidden="true" />
          <h1 className="mb-3 text-2xl font-bold">{invalidLink ? 'This link is no longer valid' : 'We could not load this packet'}</h1>
          <p className="text-sm leading-6 text-muted-foreground">
            {invalidLink
              ? 'It may have expired or already been used. If you need access, ask the current trustee to send you a new link.'
              : 'Please try again in a moment. If the problem continues, ask the current trustee to send you a new link.'}
          </p>
        </div>
      </div>
    );
  }

  const trust = packet.trust || {};
  const entities = Array.isArray(packet.entities) ? packet.entities : [];
  const beneficiaries = Array.isArray(packet.beneficiaries) ? packet.beneficiaries : [];
  const bankAccounts = Array.isArray(packet.bank_accounts) ? packet.bank_accounts : [];
  const vaultDocuments = Array.isArray(packet.vault_documents) ? packet.vault_documents : [];
  const governanceTasks = Array.isArray(packet.governance_tasks) ? packet.governance_tasks : [];
  const taxCalendar = Array.isArray(packet.tax_calendar) ? packet.tax_calendar : [];
  const trustName = packet.trust_name || trust.name || 'Trust packet';

  return (
    <div className="min-h-screen bg-subtle-bg px-4 py-8 text-navy sm:px-6 sm:py-12">
      <main className="mx-auto max-w-4xl">
        <header className="mb-8 border-b border-navy/20 pb-8">
          <div className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-gold">TrustOffice</div>
          <h1 className="font-serif font-semibold tracking-tight text-navy text-3xl sm:text-4xl">{trustName}</h1>
          <p className="mt-2 text-lg text-muted-foreground">Successor information for {packet.successor_name || 'you'}</p>
          <div className="mt-6 flex items-start gap-3 rounded border border-gold/30 bg-gold/5 p-4 text-sm leading-6 text-foreground">
            <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-gold" aria-hidden="true" />
            <p>You don&apos;t need to do anything right now. This packet is here so you have the information you may need if you ever step into the successor trustee role.</p>
          </div>
        </header>

        <div className="space-y-5">
          <section className="card-trust corner-mark sm:p-6">
            <SectionTitle icon={FileText} title="Trust Details" />
            <InfoRow label="Trust name" value={trust.name || packet.trust_name} />
            <InfoRow label="Trust type" value={trust.trust_type} />
            <InfoRow label="Formation date" value={fmtDate(trust.start_date || trust.formation_date)} valueMono />
            <InfoRow label="Jurisdiction" value={trust.jurisdiction || trust.state_code} />
            <InfoRow label="Current trustee" value={packet.trustee_name || trust.trustees} valueMono />
            <InfoRow label="Description" value={trust.description} />
          </section>

          <section className="card-trust corner-mark sm:p-6">
            <SectionTitle icon={Building2} title="Entities" />
            {entities.length ? <div className="space-y-3">{entities.map((entity, index) => <div key={entity.id || index} className="rounded bg-muted/50 p-4"><div className="font-semibold text-navy">{entity.name || entity.legal_name || 'Entity'}</div><div className="mt-1 text-sm text-muted-foreground">{[entity.entity_type && `Type: ${entity.entity_type}`, entity.ein && `EIN: ${formatEIN(entity.ein)}`, entity.governing_law && `Governing law: ${entity.governing_law}`].filter(Boolean).join(' · ') || 'No additional details provided'}</div></div>)}</div> : <EmptyState />}
          </section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={Users} title="Beneficiaries" /><DataTable columns={[{ label: 'Name', key: 'holder_name' }, { label: 'Email', key: 'email' }, { label: 'Phone', key: 'phone' }, { label: 'Share', key: 'units' }]} rows={beneficiaries} emptyText="No beneficiary records were provided." /></section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={Landmark} title="Bank Accounts" /><DataTable columns={[{ label: 'Account', key: 'account', format: (_, row) => row.nickname || row.name }, { label: 'Institution', key: 'institution_name', format: (_, row) => row.institution_name }, { label: 'Type', key: 'account_type', format: (_, row) => row.account_type || row.type }, { label: 'Last four', key: 'last_four', format: (_, row) => row.last_four || row.last4 ? `•••• ${row.last_four || row.last4}` : '' }]} rows={bankAccounts} emptyText="No bank account records were provided." /></section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={ClipboardList} title="Vault Documents" /><DataTable columns={[{ label: 'Document', key: 'name', format: (_, row) => row.name || row.title || row.filename }, { label: 'Category', key: 'category', format: (_, row) => row.category || row.document_type }, { label: 'Added', key: 'date', format: (_, row) => fmtDate(row.uploaded_at || row.date || row.created_at) }]} rows={vaultDocuments} emptyText="No vault documents were provided." /></section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={Shield} title="Governance Tasks" /><DataTable columns={[{ label: 'Task', key: 'title', format: (_, row) => row.title || row.task_type }, { label: 'Due', key: 'due_date', format: fmtDate }]} rows={governanceTasks} emptyText="No governance tasks were provided." /></section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={Calendar} title="Tax Calendar" /><DataTable columns={[{ label: 'Deadline', key: 'deadline', format: (_, row) => row.deadline_type || row.title }, { label: 'Due', key: 'due_date', format: fmtDate }]} rows={taxCalendar} emptyText="No tax calendar entries were provided." /></section>

          <section className="card-trust corner-mark sm:p-6"><SectionTitle icon={BookOpen} title="Successor Instructions" /><div className="whitespace-pre-wrap text-sm leading-7 text-foreground">{packet.successor_instructions || <EmptyState>No successor instructions were provided.</EmptyState>}</div></section>
        </div>

        <footer className="mt-8 border-t border-navy/20 pt-6 text-center text-xs leading-5 text-muted-foreground/60">This is operational information, not legal advice. Please consult qualified legal and tax professionals for guidance about your responsibilities.</footer>
      </main>
    </div>
  );
};

export default SuccessorAccessPage;
