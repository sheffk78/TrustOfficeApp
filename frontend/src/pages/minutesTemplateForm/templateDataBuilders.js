/**
 * Per-template data builders extracted from MinutesTemplateFormPage.
 *
 * Each builder receives a `ctx` object with the relevant state slices and
 * returns the template-specific data object. The dispatch map
 * `TEMPLATE_DATA_BUILDERS` maps templateType → builder function.
 *
 * `buildTemplateData(templateType, ctx)` is the single entry point used by
 * the page component, preserving the exact behaviour of the original
 * inline switch statement.
 */

const buildBaseData = (ctx) => {
  const { formData, trustEntity } = ctx;
  return {
    ...formData,
    trustees_present: formData.trustees_present.filter((t) => t.trim()),
    article_ref_distribution: trustEntity?.article_ref_distribution || '',
    article_ref_compensation: trustEntity?.article_ref_compensation || '',
    article_ref_amendment: trustEntity?.article_ref_amendment || '',
    beneficiary_standard: trustEntity?.beneficiary_standard || '',
  };
};

const buildInitialTrusteeMeeting = (ctx) => {
  const base = buildBaseData(ctx);
  const { formData } = ctx;
  return {
    ...base,
    bank_name: formData.bank_name || '',
    initial_deposit: formData.initial_deposit || '',
    meeting_location: formData.meeting_location || '',
    meeting_time: formData.meeting_time || '',
    principal_place: formData.principal_place || formData.meeting_location || '',
    fiscal_year_end: formData.fiscal_year_end || 'December 31',
    compensation_type: formData.compensation_type || 'none',
    compensation_amount: formData.compensation_amount || '',
    accept_trusteeship: formData.accept_trusteeship !== false,
    acknowledge_fiduciary_duties: formData.acknowledge_fiduciary_duties !== false,
    authorize_ein: formData.authorize_ein !== false,
    accept_initial_property: formData.accept_initial_property !== false,
    authorize_insurance: formData.authorize_insurance !== false,
    authorize_professional_services: formData.authorize_professional_services !== false,
    designate_record_keeper: formData.designate_record_keeper !== false,
    adopt_governance_standards: formData.adopt_governance_standards !== false,
    ratify_prior_actions: formData.ratify_prior_actions !== false,
  };
};

const buildDistributionToBeneficiaries = (ctx) => {
  const base = buildBaseData(ctx);
  const { distributionData } = ctx;
  return {
    ...base,
    distribution_total: parseFloat(distributionData.distribution_total) || 0,
    distribution_items: distributionData.distribution_items
      .filter((item) => item.beneficiary_name)
      .map((item) => ({
        beneficiary_name: item.beneficiary_name,
        amount: parseFloat(item.amount) || 0,
        percentage: parseFloat(item.percentage) || 0,
      })),
    distribution_date: distributionData.distribution_date,
    distribution_characterization: distributionData.distribution_characterization,
  };
};

const buildPropertyAcceptance = (ctx) => {
  const base = buildBaseData(ctx);
  const { propertyData } = ctx;
  return {
    ...base,
    grantor_name: propertyData.grantor_name,
    property_description: propertyData.property_description,
    property_value: parseFloat(propertyData.property_value) || null,
    property_identifier: propertyData.property_identifier,
    property_location: propertyData.property_location,
    conveyance_date: propertyData.conveyance_date,
    appraiser_name: propertyData.appraiser_name || null,
    add_to_schedule_a: propertyData.add_to_schedule_a,
    schedule_a_category: propertyData.schedule_a_category,
  };
};

const buildDispositionOfAsset = (ctx) => {
  const base = buildBaseData(ctx);
  const { dispositionData } = ctx;
  return {
    ...base,
    disposition_asset_id: dispositionData.disposition_asset_id,
    disposition_asset_description: dispositionData.disposition_asset_description,
    disposition_reason: dispositionData.disposition_reason,
    disposition_date: dispositionData.disposition_date,
    disposition_value: parseFloat(dispositionData.disposition_value) || null,
    disposition_recipient: dispositionData.disposition_recipient,
    disposition_notes: dispositionData.disposition_notes,
    update_schedule_a: dispositionData.update_schedule_a,
  };
};

