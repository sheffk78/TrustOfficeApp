/**
 * Template-specific form sections for MinutesTemplateFormPage (part 1).
 * Each component receives the relevant state slice + setter as props,
 * preserving the exact original behaviour.
 *
 * Sections in this file:
 *  - DistributionFields
 *  - PropertyFields
 *  - DispositionFields
 *  - TrusteeAppointmentFields
 *  - BeneficiaryDesignationFields
 *  - BankAccountFields
 *  - SitusFields
 *  - BenevolenceFields
 */
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Trash2 } from 'lucide-react';
import { formatCurrency, parseCurrencyInput, ASSET_CATEGORIES, currencyInputClass } from './constants';

const removeIconBtn = 'h-10 w-10 shrink-0 text-muted-foreground hover:text-red-600 hover:bg-red-50';

/* ── Distribution to Beneficiaries ────────────────────────── */
export const DistributionFields = ({ data, setData, onAddItem, onRemoveItem, onItemChange }) => {
  const { distribution_total, distribution_date, distribution_characterization, distribution_items } = data;
  const canRemoveItem = distribution_items.length > 1;

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Distribution Details</h2>
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div>
          <Label className="label-trust">Total Distribution Amount ($)</Label>
          <Input
            type="text"
            inputMode="numeric"
            value={formatCurrency(distribution_total)}
            onChange={(e) => setData({ ...data, distribution_total: parseCurrencyInput(e.target.value) })}
            className="mt-1 input-trust"
            placeholder="$50,000"
          />
        </div>
        <div>
          <Label className="label-trust">Distribution Date</Label>
          <Input
            value={distribution_date}
            onChange={(e) => setData({ ...data, distribution_date: e.target.value })}
            className="mt-1 input-trust"
            placeholder="March 1, 2024"
          />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Characterization</Label>
          <Select value={distribution_characterization} onValueChange={(v) => setData({ ...data, distribution_characterization: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="income">Income</SelectItem>
              <SelectItem value="principal">Principal</SelectItem>
              <SelectItem value="return_of_corpus">Return of Corpus</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center justify-between mb-2">
        <Label className="label-trust">Beneficiaries</Label>
        <Button type="button" variant="ghost" size="sm" onClick={onAddItem}>
          <Plus className="w-4 h-4 mr-1" /> Add Beneficiary
        </Button>
      </div>
      <div className="flex gap-2 mb-1 px-1">
        <span className="flex-1 min-w-0 label-trust">Name</span>
        <span className="w-40 label-trust">Amount</span>
        <span className="w-20 label-trust">%</span>
        <span className="w-10" />
      </div>
      <div className="space-y-3">
        {distribution_items.map((item, index) => (
          <div key={index} className="flex gap-2 items-center">
            <div className="flex-1 min-w-0">
              <Input
                value={item.beneficiary_name}
                onChange={(e) => onItemChange(index, 'beneficiary_name', e.target.value)}
                placeholder="Beneficiary name"
                className="input-trust"
              />
            </div>
            <div className="w-40">
              <Input
                type="text"
                inputMode="numeric"
                value={formatCurrency(item.amount)}
                onChange={(e) => onItemChange(index, 'amount', parseCurrencyInput(e.target.value))}
                placeholder="$0"
                className="input-trust"
              />
            </div>
            <div className="w-20">
              <Input
                type="number"
                value={item.percentage}
                onChange={(e) => onItemChange(index, 'percentage', e.target.value)}
                placeholder="%"
                className="input-trust"
              />
            </div>
            {canRemoveItem ? (
              <Button type="button" variant="ghost" size="icon" className={removeIconBtn} onClick={() => onRemoveItem(index)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            ) : (
              <span className="w-10" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* ── Property Acceptance / Bill of Sale / Assignment ──────── */
export const PropertyFields = ({ data, setData, templateType }) => {
  const showAppraiser = templateType === 'assignment_of_personal_property';
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Property Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <Label className="label-trust">Grantor/Creator Name</Label>
          <Input
            value={data.grantor_name}
            onChange={(e) => setData({ ...data, grantor_name: e.target.value })}
            className="mt-1 input-trust"
            placeholder="John Smith"
          />
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Property Description</Label>
          <Textarea
            value={data.property_description}
            onChange={(e) => setData({ ...data, property_description: e.target.value })}
            className="mt-1"
            placeholder="Single-family residence located at 123 Main Street, City, State 12345; Lot 4, Block 2, Subdivision XYZ"
            rows={3}
          />
        </div>
        <div>
          <Label className="label-trust">Identifier (VIN, Account #, Legal Description)</Label>
          <Input
            value={data.property_identifier}
            onChange={(e) => setData({ ...data, property_identifier: e.target.value })}
            className="mt-1 input-trust"
            placeholder="VIN: 1HGBH41JXMN109186"
          />
        </div>
        <div>
          <Label className="label-trust">Location / Institution</Label>
          <Input
            value={data.property_location}
            onChange={(e) => setData({ ...data, property_location: e.target.value })}
            className="mt-1 input-trust"
            placeholder="123 Main St, City, State 12345"
          />
        </div>
        <div>
          <Label className="label-trust">Approximate Value ($)</Label>
          <Input
            type="text"
            inputMode="numeric"
            value={formatCurrency(data.property_value)}
            onChange={(e) => setData({ ...data, property_value: parseCurrencyInput(e.target.value) })}
            className="mt-1 input-trust"
            placeholder="$250,000"
          />
        </div>
        <div>
          <Label className="label-trust">Date of Conveyance</Label>
          <Input
            value={data.conveyance_date}
            onChange={(e) => setData({ ...data, conveyance_date: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., February 23, 2024"
          />
        </div>
        {showAppraiser && (
          <div className="md:col-span-2">
            <Label className="label-trust">Appraiser Name (if appraised)</Label>
            <Input
              value={data.appraiser_name || ''}
              onChange={(e) => setData({ ...data, appraiser_name: e.target.value })}
              className="mt-1 input-trust"
              placeholder="e.g., Sotheby's Appraisal Services"
            />
          </div>
        )}
        <div className="md:col-span-2 flex items-center gap-3 mt-2">
          <Checkbox
            checked={data.add_to_schedule_a}
            onCheckedChange={(checked) => setData({ ...data, add_to_schedule_a: checked })}
            id="add-schedule-a"
          />
          <Label htmlFor="add-schedule-a" className="cursor-pointer">Automatically add to Schedule A</Label>
        </div>
        {data.add_to_schedule_a && (
          <div className="md:col-span-2">
            <Label className="label-trust">Asset Category (for Schedule A)</Label>
            <Select value={data.schedule_a_category} onValueChange={(v) => setData({ ...data, schedule_a_category: v })}>
              <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                {ASSET_CATEGORIES.map((cat) => (
                  <SelectItem key={cat.value} value={cat.value}>{cat.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
    </div>
  );
};

/* ── Disposition of Asset ─────────────────────────────────── */
export const DispositionFields = ({ data, setData, scheduleAAssets, loadingAssets }) => {
  const hasAsset = !!data.disposition_asset_id;
  const isSale = data.disposition_reason === 'sale';
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Asset Disposition Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <Label className="label-trust">Select Asset from Schedule A</Label>
          {loadingAssets ? (
            <div className="mt-2 text-muted-foreground">Loading assets...</div>
          ) : scheduleAAssets.length === 0 ? (
            <div className="mt-2 text-muted-foreground">No active assets found in Schedule A</div>
          ) : (
            <Select
              value={data.disposition_asset_id}
              onValueChange={(v) => {
                const asset = scheduleAAssets.find((a) => a.item_id === v);
                setData({
                  ...data,
                  disposition_asset_id: v,
                  disposition_asset_description: asset ? `${asset.description} (${asset.category.replace(/_/g, ' ')})` : '',
                });
              }}
            >
              <SelectTrigger className="mt-1 h-10">
                <SelectValue placeholder="Select an asset to dispose" />
              </SelectTrigger>
              <SelectContent>
                {scheduleAAssets.map((asset) => (
                  <SelectItem key={asset.item_id} value={asset.item_id}>
                    {asset.description} - {asset.category.replace(/_/g, ' ')}
                    {asset.approximate_value && ` ($${asset.approximate_value.toLocaleString()})`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        {hasAsset && (
          <>
            <div className="md:col-span-2">
              <Label className="label-trust">Asset Description (for minutes)</Label>
              <Textarea
                value={data.disposition_asset_description}
                onChange={(e) => setData({ ...data, disposition_asset_description: e.target.value })}
                className="mt-1"
                placeholder="2020 Toyota Camry, VIN: 1HGBH41JXMN109186"
                rows={2}
              />
            </div>
            <div>
              <Label className="label-trust">Reason for Disposition</Label>
              <Select value={data.disposition_reason} onValueChange={(v) => setData({ ...data, disposition_reason: v })}>
                <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="sale">Sale</SelectItem>
                  <SelectItem value="transfer">Transfer</SelectItem>
                  <SelectItem value="donation">Donation</SelectItem>
                  <SelectItem value="destruction">Destruction / Total Loss</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="label-trust">Date of Disposition</Label>
              <Input
                value={data.disposition_date}
                onChange={(e) => setData({ ...data, disposition_date: e.target.value })}
                className="mt-1 input-trust"
                placeholder="e.g., February 23, 2024"
              />
            </div>
            <div>
              <Label className="label-trust">{isSale ? 'Sale Price ($)' : 'Fair Market Value ($)'}</Label>
              <Input
                type="text"
                inputMode="numeric"
                value={formatCurrency(data.disposition_value)}
                onChange={(e) => setData({ ...data, disposition_value: parseCurrencyInput(e.target.value) })}
                className={currencyInputClass}
                placeholder="$25,000"
              />
            </div>
            <div>
              <Label className="label-trust">{isSale ? 'Buyer' : 'Recipient'} (if applicable)</Label>
              <Input
                value={data.disposition_recipient}
                onChange={(e) => setData({ ...data, disposition_recipient: e.target.value })}
                className="mt-1 input-trust"
                placeholder="ABC Motors LLC"
              />
            </div>
            <div className="md:col-span-2">
              <Label className="label-trust">Additional Notes</Label>
              <Textarea
                value={data.disposition_notes}
                onChange={(e) => setData({ ...data, disposition_notes: e.target.value })}
                className="mt-1"
                placeholder="Any additional details about the disposition..."
                rows={2}
              />
            </div>
            <div className="md:col-span-2 flex items-center gap-3 mt-2">
              <Checkbox
                checked={data.update_schedule_a}
                onCheckedChange={(checked) => setData({ ...data, update_schedule_a: checked })}
                id="update-schedule-a"
              />
              <Label htmlFor="update-schedule-a" className="cursor-pointer">
                Mark asset as disposed in Schedule A (keeps historical record)
              </Label>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

/* ── Trustee Appointment (additional / successor) ─────────── */
export const TrusteeAppointmentFields = ({ data, setData, templateType }) => {
  const isSuccessor = templateType === 'appointment_successor_trustee';
  const showThreshold = data.signature_requirement === 'threshold' || data.signature_requirement === 'all_trustees';
  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">
        {isSuccessor ? 'Successor Trustee Details' : 'New Trustee Details'}
      </h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">New Trustee Name</Label>
          <Input
            value={data.new_trustee_name}
            onChange={(e) => setData({ ...data, new_trustee_name: e.target.value })}
            className="mt-1 input-trust"
            placeholder="Jane Doe"
          />
        </div>
        <div>
          <Label className="label-trust">Gender (for document language)</Label>
          <Select value={data.new_trustee_gender} onValueChange={(v) => setData({ ...data, new_trustee_gender: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="man">Man</SelectItem>
              <SelectItem value="woman">Woman</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {isSuccessor && (
          <>
            <div>
              <Label className="label-trust">Departing Trustee Name</Label>
              <Input
                value={data.departing_trustee_name}
                onChange={(e) => setData({ ...data, departing_trustee_name: e.target.value })}
                className="mt-1 input-trust"
                placeholder="John Smith"
              />
            </div>
            <div>
              <Label className="label-trust">Reason for Departure</Label>
              <Select value={data.departing_reason} onValueChange={(v) => setData({ ...data, departing_reason: v })}>
                <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="resigned">Resigned</SelectItem>
                  <SelectItem value="died">Died</SelectItem>
                  <SelectItem value="incapacitated">Become Incapacitated</SelectItem>
                  <SelectItem value="removed">Been Removed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </>
        )}
        <div>
          <Label className="label-trust">Effective Date</Label>
          <Input
            value={data.effective_date}
            onChange={(e) => setData({ ...data, effective_date: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., February 23, 2024"
          />
        </div>
        <div>
          <Label className="label-trust">Signature Requirement</Label>
          <Select value={data.signature_requirement} onValueChange={(v) => setData({ ...data, signature_requirement: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any_one">Any One Trustee (no limit)</SelectItem>
              <SelectItem value="any_two">Any Two Trustees (all transactions)</SelectItem>
              <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
              <SelectItem value="all_trustees">All Trustees (above threshold)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {showThreshold && (
          <div>
            <Label className="label-trust">Signature Threshold Amount ($)</Label>
            <Input
              type="text"
              inputMode="numeric"
              value={formatCurrency(data.signature_threshold)}
              onChange={(e) => setData({ ...data, signature_threshold: parseCurrencyInput(e.target.value) })}
              className="mt-1 input-trust"
              placeholder="$10,000"
            />
          </div>
        )}
        <div className="md:col-span-2 flex items-center gap-3 mt-2">
          <Checkbox
            checked={data.banking_powers_granted}
            onCheckedChange={(checked) => setData({ ...data, banking_powers_granted: checked })}
            id="banking-powers"
          />
          <Label htmlFor="banking-powers" className="cursor-pointer">Grant banking and signatory powers</Label>
        </div>
      </div>
    </div>
  );
};

/* ── Beneficiary Designation ──────────────────────────────── */
export const BeneficiaryDesignationFields = ({ data, setData }) => {
  const updateBen = (index, field, value) => {
    const newBens = [...data.beneficiaries];
    newBens[index] = { ...newBens[index], [field]: value };
    setData({ ...data, beneficiaries: newBens });
  };
  const addBen = () => setData((prev) => ({
    ...prev,
    beneficiaries: [...prev.beneficiaries, { name: '', units: '', percentage: '', relationship: '' }],
  }));
  const removeBen = (index) => setData((prev) => ({
    ...prev,
    beneficiaries: prev.beneficiaries.filter((_, i) => i !== index),
  }));

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Beneficiary Designation</h2>
      <div className="grid md:grid-cols-2 gap-4 mb-6">
        <div>
          <Label className="label-trust">Designation Type</Label>
          <Select value={data.designation_type} onValueChange={(v) => setData({ ...data, designation_type: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="initial">Initial Designation</SelectItem>
              <SelectItem value="amendment">Amendment to Existing</SelectItem>
              <SelectItem value="restatement">Complete Restatement</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="label-trust">Total Units of Beneficial Interest</Label>
          <Input
            type="number"
            value={data.total_units}
            onChange={(e) => setData({ ...data, total_units: e.target.value })}
            className="mt-1 input-trust"
            placeholder="100"
          />
        </div>
      </div>
      <div className="flex items-center justify-between mb-2">
        <Label className="label-trust">Beneficiaries</Label>
        <Button type="button" variant="ghost" size="sm" onClick={addBen}>
          <Plus className="w-4 h-4 mr-1" /> Add Beneficiary
        </Button>
      </div>
      <div className="space-y-3">
        {data.beneficiaries.map((ben, index) => (
          <div key={index} className="flex gap-2 items-end">
            <div className="flex-1">
              <Input
                value={ben.name}
                onChange={(e) => updateBen(index, 'name', e.target.value)}
                placeholder="Beneficiary name"
                className="input-trust"
              />
            </div>
            <div className="w-24">
              <Input
                type="number"
                value={ben.units}
                onChange={(e) => updateBen(index, 'units', e.target.value)}
                placeholder="Units"
                className="input-trust"
              />
            </div>
            <div className="w-20">
              <Input
                type="number"
                value={ben.percentage}
                onChange={(e) => updateBen(index, 'percentage', e.target.value)}
                placeholder="%"
                className="input-trust"
              />
            </div>
            <div className="w-32">
              <Input
                value={ben.relationship}
                onChange={(e) => updateBen(index, 'relationship', e.target.value)}
                placeholder="Relationship"
                className="input-trust"
              />
            </div>
            {data.beneficiaries.length > 1 && (
              <Button type="button" variant="ghost" size="icon" onClick={() => removeBen(index)}>
                <Trash2 className="w-4 h-4 text-red-500" />
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

/* ── Bank Account Authorization ───────────────────────────── */
export const BankAccountFields = ({ data, setData }) => {
  const showThreshold = data.signature_requirement === 'threshold';
  const updateSigner = (index, value) => {
    const newSigners = [...data.authorized_signers];
    newSigners[index] = value;
    setData({ ...data, authorized_signers: newSigners });
  };
  const addSigner = () => setData((prev) => ({ ...prev, authorized_signers: [...prev.authorized_signers, ''] }));
  const removeSigner = (index) => setData((prev) => ({
    ...prev,
    authorized_signers: prev.authorized_signers.filter((_, i) => i !== index),
  }));

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Bank Account Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Bank/Institution Name</Label>
          <Input
            value={data.bank_name}
            onChange={(e) => setData({ ...data, bank_name: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., Chase Bank, Charles Schwab"
          />
        </div>
        <div>
          <Label className="label-trust">Account Type</Label>
          <Select value={data.account_type} onValueChange={(v) => setData({ ...data, account_type: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="checking">Checking Account</SelectItem>
              <SelectItem value="savings">Savings Account</SelectItem>
              <SelectItem value="brokerage">Brokerage/Investment Account</SelectItem>
              <SelectItem value="money_market">Money Market Account</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="md:col-span-2">
          <Label className="label-trust">Purpose</Label>
          <Input
            value={data.purpose}
            onChange={(e) => setData({ ...data, purpose: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., general trust administration, investment holdings"
          />
        </div>
        <div>
          <Label className="label-trust">Signature Requirement</Label>
          <Select value={data.signature_requirement} onValueChange={(v) => setData({ ...data, signature_requirement: v })}>
            <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any_one">Any One Trustee</SelectItem>
              <SelectItem value="any_two">Any Two Trustees</SelectItem>
              <SelectItem value="threshold">One up to threshold, Two above</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {showThreshold && (
          <div>
            <Label className="label-trust">Signature Threshold ($)</Label>
            <Input
              type="text"
              inputMode="numeric"
              value={formatCurrency(data.signature_threshold)}
              onChange={(e) => setData({ ...data, signature_threshold: parseCurrencyInput(e.target.value) })}
              className="mt-1 input-trust"
              placeholder="$10,000"
            />
          </div>
        )}
        <div>
          <Label className="label-trust">Initial Deposit ($)</Label>
          <Input
            type="text"
            inputMode="numeric"
            value={formatCurrency(data.initial_deposit)}
            onChange={(e) => setData({ ...data, initial_deposit: parseCurrencyInput(e.target.value) })}
            className="mt-1 input-trust"
            placeholder="$0"
          />
        </div>
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <Label className="label-trust">Authorized Signers</Label>
          <Button type="button" variant="ghost" size="sm" onClick={addSigner}>
            <Plus className="w-4 h-4 mr-1" /> Add Signer
          </Button>
        </div>
        <div className="space-y-2">
          {data.authorized_signers.map((signer, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={signer}
                onChange={(e) => updateSigner(index, e.target.value)}
                className="input-trust"
                placeholder="Trustee name"
              />
              {data.authorized_signers.length > 1 && (
                <Button type="button" variant="ghost" size="icon" onClick={() => removeSigner(index)}>
                  <Trash2 className="w-4 h-4 text-red-500" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ── Change of Situs ──────────────────────────────────────── */
export const SitusFields = ({ data, setData }) => {
  const updateReason = (index, value) => {
    const newReasons = [...data.reasons];
    newReasons[index] = value;
    setData({ ...data, reasons: newReasons });
  };
  const addReason = () => setData((prev) => ({ ...prev, reasons: [...prev.reasons, ''] }));
  const removeReason = (index) => setData((prev) => ({
    ...prev,
    reasons: prev.reasons.filter((_, i) => i !== index),
  }));

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Change of Situs Details</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Current Situs (State/Jurisdiction)</Label>
          <Input
            value={data.current_situs}
            onChange={(e) => setData({ ...data, current_situs: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., State of Texas"
          />
        </div>
        <div>
          <Label className="label-trust">New Situs (State/Jurisdiction)</Label>
          <Input
            value={data.new_situs}
            onChange={(e) => setData({ ...data, new_situs: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., State of Nevada"
          />
        </div>
        <div>
          <Label className="label-trust">Effective Date</Label>
          <Input
            value={data.effective_date}
            onChange={(e) => setData({ ...data, effective_date: e.target.value })}
            className="mt-1 input-trust"
            placeholder="March 1, 2024"
          />
        </div>
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <Label className="label-trust">Reasons for Change (optional)</Label>
          <Button type="button" variant="ghost" size="sm" onClick={addReason}>
            <Plus className="w-4 h-4 mr-1" /> Add Reason
          </Button>
        </div>
        <div className="space-y-2">
          {data.reasons.map((reason, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={reason}
                onChange={(e) => updateReason(index, e.target.value)}
                className="input-trust"
                placeholder="e.g., Favorable trust laws, tax considerations"
              />
              {data.reasons.length > 1 && (
                <Button type="button" variant="ghost" size="icon" onClick={() => removeReason(index)}>
                  <Trash2 className="w-4 h-4 text-red-500" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ── Benevolence Approval ─────────────────────────────────── */
export const BenevolenceFields = ({ data, setData }) => (
  <div className="card-trust corner-mark p-6">
    <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Benevolence Grant Details</h2>
    <div className="grid md:grid-cols-2 gap-4">
      <div className="md:col-span-2">
        <Label className="label-trust">Beneficiary Name *</Label>
        <Input
          value={data.beneficiary_name}
          onChange={(e) => setData({ ...data, beneficiary_name: e.target.value })}
          className="mt-1 input-trust"
          placeholder="Name of recipient"
        />
      </div>
      <div>
        <Label className="label-trust">Beneficiary Type</Label>
        <Select value={data.beneficiary_type} onValueChange={(v) => setData({ ...data, beneficiary_type: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="individual">Individual</SelectItem>
            <SelectItem value="family">Family</SelectItem>
            <SelectItem value="organization">Organization</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="label-trust">Purpose Category</Label>
        <Select value={data.benevolence_purpose} onValueChange={(v) => setData({ ...data, benevolence_purpose: v })}>
          <SelectTrigger className="mt-1 h-10"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="medical">Medical Expenses</SelectItem>
            <SelectItem value="housing">Housing Assistance</SelectItem>
            <SelectItem value="education">Education</SelectItem>
            <SelectItem value="food_necessities">Food & Necessities</SelectItem>
            <SelectItem value="utilities">Utilities</SelectItem>
            <SelectItem value="transportation">Transportation</SelectItem>
            <SelectItem value="emergency">Emergency Relief</SelectItem>
            <SelectItem value="spiritual">Spiritual/Ministry</SelectItem>
            <SelectItem value="assistance">General Assistance</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="md:col-span-2">
        <Label className="label-trust">Purpose Description *</Label>
        <Textarea
          value={data.purpose_description}
          onChange={(e) => setData({ ...data, purpose_description: e.target.value })}
          className="mt-1"
          placeholder="Describe the need and how the assistance will help"
          rows={3}
        />
      </div>
      <div>
        <Label className="label-trust">Grant Amount ($) *</Label>
        <Input
          type="text"
          inputMode="numeric"
          value={formatCurrency(data.amount)}
          onChange={(e) => setData({ ...data, amount: parseCurrencyInput(e.target.value) })}
          className="mt-1 input-trust"
          placeholder="$500"
        />
      </div>
      <div>
        <Label className="label-trust">Disbursement Date</Label>
        <Input
          value={data.disbursement_date}
          onChange={(e) => setData({ ...data, disbursement_date: e.target.value })}
          className="mt-1 input-trust"
          placeholder="March 1, 2024"
        />
      </div>
      <div className="md:col-span-2 flex items-center gap-3 mt-2">
        <Checkbox
          checked={data.add_to_benevolence_log}
          onCheckedChange={(checked) => setData({ ...data, add_to_benevolence_log: checked })}
          id="add-benevolence-log"
        />
        <Label htmlFor="add-benevolence-log" className="cursor-pointer">Automatically add to Benevolence Log</Label>
      </div>
    </div>
  </div>
);