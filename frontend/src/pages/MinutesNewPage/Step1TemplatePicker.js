import { Badge } from '@/components/ui/badge';
import {
  Calendar,
  Users,
  FileText,
  Building2,
  Home,
  DollarSign,
  Wallet,
  HeartHandshake,
  Scale,
  Settings,
  UserPlus,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Handshake
} from 'lucide-react';
import { useState } from 'react';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';

// Quick Minutes card data
const QUICK_MINUTES = [
  {
    value: 'annual_review',
    label: 'Annual Review',
    description: 'Year-end review and planning',
    icon: Calendar
  },
  {
    value: 'quarterly_review',
    label: 'Quarterly Review',
    description: 'Regular quarterly review',
    icon: Calendar
  },
  {
    value: 'general_meeting',
    label: 'General Meeting',
    description: 'Ad-hoc or special meeting',
    icon: Users
  }
];

// Specific Action categories
const SPECIFIC_CATEGORIES = [
  {
    name: 'Trustee Changes',
    items: [
      { value: 'appointment_additional_trustee', label: 'Appoint Additional Trustee', icon: UserPlus },
      { value: 'appointment_successor_trustee', label: 'Appoint Successor Trustee', icon: UserPlus },
      { value: 'trustee_resignation', label: 'Trustee Resignation / Removal', icon: UserPlus },
      { value: 'trustee_compensation', label: 'Trustee Compensation', icon: DollarSign }
    ]
  },
  {
    name: 'Property & Assets',
    items: [
      { value: 'acceptance_of_property', label: 'Accept Property into Trust', icon: Home },
      { value: 'disposition_of_asset', label: 'Dispose / Sell Asset', icon: Home },
      { value: 'real_estate_purchase', label: 'Real Estate Purchase', icon: Building2 },
      { value: 'real_estate_lease', label: 'Real Estate Lease', icon: Building2 }
    ]
  },
  {
    name: 'Financial',
    items: [
      { value: 'bank_account_authorization', label: 'Open Bank Account', icon: Wallet },
      { value: 'investment_policy', label: 'Investment Policy', icon: DollarSign },
      { value: 'loan_authorization', label: 'Loan Authorization', icon: DollarSign },
      { value: 'insurance_authorization', label: 'Insurance Authorization', icon: Wallet }
    ]
  },
  {
    name: 'Distributions',
    items: [
      { value: 'distribution_to_beneficiaries', label: 'Distribution to Beneficiaries', icon: DollarSign },
      { value: 'hems_distribution', label: 'HEMS Distribution', icon: DollarSign },
      { value: 'beneficiary_loan', label: 'Loan to Beneficiary', icon: DollarSign },
      { value: 'beneficiary_request_denial', label: 'Beneficiary Request Denial', icon: FileText }
    ]
  },
  {
    name: 'Legal & Governance',
    items: [
      { value: 'trust_amendment', label: 'Trust Amendment', icon: Scale },
      { value: 'change_of_situs', label: 'Change Trust Situs', icon: Scale },
      { value: 'power_of_attorney', label: 'Power of Attorney', icon: Scale },
      { value: 'trust_termination', label: 'Trust Termination', icon: Scale },
      { value: 'conflict_of_interest', label: 'Conflict of Interest', icon: Scale },
      { value: 'emergency_ratification', label: 'Emergency Ratification', icon: Scale }
    ]
  },
  {
    name: 'Admin',
    items: [
      { value: 'fiscal_year_election', label: 'Fiscal Year Election', icon: Settings },
      { value: 'tax_filing_authorization', label: 'Tax Filing Authorization', icon: Settings },
      { value: 'business_interest_acquisition', label: 'Business Interest Acquisition', icon: Settings }
    ]
  },
  {
    name: 'Beneficiaries',
    items: [
      { value: 'designation_of_beneficiaries', label: 'Designate Beneficiaries', icon: Users },
      { value: 'initial_trustee_meeting', label: 'Initial Trustee Meeting', icon: Users }
    ]
  },
  {
    name: 'Benevolence',
    items: [
      { value: 'benevolence_approval', label: 'Benevolence Approval', icon: HeartHandshake }
    ]
  }
];

/**
 * Step 1: Template Picker
 *
 * Props:
 *   selectedTemplate — currently selected template value
 *   onSelect         — (templateValue) => void
 *   hasExistingMinutes — boolean, if false shows "First Meeting" card
 *   templateOptions  — array from API (optional, merges with static data)
 */
