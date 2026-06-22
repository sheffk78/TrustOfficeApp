import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { fetchWithAuth } from '@/utils/api';
import {
  Shield,
  UserCheck,
  AlertTriangle,
  ChevronRight,
  Users,
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import PageHelpButton from '@/components/PageHelpButton';

const ROLE_COLORS = {
  Trustee: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  Grantor: { bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200' },
  Protector: { bg: 'bg-warning/5', text: 'text-warning', border: 'border-warning/20' },
  Beneficiary: { bg: 'bg-success/5', text: 'text-success', border: 'border-success/20' },
  Manager: { bg: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200' },
  'Successor Trustee': { bg: 'bg-cyan-50', text: 'text-cyan-700', border: 'border-cyan-200' },
};

const AUTHORITY_LEVELS = {
  full: { label: 'Full Authority', color: 'text-success', icon: CheckCircle2 },
  limited: { label: 'Limited Authority', color: 'text-warning', icon: AlertTriangle },
  none: { label: 'No Authority', color: 'text-red-500', icon: XCircle },
};

export default function AuthorityPage() {
  const { selectedTrust } = useAuth();
  const [entities, setEntities] = useState([]);
  const [relationships, setRelationships] = useState([]);
  const [trustData, setTrustData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedEntity, setSelectedEntity] = useState(null);

  useEffect(() => {
    if (selectedTrust) loadData();
  }, [selectedTrust]);

  const loadData = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const [entitiesRes, relsRes, trustRes] = await Promise.all([
        fetchWithAuth(`/entities?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/relationships?trust_id=${selectedTrust.trust_id}`),
        fetchWithAuth(`/trusts/${selectedTrust.trust_id}`),
      ]);
      if (entitiesRes.ok) setEntities((await entitiesRes.json()).entities || []);
      if (relsRes.ok) setRelationships((await relsRes.json()).relationships || []);
      if (trustRes.ok) setTrustData(await trustRes.json());
    } catch (error) {
      console.error('Failed to load authority data:', error);
    } finally {
      setLoading(false);
    }
  };

  const parseNames = (namesStr) => {
    if (!namesStr) return [];
    return namesStr.split(',').map(n => n.trim()).filter(Boolean);
  };

  const getAuthorityPeople = () => {
    const people = [];

    // From trust-level data
    if (trustData) {
      if (trustData.trustees) {
        parseNames(trustData.trustees).forEach(name => {
          people.push({
            name,
            role: 'Trustee',
            source: trustData.name,
            authority: 'full',
            authorityClause: trustData.authority_clause || null,
          });
        });
      }
      if (trustData.grantor_name) {
        people.push({
          name: trustData.grantor_name,
          role: 'Grantor',
          source: trustData.name,
          authority: trustData.trust_type === 'revocable' ? 'full' : 'limited',
          authorityClause: null,
        });
      }
    }

    // From entity-level data
    entities.forEach(entity => {
      parseNames(entity.trustee_names).forEach(name => {
        if (!people.find(p => p.name === name && p.role === 'Trustee')) {
          people.push({
            name,
            role: 'Trustee',
            source: entity.name,
            authority: 'full',
            authorityClause: entity.article_ref_compensation || null,
          });
        }
      });
      parseNames(entity.manager_names).forEach(name => {
        people.push({
          name,
          role: 'Manager',
          source: entity.name,
          authority: 'limited',
          authorityClause: entity.article_ref_compensation || null,
        });
      });
      parseNames(entity.member_names).forEach(name => {
        people.push({
          name,
          role: 'Member',
          source: entity.name,
          authority: 'limited',
          authorityClause: entity.article_ref_distribution || null,
        });
      });
    });

    return people;
  };

  const people = getAuthorityPeople();

  const getRoleColor = (role) => ROLE_COLORS[role] || ROLE_COLORS['Manager'];

  const getAuthorityInfo = (level) => AUTHORITY_LEVELS[level] || AUTHORITY_LEVELS['none'];

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!selectedTrust) {
    return (
      <div className="flex items-center justify-center min-h-screen text-muted-foreground">
        Select a trust to view authority management
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        <div className="max-w-6xl mx-auto space-y-6">
          {/* Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Authority Management</h1>
              <p className="page-subtitle">Define and manage trustee authorities, signing powers, and delegation of duties</p>
            </div>
            <div className="flex items-center gap-2">
              <PageHelpButton
                items={[
                  { text: 'Define and manage trustee authorities and signing powers' },
                  { text: 'Delegate duties and document who can act on behalf of the trust' },
                  { text: 'Maintain a clear record of authorized decision-makers' },
                ]}
                taPrompt="Help me understand the Authority Management page"
              />
              <Button variant="outline" size="sm" onClick={loadData}>
                <RefreshCw className="w-4 h-4 mr-1" /> Refresh
              </Button>
            </div>
          </div>

          {/* Authority Clause */}
          {trustData?.authority_clause && (
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-3 flex items-center gap-2">
                <FileText className="w-5 h-5" /> Governing Authority Clause
              </h2>
              <div className="bg-slate-50 rounded p-4 text-sm leading-relaxed border border-slate-200">
                {trustData.authority_clause}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Source: {trustData.name} Trust Agreement
              </p>
            </div>
          )}

          {/* Authority Grid */}
          {people.length === 0 ? (
            <div className="card-trust text-center py-12">
              <Users className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="font-serif text-lg text-navy mb-2">No Authority Records</h3>
              <p className="text-sm text-muted-foreground">
                Add trustees, managers, and members to your entities to see authority relationships here.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {people.map((person, idx) => {
                const roleColor = getRoleColor(person.role);
                const authInfo = getAuthorityInfo(person.authority);
                const AuthIcon = authInfo.icon;
                const isSelected = selectedEntity === idx;

                return (
                  <div
                    key={`${person.name}-${person.role}-${idx}`}
                    className={`card-trust cursor-pointer transition-all hover:shadow-md ${isSelected ? 'ring-2 ring-navy' : ''}`}
                    onClick={() => setSelectedEntity(isSelected ? null : idx)}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-8 h-8 rounded-full ${roleColor.bg} ${roleColor.border} border flex items-center justify-center`}>
                          <UserCheck className={`w-4 h-4 ${roleColor.text}`} />
                        </div>
                        <div>
                          <p className="font-semibold text-navy text-sm">{person.name}</p>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${roleColor.bg} ${roleColor.text} ${roleColor.border} border`}>
                            {person.role}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <AuthIcon className={`w-4 h-4 ${authInfo.color}`} />
                        <span className={`text-xs font-medium ${authInfo.color}`}>
                          {authInfo.label}
                        </span>
                      </div>
                    </div>

                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Source Entity</span>
                        <span className="font-medium text-navy">{person.source}</span>
                      </div>

                      {person.authorityClause && isSelected && (
                        <div className="mt-3 pt-3 border-t border-slate-100">
                          <p className="text-muted-foreground mb-1">Authority Reference</p>
                          <p className="text-navy text-xs leading-relaxed bg-slate-50 rounded p-2">
                            {person.authorityClause}
                          </p>
                        </div>
                      )}
                    </div>

                    {isSelected && (
                      <div className="mt-3 pt-2 border-t border-slate-100">
                        <p className="text-[10px] text-muted-foreground">
                          Tap to collapse • Article references available in entity settings
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Authority by Entity */}
          {entities.length > 0 && (
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
                <Clock className="w-5 h-5" /> Authority by Entity
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200">
                      <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Entity</th>
                      <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Type</th>
                      <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Trustees/Managers</th>
                      <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Authority Scope</th>
                    </tr>
                  </thead>
                  <tbody>
                    {entities.map(entity => {
                      const trusteeList = parseNames(entity.trustee_names);
                      const managerList = parseNames(entity.manager_names);
                      const allPeople = [...trusteeList, ...managerList];

                      return (
                        <tr key={entity.entity_id} className="border-b border-slate-50 hover:bg-slate-50">
                          <td className="py-2 px-3 font-medium text-navy">{entity.name}</td>
                          <td className="py-2 px-3">
                            <span className="text-xs font-mono text-muted-foreground">{entity.entity_type}</span>
                          </td>
                          <td className="py-2 px-3">
                            {allPeople.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {allPeople.map((name, i) => (
                                  <span key={i} className="text-xs bg-slate-100 px-1.5 py-0.5 rounded">
                                    {name}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground italic">None assigned</span>
                            )}
                          </td>
                          <td className="py-2 px-3">
                            {entity.article_ref_compensation ? (
                              <span className="text-xs text-success">Defined</span>
                            ) : (
                              <span className="text-xs text-warning">Not specified</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Relationships */}
          {relationships.length > 0 && (
            <div className="card-trust">
              <h2 className="font-serif text-lg text-navy mb-4 flex items-center gap-2">
                <ChevronRight className="w-5 h-5" /> Authority Relationships
              </h2>
              <div className="space-y-2">
                {relationships.map((rel, idx) => (
                  <div key={idx} className="flex items-center gap-3 py-2 px-3 bg-slate-50 rounded text-sm">
                    <span className="font-medium text-navy">{rel.parent_entity_id}</span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-medium">
                      {rel.relationship_type.replace(/_/g, ' ')}
                      {rel.ownership_percentage && ` (${rel.ownership_percentage}%)`}
                    </span>
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    <span className="font-medium text-navy">{rel.child_entity_id}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />
    </div>
  );
}