const buildTrusteeAppointment = (ctx) => {
  const base = buildBaseData(ctx);
  const { templateType, trusteeData } = ctx;
  return {
    ...base,
    appointment_type: templateType === 'appointment_successor_trustee' ? 'successor' : 'additional',
    new_trustee_name: trusteeData.new_trustee_name,
    new_trustee_gender: trusteeData.new_trustee_gender,
    departing_trustee_name: trusteeData.departing_trustee_name,
    departing_reason: trusteeData.departing_reason,
    signature_requirement: trusteeData.signature_requirement,
    signature_threshold: parseFloat(trusteeData.signature_threshold) || null,
    banking_powers_granted: trusteeData.banking_powers_granted,
    effective_date: trusteeData.effective_date,
  };
};

const buildDesignationOfBeneficiaries = (ctx) => {
  const base = buildBaseData(ctx);
  const { beneficiaryData } = ctx;
  return {
    ...base,
    designation_type: beneficiaryData.designation_type,
    total_units: parseInt(beneficiaryData.total_units) || 100,
    beneficiaries: beneficiaryData.beneficiaries
      .filter((b) => b.name)
      .map((b) => ({
        name: b.name,
        units: parseInt(b.units) || 0,
        percentage: parseFloat(b.percentage) || 0,
        relationship: b.relationship,
      })),
  };
};

const buildBankAccountAuthorization = (ctx) => {
  const base = buildBaseData(ctx);
  const { bankData } = ctx;
  return {
    ...base,
    bank_name: bankData.bank_name,
    account_type: bankData.account_type,
    purpose: bankData.purpose,
    authorized_signers: bankData.authorized_signers.filter((s) => s.trim()),
    signature_requirement: bankData.signature_requirement,
    signature_threshold: parseFloat(bankData.signature_threshold) || null,
    initial_deposit: parseFloat(bankData.initial_deposit) || null,
  };
};

const buildChangeOfSitus = (ctx) => {
  const base = buildBaseData(ctx);
  const { situsData } = ctx;
  return {
    ...base,
    current_situs: situsData.current_situs,
    new_situs: situsData.new_situs,
    effective_date: situsData.effective_date,
    reasons: situsData.reasons.filter((r) => r.trim()),
  };
};

const buildBenevolenceApproval = (ctx) => {
  const base = buildBaseData(ctx);
  const { benevolenceData } = ctx;
  return {
    ...base,
    beneficiary_name: benevolenceData.beneficiary_name,
    beneficiary_type: benevolenceData.beneficiary_type,
    benevolence_purpose: benevolenceData.benevolence_purpose,
    purpose_description: benevolenceData.purpose_description,
    amount: parseFloat(benevolenceData.amount) || 0,
    disbursement_date: benevolenceData.disbursement_date,
    add_to_benevolence_log: benevolenceData.add_to_benevolence_log,
  };
};

const buildInvestmentPolicy = (ctx) => {
  const base = buildBaseData(ctx);
  const { investmentPolicyData } = ctx;
  return {
    ...base,
    policy_type: investmentPolicyData.policy_type,
    risk_tolerance: investmentPolicyData.risk_tolerance,
    asset_allocation: investmentPolicyData.asset_allocation,
    investment_restrictions: investmentPolicyData.investment_restrictions.filter((r) => r.trim()),
    review_frequency: investmentPolicyData.review_frequency,
  };
};

const buildLoanAuthorization = (ctx) => {
  const base = buildBaseData(ctx);
  const { loanAuthData } = ctx;
  return {
    ...base,
    loan_direction: loanAuthData.loan_direction,
    borrower_name: loanAuthData.borrower_name,
    lender_name: loanAuthData.lender_name,
    loan_amount: parseFloat(loanAuthData.loan_amount) || 0,
    interest_rate: loanAuthData.interest_rate,
    term_months: parseInt(loanAuthData.term_months) || 60,
    loan_purpose: loanAuthData.loan_purpose,
    collateral_description: loanAuthData.collateral_description,
  };
};

const buildInsuranceAuthorization = (ctx) => {
  const base = buildBaseData(ctx);
  const { insuranceData } = ctx;
  return {
    ...base,
    insurance_type: insuranceData.insurance_type,
    policy_action: insuranceData.policy_action,
    insurer_name: insuranceData.insurer_name,
    coverage_amount: parseFloat(insuranceData.coverage_amount) || 0,
    premium_amount: parseFloat(insuranceData.premium_amount) || 0,
    coverage_description: insuranceData.coverage_description,
    policy_number: insuranceData.policy_number,
  };
};

