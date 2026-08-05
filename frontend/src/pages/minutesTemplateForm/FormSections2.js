/**
 * Template-specific form sections for MinutesTemplateFormPage (part 2).
 * Batch 1 + Batch 2 template form sections.
 *
 * Each component receives the relevant state slice + setter as props.
 */
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Trash2 } from 'lucide-react';
import { formatCurrency, parseCurrencyInput } from './constants';

/* ── Investment Policy ────────────────────────────────────── */
export const InvestmentPolicyFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Investment Policy Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Policy Action</Label>
        <Select value={data.policy_type} onValueChange={(v) => setData({ ...data, policy_type: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="adopt">Adopt New Policy</SelectItem>
            <SelectItem value="amend">Amend Existing Policy</SelectItem>
            <SelectItem value="review">Review & Reaffirm</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Risk Tolerance</Label>
        <Select value={data.risk_tolerance} onValueChange={(v) => setData({ ...data, risk_tolerance: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="conservative">Conservative</SelectItem>
            <SelectItem value="moderate">Moderate</SelectItem>
            <SelectItem value="moderately_aggressive">Moderately Aggressive</SelectItem>
            <SelectItem value="aggressive">Aggressive</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Review Frequency</Label>
        <Select value={data.review_frequency} onValueChange={(v) => setData({ ...data, review_frequency: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="quarterly">Quarterly</SelectItem>
            <SelectItem value="semi-annually">Semi-Annually</SelectItem>
            <SelectItem value="annually">Annually</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>
  </div>
);

/* ── Loan Authorization ────────────────────────────────────── */
export const LoanAuthFields = ({ data, setData }) => {
  const isMaking = data.loan_direction === 'making';
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Loan Authorization Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Loan Direction</Label>
          <Select value={data.loan_direction} onValueChange={(v) => setData({ ...data, loan_direction: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="making">Trust Making Loan</SelectItem>
              <SelectItem value="receiving">Trust Receiving Loan</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">{isMaking ? 'Borrower Name' : 'Lender Name'}</Label>
          <Input
            value={isMaking ? data.borrower_name : data.lender_name}
            onChange={(e) => setData({ ...data, [isMaking ? 'borrower_name' : 'lender_name']: e.target.value })}
            className="mt-1 input-trust"
            placeholder="Name"
          />
        </div>
        <div>
          <Label className="label-trust">Loan Amount ($)</Label>
          <Input type="text" inputMode="numeric" value={formatCurrency(data.loan_amount)} onChange={(e) => setData({ ...data, loan_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$50,000" />
        </div>
        <div>
          <Label className="label-trust">Interest Rate</Label>
          <Input value={data.interest_rate} onChange={(e) => setData({ ...data, interest_rate: e.target.value })} className="mt-1 input-trust" placeholder="AFR or 5%" />
        </div>
        <div>
          <Label className="label-trust">Term (Months)</Label>
          <Input type="number" value={data.term_months} onChange={(e) => setData({ ...data, term_months: e.target.value })} className="mt-1 input-trust" placeholder="60" />
        </div>
        <div>
          <Label className="label-trust">Purpose</Label>
          <Input value={data.loan_purpose} onChange={(e) => setData({ ...data, loan_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Home purchase, business capital, etc." />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Collateral Description (if any)</Label>
          <Input value={data.collateral_description} onChange={(e) => setData({ ...data, collateral_description: e.target.value })} className="mt-1 input-trust" placeholder="Real property, securities, etc." />
        </div>
      </div>
    </div>
  );
};

/* ── Insurance Authorization ───────────────────────────────── */
export const InsuranceFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Insurance Authorization Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Insurance Type</Label>
        <Select value={data.insurance_type} onValueChange={(v) => setData({ ...data, insurance_type: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="property">Property & Casualty</SelectItem>
            <SelectItem value="liability">Liability</SelectItem>
            <SelectItem value="life">Life Insurance</SelectItem>
            <SelectItem value="health">Health Insurance</SelectItem>
            <SelectItem value="umbrella">Umbrella/Excess</SelectItem>
            <SelectItem value="professional">Professional Liability</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Action</Label>
        <Select value={data.policy_action} onValueChange={(v) => setData({ ...data, policy_action: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="obtain">Obtain New Policy</SelectItem>
            <SelectItem value="renew">Renew Existing</SelectItem>
            <SelectItem value="modify">Modify Coverage</SelectItem>
            <SelectItem value="cancel">Cancel Policy</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Insurance Company</Label>
        <Input value={data.insurer_name} onChange={(e) => setData({ ...data, insurer_name: e.target.value })} className="mt-1 input-trust" placeholder="Company name" />
      </div>
      <div>
        <Label className="label-trust">Coverage Amount ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.coverage_amount)} onChange={(e) => setData({ ...data, coverage_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$1,000,000" />
      </div>
      <div>
        <Label className="label-trust">Annual Premium ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.premium_amount)} onChange={(e) => setData({ ...data, premium_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$5,000" />
      </div>
      <div>
        <Label className="label-trust">Policy Number (if existing)</Label>
        <Input value={data.policy_number} onChange={(e) => setData({ ...data, policy_number: e.target.value })} className="mt-1 input-trust" placeholder="POL-123456" />
      </div>
      <div className="md:col-span-2">
        <Label className="label-trust">Coverage Description</Label>
        <Textarea value={data.coverage_description} onChange={(e) => setData({ ...data, coverage_description: e.target.value })} className="mt-1" rows={2} placeholder="Describe what is covered" />
      </div>
    </div>
  </div>
);

/* ── Annual Review ────────────────────────────────────────── */
export const AnnualReviewFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Annual Review Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Fiscal Year</Label>
        <Input value={data.fiscal_year} onChange={(e) => setData({ ...data, fiscal_year: e.target.value })} className="mt-1 input-trust" placeholder="2025" />
      </div>
      <div>
        <Label className="label-trust">Investment Return</Label>
        <Input value={data.investment_return} onChange={(e) => setData({ ...data, investment_return: e.target.value })} className="mt-1 input-trust" placeholder="7.5%" />
      </div>
      <div>
        <Label className="label-trust">Total Assets (Year End) ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.total_assets)} onChange={(e) => setData({ ...data, total_assets: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$1,000,000" />
      </div>
      <div>
        <Label className="label-trust">Total Income ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.total_income)} onChange={(e) => setData({ ...data, total_income: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$50,000" />
      </div>
      <div>
        <Label className="label-trust">Total Expenses ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.total_expenses)} onChange={(e) => setData({ ...data, total_expenses: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$10,000" />
      </div>
      <div>
        <Label className="label-trust">Total Distributions ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.total_distributions)} onChange={(e) => setData({ ...data, total_distributions: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$30,000" />
      </div>
    </div>
  </div>
);

/* ── Quarterly Review ─────────────────────────────────────── */
export const QuarterlyReviewFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Quarterly Review Details</h2>
    <div className="grid md:grid-cols-3 gap-4">
      <div>
        <Label className="label-trust">Quarter</Label>
        <Select value={data.quarter} onValueChange={(v) => setData({ ...data, quarter: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Q1">Q1 (Jan-Mar)</SelectItem>
            <SelectItem value="Q2">Q2 (Apr-Jun)</SelectItem>
            <SelectItem value="Q3">Q3 (Jul-Sep)</SelectItem>
            <SelectItem value="Q4">Q4 (Oct-Dec)</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Year</Label>
        <Input value={data.year} onChange={(e) => setData({ ...data, year: e.target.value })} className="mt-1 input-trust" placeholder="2026" />
      </div>
    </div>
    <div className="grid md:grid-cols-2 gap-4 mt-4">
      <div>
        <Label className="label-trust">Beginning Balance ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.beginning_balance)} onChange={(e) => setData({ ...data, beginning_balance: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$500,000" />
      </div>
      <div>
        <Label className="label-trust">Ending Balance ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.ending_balance)} onChange={(e) => setData({ ...data, ending_balance: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$510,000" />
      </div>
      <div>
        <Label className="label-trust">Income Received ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.income_received)} onChange={(e) => setData({ ...data, income_received: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$15,000" />
      </div>
      <div>
        <Label className="label-trust">Distributions Made ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.distributions_made)} onChange={(e) => setData({ ...data, distributions_made: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$5,000" />
      </div>
    </div>
  </div>
);

/* ── Trustee Compensation ──────────────────────────────────── */
export const TrusteeCompensationFields = ({ data, setData }) => {
  const showName = !data.all_trustees;
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Trustee Compensation Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2 flex items-center gap-3">
          <Checkbox checked={data.all_trustees} onCheckedChange={(c) => setData({ ...data, all_trustees: c })} id="all-trustees" />
          <Label htmlFor="all-trustees" className="cursor-pointer">Apply to all trustees</Label>
        </div>
        {showName && (
          <div>
            <Label className="label-trust">Trustee Name</Label>
            <Input value={data.trustee_name} onChange={(e) => setData({ ...data, trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith" />
          </div>
        )}
        <div>
          <Label className="label-trust">Compensation Type</Label>
          <Select value={data.compensation_type} onValueChange={(v) => setData({ ...data, compensation_type: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="annual">Annual Fee</SelectItem>
              <SelectItem value="hourly">Hourly Rate</SelectItem>
              <SelectItem value="per_meeting">Per Meeting</SelectItem>
              <SelectItem value="percentage">% of Assets</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">Amount ($)</Label>
          <Input type="text" inputMode="numeric" value={formatCurrency(data.compensation_amount)} onChange={(e) => setData({ ...data, compensation_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$5,000" />
        </div>
        <div>
          <Label className="label-trust">Effective Date</Label>
          <Input value={data.effective_date} onChange={(e) => setData({ ...data, effective_date: e.target.value })} className="mt-1 input-trust" placeholder="January 1, 2026" />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Compensation Basis/Justification</Label>
          <Textarea value={data.compensation_basis} onChange={(e) => setData({ ...data, compensation_basis: e.target.value })} className="mt-1" rows={2} placeholder="Based on comparable trustee fees in the region..." />
        </div>
      </div>
    </div>
  );
};

/* ── Trustee Resignation ──────────────────────────────────── */
export const TrusteeResignationFields = ({ data, setData, trusteesPresent }) => {
  const validTrustees = trusteesPresent.filter((t) => t.trim());
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Trustee Departure Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Departing Trustee Name</Label>
          <Select value={data.departing_trustee_name} onValueChange={(value) => setData({ ...data, departing_trustee_name: value })}>
            <SelectTrigger className="mt-1 input-trust" data-testid="resign-departing-trustee-select">
              <SelectValue placeholder="Select departing trustee..." />
            </SelectTrigger>
            <SelectContent>
              {validTrustees.length > 0 ? (
                validTrustees.map((trustee) => (
                  <SelectItem key={trustee} value={trustee}>{trustee}</SelectItem>
                ))
              ) : (
                <SelectItem value="__none__" disabled>No trustees available</SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">Departure Type</Label>
          <Select value={data.departure_type} onValueChange={(v) => setData({ ...data, departure_type: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="resignation">Resignation</SelectItem>
              <SelectItem value="removal">Removal</SelectItem>
              <SelectItem value="death">Death</SelectItem>
              <SelectItem value="incapacity">Incapacity</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">Effective Date</Label>
          <Input value={data.effective_date} onChange={(e) => setData({ ...data, effective_date: e.target.value })} className="mt-1 input-trust" placeholder="March 1, 2026" />
        </div>
        <div>
          <Label className="label-trust">Reason (optional)</Label>
          <Input value={data.departure_reason} onChange={(e) => setData({ ...data, departure_reason: e.target.value })} className="mt-1 input-trust" placeholder="Personal reasons, relocation, etc." />
        </div>
        <div className="md:col-span-2 flex items-center gap-3">
          <Checkbox checked={data.successor_appointed} onCheckedChange={(c) => setData({ ...data, successor_appointed: c })} id="successor-appointed" />
          <Label htmlFor="successor-appointed" className="cursor-pointer">Successor trustee being appointed</Label>
        </div>
        {data.successor_appointed && (
          <div className="md:col-span-2">
            <Label className="label-trust">Successor Name</Label>
            <Input value={data.successor_name} onChange={(e) => setData({ ...data, successor_name: e.target.value })} className="mt-1 input-trust" placeholder="Jane Doe" />
          </div>
        )}
      </div>
    </div>
  );
};

/* ── Beneficiary Request Denial ────────────────────────────── */
export const DenialFields = ({ data, setData }) => {
  const updateReason = (idx, value) => {
    const newReasons = [...data.denial_reasons];
    newReasons[idx] = value;
    setData({ ...data, denial_reasons: newReasons });
  };
  const addReason = () => setData({ ...data, denial_reasons: [...data.denial_reasons, ''] });
  const removeReason = (idx) => setData({ ...data, denial_reasons: data.denial_reasons.filter((_, i) => i !== idx) });

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Request Denial Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Beneficiary Name</Label>
          <Input value={data.beneficiary_name} onChange={(e) => setData({ ...data, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
        </div>
        <div>
          <Label className="label-trust">Request Type</Label>
          <Select value={data.request_type} onValueChange={(v) => setData({ ...data, request_type: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="distribution">Distribution Request</SelectItem>
              <SelectItem value="loan">Loan Request</SelectItem>
              <SelectItem value="early_distribution">Early Distribution</SelectItem>
              <SelectItem value="special_request">Special Request</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">Request Amount ($)</Label>
          <Input type="text" inputMode="numeric" value={formatCurrency(data.request_amount)} onChange={(e) => setData({ ...data, request_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$25,000" />
        </div>
        <div>
          <Label className="label-trust">Request Date</Label>
          <Input value={data.request_date} onChange={(e) => setData({ ...data, request_date: e.target.value })} className="mt-1 input-trust" placeholder="February 15, 2026" />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Request Purpose</Label>
          <Input value={data.request_purpose} onChange={(e) => setData({ ...data, request_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Vacation, luxury purchase, etc." />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Reasons for Denial</Label>
          <div className="space-y-2 mt-1">
            {data.denial_reasons.map((reason, idx) => (
              <div key={idx} className="flex gap-2">
                <Input value={reason} onChange={(e) => updateReason(idx, e.target.value)} className="input-trust" placeholder="Reason for denial" />
                {data.denial_reasons.length > 1 && (
                  <Button variant="ghost" size="icon" onClick={() => removeReason(idx)}>
                    <Trash2 className="w-4 h-4 text-red-500" />
                  </Button>
                )}
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={addReason}>
              <Plus className="w-4 h-4 mr-1" /> Add Reason
            </Button>
          </div>
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Alternative Offered (optional)</Label>
          <Textarea value={data.alternative_offered} onChange={(e) => setData({ ...data, alternative_offered: e.target.value })} className="mt-1" rows={2} placeholder="Smaller distribution, loan instead, etc." />
        </div>
      </div>
    </div>
  );
};

/* ── HEMS Distribution ─────────────────────────────────────── */
export const HemsFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">HEMS Distribution Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Beneficiary Name</Label>
        <Input value={data.beneficiary_name} onChange={(e) => setData({ ...data, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
      </div>
      <div>
        <Label className="label-trust">HEMS Category</Label>
        <Select value={data.hems_category} onValueChange={(v) => setData({ ...data, hems_category: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="health">Health (Medical)</SelectItem>
            <SelectItem value="education">Education</SelectItem>
            <SelectItem value="maintenance">Maintenance</SelectItem>
            <SelectItem value="support">Support</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Distribution Amount ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.distribution_amount)} onChange={(e) => setData({ ...data, distribution_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$10,000" />
      </div>
      <div className="flex items-center gap-3">
        <Checkbox checked={data.recurring} onCheckedChange={(c) => setData({ ...data, recurring: c })} id="recurring-hems" />
        <Label htmlFor="recurring-hems" className="cursor-pointer">Recurring Distribution</Label>
      </div>
      {data.recurring && (
        <div>
          <Label className="label-trust">Frequency</Label>
          <Select value={data.recurring_frequency} onValueChange={(v) => setData({ ...data, recurring_frequency: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="monthly">Monthly</SelectItem>
              <SelectItem value="quarterly">Quarterly</SelectItem>
              <SelectItem value="semi-annually">Semi-Annually</SelectItem>
              <SelectItem value="annually">Annually</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
      <div className="md:col-span-2">
        <Label className="label-trust">Specific Purpose</Label>
        <Textarea value={data.specific_purpose} onChange={(e) => setData({ ...data, specific_purpose: e.target.value })} className="mt-1" rows={2} placeholder="Describe the specific HEMS need" />
      </div>
    </div>
  </div>
);

/* ── Beneficiary Distribution Notice ──────────────────────── */
export const DistributionNoticeFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Distribution Notice Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Beneficiary Name</Label>
        <Input value={data.beneficiary_name} onChange={(e) => setData({ ...data, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
      </div>
      <div>
        <Label className="label-trust">Distribution Amount ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.distribution_amount)} onChange={(e) => setData({ ...data, distribution_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$15,000" />
      </div>
      <div>
        <Label className="label-trust">Distribution Date</Label>
        <Input value={data.distribution_date} onChange={(e) => setData({ ...data, distribution_date: e.target.value })} className="mt-1 input-trust" placeholder="February 15, 2026" />
      </div>
      <div>
        <Label className="label-trust">Trustee Name</Label>
        <Input value={data.trustee_name} onChange={(e) => setData({ ...data, trustee_name: e.target.value })} className="mt-1 input-trust" placeholder="Your name" />
      </div>
      <div className="md:col-span-2">
        <Label className="label-trust">Distribution Purpose</Label>
        <Textarea value={data.distribution_purpose} onChange={(e) => setData({ ...data, distribution_purpose: e.target.value })} className="mt-1" rows={2} placeholder="Education expenses for fall semester tuition" />
      </div>
    </div>
  </div>
);

/* ── Beneficiary Loan ─────────────────────────────────────── */
export const BeneficiaryLoanFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Beneficiary Loan Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div>
        <Label className="label-trust">Beneficiary Name</Label>
        <Input value={data.beneficiary_name} onChange={(e) => setData({ ...data, beneficiary_name: e.target.value })} className="mt-1 input-trust" placeholder="John Smith Jr." />
      </div>
      <div>
        <Label className="label-trust">Loan Amount ($)</Label>
        <Input type="text" inputMode="numeric" value={formatCurrency(data.loan_amount)} onChange={(e) => setData({ ...data, loan_amount: parseCurrencyInput(e.target.value) })} className="mt-1 input-trust" placeholder="$50,000" />
      </div>
      <div>
        <Label className="label-trust">Interest Rate</Label>
        <Input value={data.interest_rate} onChange={(e) => setData({ ...data, interest_rate: e.target.value })} className="mt-1 input-trust" placeholder="AFR or 5%" />
      </div>
      <div>
        <Label className="label-trust">Term (Months)</Label>
        <Input type="number" value={data.term_months} onChange={(e) => setData({ ...data, term_months: e.target.value })} className="mt-1 input-trust" placeholder="60" />
      </div>
      <div>
        <Label className="label-trust">Repayment Terms</Label>
        <Select value={data.repayment_terms} onValueChange={(v) => setData({ ...data, repayment_terms: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="monthly installments">Monthly Installments</SelectItem>
            <SelectItem value="quarterly installments">Quarterly Installments</SelectItem>
            <SelectItem value="annual installments">Annual Installments</SelectItem>
            <SelectItem value="balloon payment">Balloon at Maturity</SelectItem>
            <SelectItem value="interest only">Interest Only</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Purpose</Label>
        <Input value={data.loan_purpose} onChange={(e) => setData({ ...data, loan_purpose: e.target.value })} className="mt-1 input-trust" placeholder="Home purchase, education, etc." />
      </div>
      <div className="md:col-span-2">
        <Label className="label-trust">Collateral (if any)</Label>
        <Input value={data.collateral_description} onChange={(e) => setData({ ...data, collateral_description: e.target.value })} className="mt-1 input-trust" placeholder="Real property, vehicle, etc." />
      </div>
    </div>
  </div>
);