export default function Step1TemplatePicker({ selectedTemplate, onSelect, hasExistingMinutes = true, templateOptions = [] }) {
  const [openCategories, setOpenCategories] = useState({});

  // Merge API template options into categories if provided
  const mergedCategories = SPECIFIC_CATEGORIES.map(cat => {
    const apiItems = templateOptions
      .filter(t => t.category === cat.name)
      .map(t => ({
        value: t.value || t.type,
        label: t.label || t.name,
        icon: cat.items[0]?.icon || FileText,
        ...t
      }));
    // If API provides items for this category, prefer them; else use static
    if (apiItems.length > 0) {
      return { ...cat, items: apiItems };
    }
    return cat;
  });

  // Also merge Quick Minutes from API
  const mergedQuickMinutes = templateOptions
    .filter(t => t.category === 'Quick Minutes' || QUICK_MINUTES.some(q => q.value === (t.value || t.type)))
    .length > 0
    ? QUICK_MINUTES.map(q => {
        const apiMatch = templateOptions.find(t => (t.value || t.type) === q.value);
        return apiMatch ? { ...q, label: apiMatch.label || q.label, description: apiMatch.description || q.description } : q;
      })
    : QUICK_MINUTES;

  const toggleCategory = (name) => {
    setOpenCategories(prev => ({ ...prev, [name]: !prev[name] }));
  };

  const handleSelect = (value) => {
    onSelect(value);
  };

  return (
    <div className="space-y-8" data-testid="step1-template-picker">
      {/* First Meeting card (only if trust has 0 minutes) */}
      {!hasExistingMinutes && (
        <div>
          <button
            onClick={() => handleSelect('initial_trustee_meeting')}
            className={`w-full p-5 border text-left transition-all relative ${
              selectedTemplate === 'initial_trustee_meeting'
                ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5 ring-2 ring-navy/20 dark:ring-gold/20'
                : 'border-navy/20 dark:border-white/20 hover:border-navy/40 dark:hover:border-white/40'
            }`}
          >
            <Badge className="absolute top-3 right-3 bg-gold text-navy text-[10px] font-mono">
              Start Here
            </Badge>
            <div className="flex items-center gap-3">
              <Sparkles className="w-6 h-6 text-gold" />
              <div>
                <div className="font-serif text-lg text-navy dark:text-gold">First Meeting</div>
                <div className="text-sm text-muted-foreground mt-0.5">
                  Document the initial trustee meeting to establish your trust
                </div>
              </div>
            </div>
          </button>
        </div>
      )}

      {/* Quick Minutes */}
      <div>
        <h3 className="font-mono text-xs uppercase tracking-widest text-navy/50 dark:text-white/50 mb-4">
          Quick Minutes
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {mergedQuickMinutes.map((type) => {
            const Icon = type.icon;
            const isSelected = selectedTemplate === type.value;
            return (
              <button
                key={type.value}
                onClick={() => handleSelect(type.value)}
                className={`p-4 border text-left transition-all ${
                  isSelected
                    ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5 ring-2 ring-navy/20 dark:ring-gold/20'
                    : 'border-navy/20 dark:border-white/20 hover:border-navy/40 dark:hover:border-white/40'
                }`}
                data-testid={`template-${type.value}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Icon className={`w-4 h-4 ${isSelected ? 'text-navy dark:text-gold' : 'text-muted-foreground'}`} />
                  <span className={`font-serif text-base ${isSelected ? 'text-navy dark:text-gold' : ''}`}>
                    {type.label}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{type.description}</p>
                {isSelected && (
                  <div className="mt-2 text-xs font-mono text-navy dark:text-gold flex items-center gap-1">
                    ✓ Selected
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Specific Actions (collapsible categories) */}
      <div>
        <h3 className="font-mono text-xs uppercase tracking-widest text-navy/50 dark:text-white/50 mb-4">
          Specific Actions
        </h3>
        <div className="space-y-2">
          {mergedCategories.map((cat) => (
            <Collapsible
              key={cat.name}
              open={openCategories[cat.name]}
              onOpenChange={() => toggleCategory(cat.name)}
            >
              <CollapsibleTrigger className="w-full flex items-center justify-between p-3 border border-navy/10 dark:border-white/10 hover:bg-navy/3 dark:hover:bg-white/3 transition-colors text-left">
                <span className="font-serif text-sm text-navy dark:text-gold">{cat.name}</span>
                {openCategories[cat.name] ? (
                  <ChevronDown className="w-4 h-4 text-muted-foreground" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-muted-foreground" />
                )}
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3 border border-t-0 border-navy/10 dark:border-white/10">
                  {cat.items.map((item) => {
                    const Icon = item.icon;
                    const isSelected = selectedTemplate === item.value;
                    return (
                      <button
                        key={item.value}
                        onClick={() => handleSelect(item.value)}
                        className={`p-3 border text-left transition-all ${
                          isSelected
                            ? 'border-navy dark:border-gold bg-navy/5 dark:bg-gold/5 ring-2 ring-navy/20 dark:ring-gold/20'
                            : 'border-navy/10 dark:border-white/10 hover:border-navy/30 dark:hover:border-white/30'
                        }`}
                        data-testid={`template-${item.value}`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <Icon className={`w-3.5 h-3.5 ${isSelected ? 'text-navy dark:text-gold' : 'text-muted-foreground'}`} />
                          <span className={`text-sm font-medium ${isSelected ? 'text-navy dark:text-gold' : ''}`}>
                            {item.label}
                          </span>
                        </div>
                        {isSelected && (
                          <div className="text-xs font-mono text-navy dark:text-gold">✓ Selected</div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </CollapsibleContent>
            </Collapsible>
          ))}
        </div>
      </div>
    </div>
  );
}