const buildAnnualReview = (ctx) => {
  const base = buildBaseData(ctx);
  const { annualReviewData } = ctx;
  return {
    ...base,
    fiscal_year: annualReviewData.fiscal_year,
    total_assets: parseFloat(annualReviewData.total_assets) || 0,
    total_income: parseFloat(annualReviewData.total_income) || 0,
    total_expenses: parseFloat(annualReviewData.total_expenses) || 0,
    total_distributions: parseFloat(annualReviewData.total_distributions) || 0,
    investment_return: annualReviewData.investment_return,
    key_accomplishments: annualReviewData.key_accomplishments.filter((a) => a.trim()),
    upcoming_priorities: annualReviewData.upcoming_priorities.filter((p) => p.trim()),
    governance_items: annualReviewData.governance_items.filter((g) => g.trim()),
  };
};

const buildQuarterlyReview = (ctx) => {
  const base = buildBaseData(ctx);
  const { quarterlyReviewData } = ctx;
  return {
    ...base,
    quarter: quarterlyReviewData.quarter,
    year: quarterlyReviewData.year,
    beginning_balance: parseFloat(quarterlyReviewData.beginning_balance) || 0,
    ending_balance: parseFloat(quarterlyReviewData.ending_balance) || 0,
    income_received: parseFloat(quarterlyReviewData.income_received) || 0,
    expenses_paid: parseFloat(quarterlyReviewData.expenses_paid) || 0,
    distributions_made: parseFloat(quarterlyReviewData.distributions_made) || 0,
    discussion_items: quarterlyReviewData.discussion_items.filter((d) => d.trim()),
    action_items: quarterlyReviewData.action_items.filter((a) => a.trim()),
  };
};

const buildTrusteeCompensation = (ctx) => {
  const base = buildBaseData(ctx);
  const { trusteeCompData } = ctx;
  return {
    ...base,
    trustee_name: trusteeCompData.trustee_name,
    compensation_type: trusteeCompData.compensation_type,
    compensation_amount: parseFloat(trusteeCompData.compensation_amount) || 0,
    effective_date: trusteeCompData.effective_date,
    compensation_basis: trusteeCompData.compensation_basis,
    duties_description: trusteeCompData.duties_description,
    all_trustees: trusteeCompData.all_trustees,
  };
};

const buildTrusteeResignation = (ctx) => {
  const base = buildBaseData(ctx);
  const { trusteeResignData } = ctx;
  return {
    ...base,
    departing_trustee_name: trusteeResignData.departing_trustee_name,
    departure_type: trusteeResignData.departure_type,
    departure_reason: trusteeResignData.departure_reason,
    effective_date: trusteeResignData.effective_date,
    remaining_trustees: trusteeResignData.remaining_trustees.filter((t) => t.trim()),
    successor_appointed: trusteeResignData.successor_appointed,
    successor_name: trusteeResignData.successor_name,
  };
};

const buildBeneficiaryRequestDenial = (ctx) => {
  const base = buildBaseData(ctx);
  const { denialData } = ctx;
  return {
    ...base,
    beneficiary_name: denialData.beneficiary_name,
    request_type: denialData.request_type,
    request_amount: parseFloat(denialData.request_amount) || 0,
    request_purpose: denialData.request_purpose,
    request_date: denialData.request_date,
    denial_reasons: denialData.denial_reasons.filter((r) => r.trim()),
    alternative_offered: denialData.alternative_offered,
  };
};

const buildHemsDistribution = (ctx) => {
  const base = buildBaseData(ctx);
  const { hemsData } = ctx;
  return {
    ...base,
    beneficiary_name: hemsData.beneficiary_name,
    hems_category: hemsData.hems_category,
    distribution_amount: parseFloat(hemsData.distribution_amount) || 0,
    specific_purpose: hemsData.specific_purpose,
    supporting_documentation: hemsData.supporting_documentation.filter((d) => d.trim()),
    recurring: hemsData.recurring,
    recurring_frequency: hemsData.recurring_frequency,
  };
};

const buildBeneficiaryDistributionNotice = (ctx) => {
  const base = buildBaseData(ctx);
  const { distributionNoticeData } = ctx;
  return {
    ...base,
    beneficiary_name: distributionNoticeData.beneficiary_name,
    distribution_amount: parseFloat(distributionNoticeData.distribution_amount) || 0,
    distribution_purpose: distributionNoticeData.distribution_purpose,
    distribution_date: distributionNoticeData.distribution_date,
    trustee_name: distributionNoticeData.trustee_name,
  };
};

const buildBeneficiaryLoan = (ctx) => {
  const base = buildBaseData(ctx);
  const { beneficiaryLoanData } = ctx;
  return {
    ...base,
    beneficiary_name: beneficiaryLoanData.beneficiary_name,
    loan_amount: parseFloat(beneficiaryLoanData.loan_amount) || 0,
    interest_rate: beneficiaryLoanData.interest_rate,
    term_months: parseInt(beneficiaryLoanData.term_months) || 60,
    loan_purpose: beneficiaryLoanData.loan_purpose,
    collateral_description: beneficiaryLoanData.collateral_description,
    repayment_terms: beneficiaryLoanData.repayment_terms,
  };
};

