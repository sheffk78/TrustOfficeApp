import { Landmark, Building2, Building } from 'lucide-react';

export const ENTITY_TYPES = [
  { value: 'Trust', label: 'Trust', icon: Landmark },
  { value: 'Holding LLC', label: 'Holding LLC', icon: Building2 },
  { value: 'Operating LLC', label: 'Operating LLC', icon: Building },
];

export const RELATIONSHIP_TYPES = [
  { value: 'owns', label: 'Owns' },
  { value: 'controls', label: 'Controls' },
  { value: 'receives_distributions_from', label: 'Receives Distributions From' },
  { value: 'pays_compensation_to', label: 'Pays Compensation To' },
];