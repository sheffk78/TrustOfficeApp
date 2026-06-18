// Page help content for PageHelpButton component
// Each entry: { page, items: [{text}], taPrompt }

const PAGE_HELP = {
  Dashboard: {
    items: [
      { text: 'View your trust\'s key metrics at a glance — defensibility score, upcoming deadlines, and recent activity' },
      { text: 'Use Quick Actions to jump to common tasks like recording a distribution or adding an asset' },
      { text: 'Complete your onboarding checklist to set up your trust profile' },
    ],
    taPrompt: 'Walk me through the Dashboard page and what I should do first',
  },
  Minutes: {
    items: [
      { text: 'Create, review, and manage trust meeting minutes for all your trust decisions' },
      { text: 'Filter by type, date, or search to find specific minutes quickly' },
      { text: 'Use the Trust Assistant to draft minutes from a natural language description' },
    ],
    taPrompt: 'Help me understand the Minutes page and how to create trust meeting minutes',
  },
  Distributions: {
    items: [
      { text: 'Record and manage all distributions to trust beneficiaries' },
      { text: 'Track distribution amounts, purposes, and approval status' },
      { text: 'Send beneficiary notices and attach supporting minutes' },
    ],
    taPrompt: 'Walk me through the Distributions page and how to record a distribution',
  },
  Expenses: {
    items: [
      { text: 'Track and manage trust-related expenses and payments' },
      { text: 'Categorize spending and maintain accurate financial records' },
      { text: 'Attach receipts and documentation to each expense' },
    ],
    taPrompt: 'Help me understand the Expenses page and how to add an expense',
  },
  Calendar: {
    items: [
      { text: 'Schedule and track trust compliance tasks, meetings, and deadlines' },
      { text: 'View upcoming fiduciary obligations at a glance' },
      { text: 'Mark tasks complete and stay on top of your governance calendar' },
    ],
    taPrompt: 'Walk me through the Governance Calendar and how to manage compliance tasks',
  },
  Compensation: {
    items: [
      { text: 'Set up and manage trustee compensation plans and payment schedules' },
      { text: 'Track payments, document approvals, and maintain compliance' },
      { text: 'View compensation history per trustee' },
    ],
    taPrompt: 'Help me understand the Compensation page and how to set up trustee pay',
  },
  Governance: {
    items: [
      { text: 'Assess trust health across 7 criteria including defensibility and compliance' },
      { text: 'Track your trust\'s overall governance quality score' },
      { text: 'Identify areas that need attention to improve your trust health' },
    ],
    taPrompt: 'Walk me through the Trust Health page and how to interpret my scores',
  },
  Structures: {
    items: [
      { text: 'Manage trust structures, entities, and their relationships' },
      { text: 'Define the organizational framework of your trust' },
      { text: 'Add entities like LLCs, partnerships, or other trusts' },
    ],
    taPrompt: 'Help me understand the Structures page and how to add an entity',
  },
  Settings: {
    items: [
      { text: 'Configure trust settings, preferences, and account details' },
      { text: 'Manage notifications, security, and trust profile information' },
      { text: 'Update your personal and billing information' },
    ],
    taPrompt: 'Walk me through the Settings page and what I can configure',
  },
  Billing: {
    items: [
      { text: 'Manage your subscription plan, billing history, and payment methods' },
      { text: 'Upgrade, downgrade, or cancel your plan at any time' },
      { text: 'View invoices and payment receipts' },
    ],
    taPrompt: 'Help me understand the Billing page and my subscription options',
  },
  Benevolence: {
    items: [
      { text: 'Manage benevolence requests and charitable distributions' },
      { text: 'Review, approve, and document giving decisions' },
      { text: 'Track charitable giving against trust purposes' },
    ],
    taPrompt: 'Walk me through the Benevolence page and how to approve a request',
  },
  Vault: {
    items: [
      { text: 'Store, organize, and access all trust documents in one place' },
      { text: 'Upload files, manage categories, and control access' },
      { text: 'Share documents with beneficiaries and advisors securely' },
    ],
    taPrompt: 'Help me understand the Document Vault and how to upload files',
  },
  RiskDashboard: {
    items: [
      { text: 'Monitor trust risks, compliance gaps, and alerts across all modules' },
      { text: 'Review flagged items and take corrective action' },
      { text: 'Track high, medium, and low risk items by category' },
    ],
    taPrompt: 'Walk me through the Risk Dashboard and how to address flagged risks',
  },
  TaxCalendar: {
    items: [
      { text: 'Track tax deadlines, filing dates, and compliance events' },
      { text: 'Never miss a trust tax obligation with automated reminders' },
      { text: 'View deadlines by fiscal year and trust type' },
    ],
    taPrompt: 'Help me understand the Tax Calendar and upcoming deadlines',
  },
  Communications: {
    items: [
      { text: 'Record and track all beneficiary communications in one place' },
      { text: 'Document calls, emails, and notices to satisfy UTC § 813 requirements' },
      { text: 'Maintain a complete history of beneficiary contact' },
    ],
    taPrompt: 'Walk me through the Communication Log and how to log a beneficiary contact',
  },
  Investments: {
    items: [
      { text: 'Manage trust investments and track portfolio performance' },
      { text: 'Document investment decisions for fiduciary compliance' },
      { text: 'View holdings, returns, and allocation at a glance' },
    ],
    taPrompt: 'Help me understand the Investment Holdings page and how to add an investment',
  },
  StateCompliance: {
    items: [
      { text: 'Review state-specific trust requirements for your jurisdiction' },
      { text: 'Check UTC adoption status, fiduciary standards, and notification rules' },
      { text: 'Ensure your trust administration complies with local law' },
    ],
    taPrompt: 'Walk me through the State Compliance page for my state',
  },
  Authority: {
    items: [
      { text: 'Define and manage trustee authorities and signing powers' },
      { text: 'Delegate duties and document who can act on behalf of the trust' },
      { text: 'Maintain a clear record of authorized decision-makers' },
    ],
    taPrompt: 'Help me understand the Authority Management page',
  },
  AuditTrail: {
    items: [
      { text: 'View a complete log of all trust administration actions' },
      { text: 'Track changes, access, and decisions for compliance and transparency' },
      { text: 'Export audit logs for review or regulatory purposes' },
    ],
    taPrompt: 'Walk me through the Audit Trail and what gets logged',
  },
  TransactionLedger: {
    items: [
      { text: 'View and manage all trust financial transactions in one ledger' },
      { text: 'Track income, expenses, and transfers across accounts' },
      { text: 'Import CSV files and reconcile with bank statements' },
    ],
    taPrompt: 'Help me understand the Transaction Ledger and how to add a transaction',
  },
  ScheduleA: {
    items: [
      { text: 'Manage trust assets and corpus — the initial and current property of the trust' },
      { text: 'Add, update, or dispose of trust assets with proper documentation' },
      { text: 'Track asset values, dates, and disposition history' },
    ],
    taPrompt: 'Walk me through the Schedule A page and how to add an asset',
  },
  Beneficiaries: {
    items: [
      { text: 'Manage trust beneficiaries, ownership interests, and class designations' },
      { text: 'Add, update, or remove beneficiaries with proper documentation' },
      { text: 'View beneficiary certificates and allocation percentages' },
    ],
    taPrompt: 'Help me understand the Beneficiaries page and how to add a beneficiary',
  },
  BenevolenceLog: {
    items: [
      { text: 'Track charitable giving and benevolence distributions' },
      { text: 'Document donations, recipients, and alignment with trust purposes' },
      { text: 'View giving history and totals over time' },
    ],
    taPrompt: 'Walk me through the Benevolence Log page',
  },
  EntityDetail: {
    items: [
      { text: 'View and manage entity details including type, status, and relationships' },
      { text: 'Update entity information and track changes over time' },
      { text: 'Maintain accurate records of all trust-related entities' },
    ],
    taPrompt: 'Help me understand the Entity Detail page',
  },
  TrustAssistant: {
    items: [
      { text: 'Ask questions about trust administration in plain language' },
      { text: 'Draft minutes, manage distributions, and execute trust actions' },
      { text: 'Get guidance on fiduciary duties, deadlines, and best practices' },
    ],
    taPrompt: 'What can I ask you to help me with?',
  },
  Stats: {
    items: [
      { text: 'View revenue metrics, subscription analytics, and business performance' },
      { text: 'Track MRR, ARR, paid customers, and revenue trends over time' },
      { text: 'Filter by date range to analyze specific periods' },
    ],
    taPrompt: 'Walk me through the Stats dashboard',
  },
  Admin: {
    items: [
      { text: 'Manage customers, subscriptions, and system administration' },
      { text: 'View and manage leads, extend trials, and gift subscriptions' },
      { text: 'Access revenue data and customer details' },
    ],
    taPrompt: 'Walk me through the Admin panel',
  },
};

export default PAGE_HELP;