const buildTrustAmendment = (ctx) => {
  const base = buildBaseData(ctx);
  const { amendmentData } = ctx;
  return {
    ...base,
    amendment_type: amendmentData.amendment_type,
    article_section: amendmentData.article_section,
    current_provision: amendmentData.current_provision,
    amended_provision: amendmentData.amended_provision,
    effective_date: amendmentData.effective_date,
    reason: amendmentData.reason,
  };
};

const buildPowerOfAttorney = (ctx) => {
  const base = buildBaseData(ctx);
  const { poaData } = ctx;
  return {
    ...base,
    agent_name: poaData.agent_name,
    scope: poaData.scope,
    powers_granted: poaData.powers_granted.filter((p) => p.trim()),
    expiration: poaData.expiration,
    purpose: poaData.purpose,
  };
};

const buildTrustTermination = (ctx) => {
  const base = buildBaseData(ctx);
  const { terminationData } = ctx;
  return {
    ...base,
    termination_reason: terminationData.termination_reason,
    termination_date: terminationData.termination_date,
    distribution_plan: terminationData.distribution_plan,
    final_accounting_date: terminationData.final_accounting_date,
    outstanding_obligations: terminationData.outstanding_obligations,
  };
};

const buildRealEstatePurchase = (ctx) => {
  const base = buildBaseData(ctx);
  const { realEstatePurchaseData } = ctx;
  return {
    ...base,
    property_address: realEstatePurchaseData.property_address,
    property_type: realEstatePurchaseData.property_type,
    purchase_price: realEstatePurchaseData.purchase_price,
    financing: realEstatePurchaseData.financing,
    purpose: realEstatePurchaseData.purpose,
    inspection_period: realEstatePurchaseData.inspection_period,
  };
};

const buildBusinessInterestAcquisition = (ctx) => {
  const base = buildBaseData(ctx);
  const { businessInterestData } = ctx;
  return {
    ...base,
    entity_name: businessInterestData.entity_name,
    entity_type: businessInterestData.entity_type,
    ownership_percentage: businessInterestData.ownership_percentage,
    purchase_price: businessInterestData.purchase_price,
    purpose: businessInterestData.purpose,
    due_diligence: businessInterestData.due_diligence,
  };
};

const buildRealEstateLease = (ctx) => {
  const base = buildBaseData(ctx);
  const { realEstateLeaseData } = ctx;
  return {
    ...base,
    property_address: realEstateLeaseData.property_address,
    tenant_name: realEstateLeaseData.tenant_name,
    lease_term: realEstateLeaseData.lease_term,
    monthly_rent: realEstateLeaseData.monthly_rent,
    security_deposit: realEstateLeaseData.security_deposit,
    permitted_use: realEstateLeaseData.permitted_use,
  };
};

const buildFiscalYearElection = (ctx) => {
  const base = buildBaseData(ctx);
  const { fiscalYearData } = ctx;
  return {
    ...base,
    fiscal_year_end: fiscalYearData.fiscal_year_end,
    election_type: fiscalYearData.election_type,
    effective_year: fiscalYearData.effective_year,
    reason: fiscalYearData.reason,
  };
};

const buildTaxFilingAuthorization = (ctx) => {
  const base = buildBaseData(ctx);
  const { taxFilingData } = ctx;
  return {
    ...base,
    tax_year: taxFilingData.tax_year,
    preparer_name: taxFilingData.preparer_name,
    returns_to_file: taxFilingData.returns_to_file.filter((r) => r.trim()),
    filing_deadline: taxFilingData.filing_deadline,
    extension_authorized: taxFilingData.extension_authorized,
  };
};

const buildEmergencyRatification = (ctx) => {
  const base = buildBaseData(ctx);
  const { emergencyData } = ctx;
  return {
    ...base,
    action_date: emergencyData.action_date,
    emergency_type: emergencyData.emergency_type,
    actions_taken: emergencyData.actions_taken.filter((a) => a.trim()),
    trustee_acting: emergencyData.trustee_acting,
    cost_incurred: emergencyData.cost_incurred,
    outcome: emergencyData.outcome,
  };
};

const buildConflictOfInterest = (ctx) => {
  const base = buildBaseData(ctx);
  const { conflictData } = ctx;
  return {
    ...base,
    trustee_name: conflictData.trustee_name,
    conflict_type: conflictData.conflict_type,
    description: conflictData.description,
    related_transaction: conflictData.related_transaction,
    disclosure_date: conflictData.disclosure_date,
    waiver_granted: conflictData.waiver_granted,
    conditions: conflictData.conditions,
  };
};

const buildSpendingAuthorization = (ctx) => {
  const base = buildBaseData(ctx);
  const { spendingAuthData } = ctx;
  return {
    ...base,
    expenditure_amount: spendingAuthData.expenditure_amount,
    expenditure_date: spendingAuthData.expenditure_date,
    expenditure_purpose: spendingAuthData.expenditure_purpose,
    expenditure_vendor: spendingAuthData.expenditure_vendor,
    expenditure_source_account: spendingAuthData.expenditure_source_account,
  };
};

const buildGeneralMeeting = (ctx) => {
  const base = buildBaseData(ctx);
  const { resolutions } = ctx;
  return {
    ...base,
    resolutions: resolutions
      .filter((r) => r.title)
      .map((r) => ({
        title: r.title,
        whereas_clauses: r.whereas_clauses.filter((c) => c.trim()),
        resolved_clauses: r.resolved_clauses.filter((c) => c.trim()),
        vote: r.vote,
        effective_date: r.effective_date,
      })),
  };
};

/**
 * Dispatch map: templateType → builder function.
 * Template types that share a builder are grouped via arrays of keys.
 */
const TEMPLATE_DATA_BUILDERS = {
  initial_trustee_meeting: buildInitialTrusteeMeeting,
  distribution_to_beneficiaries: buildDistributionToBeneficiaries,
  acceptance_of_property: buildPropertyAcceptance,
  bill_of_sale: buildPropertyAcceptance,
  assignment_of_personal_property: buildPropertyAcceptance,
  general_assignment: buildPropertyAcceptance,
  disposition_of_asset: buildDispositionOfAsset,
  appointment_additional_trustee: buildTrusteeAppointment,
  appointment_successor_trustee: buildTrusteeAppointment,
  designation_of_beneficiaries: buildDesignationOfBeneficiaries,
  bank_account_authorization: buildBankAccountAuthorization,
  change_of_situs: buildChangeOfSitus,
  benevolence_approval: buildBenevolenceApproval,
  investment_policy: buildInvestmentPolicy,
  loan_authorization: buildLoanAuthorization,
  insurance_authorization: buildInsuranceAuthorization,
  annual_review: buildAnnualReview,
  quarterly_review: buildQuarterlyReview,
  trustee_compensation: buildTrusteeCompensation,
  trustee_resignation: buildTrusteeResignation,
  beneficiary_request_denial: buildBeneficiaryRequestDenial,
  hems_distribution: buildHemsDistribution,
  beneficiary_distribution_notice: buildBeneficiaryDistributionNotice,
  beneficiary_loan: buildBeneficiaryLoan,
  trust_amendment: buildTrustAmendment,
  power_of_attorney: buildPowerOfAttorney,
  trust_termination: buildTrustTermination,
  real_estate_purchase: buildRealEstatePurchase,
  business_interest_acquisition: buildBusinessInterestAcquisition,
  real_estate_lease: buildRealEstateLease,
  fiscal_year_election: buildFiscalYearElection,
  tax_filing_authorization: buildTaxFilingAuthorization,
  emergency_ratification: buildEmergencyRatification,
  conflict_of_interest: buildConflictOfInterest,
  general_meeting: buildGeneralMeeting,
  spending_authorization: buildSpendingAuthorization,
  evaluate_distribution: (ctx) => {
    const base = buildBaseData(ctx);
    const { evalData } = ctx;
    return {
      ...base,
      beneficiary_name: evalData?.beneficiary_name || '',
      requested_amount: evalData?.requested_amount || '',
      request_purpose: evalData?.request_purpose || '',
      hems_category: evalData?.hems_category || 'support',
      beneficiary_financial_situation: evalData?.beneficiary_financial_situation || '',
      beneficiary_other_resources: evalData?.beneficiary_other_resources || '',
      past_distributions_note: evalData?.past_distributions_note || '',
    };
  },
};

/**
 * Build the template-specific data payload for the given template type.
 * Falls back to the general_meeting builder for unknown types.
 */
export const buildTemplateData = (templateType, ctx) => {
  const builder = TEMPLATE_DATA_BUILDERS[templateType] || buildGeneralMeeting;
  return builder({ ...ctx, templateType });
};