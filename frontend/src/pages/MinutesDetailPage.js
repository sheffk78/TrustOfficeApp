import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { fetchWithAuth } from '@/utils/api';
import { toast } from 'sonner';
import PDFPreviewModal from '@/components/PDFPreviewModal';
import { format, parseISO } from 'date-fns';
import { 
  ArrowLeft, 
  FileText, 
  Calendar, 
  Users, 
  Save,
  Download,
  Eye,
  Pencil,
  Clock,
  UserCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Sparkles,
  FilePenLine
} from 'lucide-react';

export default function MinutesDetailPage() {
  const { minutesId } = useParams();
  const navigate = useNavigate();
  const { selectedTrust } = useAuth();
  
  const [minutes, setMinutes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  
  // Editable fields
  const [editedText, setEditedText] = useState('');
  const [editedParticipants, setEditedParticipants] = useState('');
  const [editedOtherAttendees, setEditedOtherAttendees] = useState('');
  
  // PDF Preview
  const [pdfPreview, setPdfPreview] = useState({ show: false, loading: false, data: null, filename: '' });

  // Collapsible sections state
  const [collapsedSections, setCollapsedSections] = useState({});

  const toggleSection = (index) => {
    setCollapsedSections(prev => ({ ...prev, [index]: !prev[index] }));
  };

  const loadMinutes = useCallback(async () => {
    if (!minutesId) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/minutes/${minutesId}`);
      if (response.ok) {
        const data = await response.json();
        setMinutes(data);
        setEditedText(data.decisions_text || '');
        setEditedParticipants(data.participants_text || '');
        setEditedOtherAttendees(data.other_attendees_text || '');
      } else {
        toast.error('Failed to load minutes');
        navigate('/minutes');
      }
    } catch (error) {
      console.error('Failed to load minutes:', error);
      toast.error('Failed to load minutes');
    } finally {
      setLoading(false);
    }
  }, [minutesId, navigate]);

  useEffect(() => {
    loadMinutes();
  }, [loadMinutes]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetchWithAuth(`/minutes/${minutesId}`, {
        method: 'PUT',
        body: JSON.stringify({
          decisions_text: editedText,
          participants_text: editedParticipants,
          other_attendees_text: editedOtherAttendees
        })
      });
      
      if (response.ok) {
        toast.success('Minutes updated successfully');
        setIsEditing(false);
        loadMinutes();
      } else {
        toast.error('Failed to save changes');
      }
    } catch (error) {
      toast.error('Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleViewPDF = async () => {
    setPdfPreview({ show: true, loading: true, data: null, filename: '' });
    try {
      const response = await fetchWithAuth(`/minutes/${minutesId}/pdf`);
      if (response.ok) {
        const data = await response.json();
        setPdfPreview({ show: true, loading: false, data: data.pdf_base64, filename: data.filename });
      } else {
        toast.error('Failed to generate PDF');
        setPdfPreview({ show: false, loading: false, data: null, filename: '' });
      }
    } catch (error) {
      toast.error('Failed to generate PDF');
      setPdfPreview({ show: false, loading: false, data: null, filename: '' });
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return format(parseISO(dateStr), 'MMMM d, yyyy');
    } catch {
      return dateStr;
    }
  };

  const formatDateTime = (dateStr) => {
    if (!dateStr) return '—';
    try {
      return format(parseISO(dateStr), 'MMM d, yyyy h:mm a');
    } catch {
      return dateStr;
    }
  };

  // Helper: format template_type for display
  const formatTemplateType = (templateType) => {
    if (!templateType) return null;
    return templateType.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8 flex items-center justify-center">
            <div className="w-8 h-8 border-2 border-navy dark:border-gold border-t-transparent animate-spin"></div>
          </div>
        </main>
      </div>
    );
  }

  if (!minutes) {
    return (
      <div className="min-h-screen bg-background">
        <Sidebar />
        <main className="lg:pl-64 pt-16 lg:pt-0">
          <div className="p-8">
            <div className="card-trust p-8 text-center">
              <p className="text-muted-foreground">Minutes not found</p>
              <Button onClick={() => navigate('/minutes')} className="mt-4">
                <ArrowLeft className="w-4 h-4 mr-2" /> Back to Minutes
              </Button>
            </div>
          </div>
        </main>
      </div>
    );
  }

  const hasSections = Array.isArray(minutes.sections) && minutes.sections.length > 0;
  const isRetroactive = minutes.is_retroactive === true;
  const isAiGenerated = minutes.source === 'ai_generated';
  const isDraft = minutes.status === 'draft';

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <main className="lg:pl-64 pt-16 lg:pt-0">
        <div className="p-4 lg:p-8 max-w-5xl">

          {/* Retroactive Banner */}
          {isRetroactive && (
            <div className="mb-6 p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-lg flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 mt-0.5 shrink-0" />
              <div className="text-sm text-amber-800 dark:text-amber-200">
                <p className="font-semibold">Retroactive Minutes</p>
                <p className="mt-1">
                  Created {formatDateTime(minutes.created_at)} for meeting on {formatDate(minutes.meeting_date)}.
                  {minutes.retroactive_reason && (
                    <span className="block mt-1 italic">Reason: {minutes.retroactive_reason}</span>
                  )}
                </p>
              </div>
            </div>
          )}

          {/* Header */}
          <div className="flex items-center gap-4 mb-6">
            <Button variant="ghost" onClick={() => navigate('/minutes')} className="p-2">
              <ArrowLeft className="w-5 h-5" />
            </Button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="font-serif text-2xl lg:text-3xl text-navy dark:text-gold">
                  {minutes.minutes_type?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())} Minutes
                </h1>
                {/* Template Type Badge */}
                {minutes.template_type && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-navy/10 dark:bg-gold/10 text-navy dark:text-gold text-xs font-mono rounded-full border border-navy/20 dark:border-gold/20">
                    <FilePenLine className="w-3 h-3" />
                    {formatTemplateType(minutes.template_type)}
                  </span>
                )}
                {/* AI Generated Badge */}
                {isAiGenerated && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 text-xs font-mono rounded-full border border-purple-200 dark:border-purple-700">
                    <Sparkles className="w-3 h-3" />
                    AI Generated
                  </span>
                )}
                {/* Draft Badge */}
                {isDraft && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300 text-xs font-mono rounded-full border border-red-300 dark:border-red-700 font-semibold uppercase tracking-wider">
                    Draft
                  </span>
                )}
              </div>
              <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground mt-1">
                {selectedTrust?.name} • {isRetroactive ? `Meeting: ${formatDate(minutes.meeting_date)}` : formatDate(minutes.meeting_date)}
              </p>
            </div>
            <div className="flex gap-2">
              {!isEditing ? (
                <>
                  <Button variant="outline" onClick={() => setIsEditing(true)} data-testid="edit-minutes-btn">
                    <Pencil className="w-4 h-4 mr-2" />
                    Edit
                  </Button>
                  <Button variant="outline" onClick={handleViewPDF} data-testid="view-pdf-btn">
                    <Eye className="w-4 h-4 mr-2" />
                    View PDF
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={() => { setIsEditing(false); setEditedText(minutes.decisions_text || ''); }}>
                    Cancel
                  </Button>
                  <Button className="btn-primary" onClick={handleSave} disabled={saving} data-testid="save-minutes-btn">
                    <Save className="w-4 h-4 mr-2" />
                    {saving ? 'Saving...' : 'Save Changes'}
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Meeting Info Card */}
          <div className="card-trust p-6 mb-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div className="flex items-start gap-3">
                <Calendar className="w-5 h-5 text-navy dark:text-gold mt-0.5" />
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Meeting Date</p>
                  <p className="font-medium">{formatDate(minutes.meeting_date)}</p>
                </div>
              </div>
              
              <div className="flex items-start gap-3">
                <FileText className="w-5 h-5 text-navy dark:text-gold mt-0.5" />
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">Type</p>
                  <p className="font-medium capitalize">{minutes.minutes_type?.replace(/_/g, ' ')}</p>
                </div>
              </div>
              
              <div className="flex items-start gap-3">
                <Clock className="w-5 h-5 text-navy dark:text-gold mt-0.5" />
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    {isRetroactive ? 'Date Created' : 'Created'}
                  </p>
                  <p className="font-medium">{formatDateTime(minutes.created_at)}</p>
                  {isRetroactive && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                      After meeting date
                    </p>
                  )}
                </div>
              </div>
              
              {/* Show meeting date distinctly for retroactive records */}
              {isRetroactive && (
                <div className="flex items-start gap-3">
                  <Calendar className="w-5 h-5 text-amber-500 mt-0.5" />
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-widest text-amber-600 dark:text-amber-400">Meeting Date</p>
                    <p className="font-medium">{formatDate(minutes.meeting_date)}</p>
                    <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                      Before creation date
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Participants Section */}
          <div className="card-trust p-6 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Users className="w-4 h-4 text-navy dark:text-gold" />
              <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Participants</h2>
            </div>
            
            {isEditing ? (
              <div className="space-y-4">
                <div>
                  <Label className="label-trust">Trustees Present</Label>
                  <Input
                    value={editedParticipants}
                    onChange={(e) => setEditedParticipants(e.target.value)}
                    placeholder="John Smith, Jane Doe"
                    className="mt-1"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Comma-separated list of trustees</p>
                </div>
                <div>
                  <Label className="label-trust">Other Attendees</Label>
                  <Input
                    value={editedOtherAttendees}
                    onChange={(e) => setEditedOtherAttendees(e.target.value)}
                    placeholder="Bob Wilson (Attorney), Mary Smith (CPA)"
                    className="mt-1"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Comma-separated list of other attendees (guests, advisors, etc.)</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Trustees */}
                <div>
                  <p className="text-xs font-mono uppercase tracking-widest text-navy/50 dark:text-white/50 mb-2">Trustees Present</p>
                  <div className="flex flex-wrap gap-2">
                    {minutes.participants_text?.split(',').filter(p => p.trim()).map((p, i) => (
                      <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-navy/5 dark:bg-gold/5 border border-navy/10 dark:border-gold/10">
                        <UserCircle className="w-4 h-4 text-navy dark:text-gold" />
                        <span className="text-sm">{p.trim()}</span>
                        <span className="text-xs text-muted-foreground">(Trustee)</span>
                      </div>
                    ))}
                    {!minutes.participants_text && (
                      <p className="text-sm text-muted-foreground italic">No trustees listed</p>
                    )}
                  </div>
                </div>
                
                {/* Other Attendees */}
                {minutes.other_attendees_text && (
                  <div>
                    <p className="text-xs font-mono uppercase tracking-widest text-navy/50 dark:text-white/50 mb-2">Also Present</p>
                    <div className="flex flex-wrap gap-2">
                      {minutes.other_attendees_text.split(',').filter(p => p.trim()).map((p, i) => (
                        <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-muted/50 border border-border">
                          <UserCircle className="w-4 h-4 text-muted-foreground" />
                          <span className="text-sm">{p.trim()}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Sections Display (collapsible) */}
          {hasSections && !isEditing && (
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-4">
                <FileText className="w-4 h-4 text-navy dark:text-gold" />
                <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">Sections</h2>
              </div>
              <div className="space-y-3">
                {minutes.sections.map((section, index) => {
                  const isCollapsed = collapsedSections[index] !== false; // default expanded
                  const sectionTitle = section.title || section.template_type
                    ? formatTemplateType(section.template_type || section.title)
                    : `Section ${index + 1}`;
                  return (
                    <div key={index} className="card-trust overflow-hidden">
                      <button
                        onClick={() => toggleSection(index)}
                        className="w-full flex items-center gap-3 p-4 hover:bg-navy/5 dark:hover:bg-gold/5 transition-colors text-left"
                      >
                        {isCollapsed ? (
                          <ChevronRight className="w-4 h-4 text-navy dark:text-gold shrink-0" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-navy dark:text-gold shrink-0" />
                        )}
                        <span className="font-semibold text-sm text-navy dark:text-gold flex-1">
                          {sectionTitle}
                        </span>
                        {section.template_type && (
                          <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground bg-muted px-2 py-0.5 rounded">
                            {formatTemplateType(section.template_type)}
                          </span>
                        )}
                      </button>
                      {!isCollapsed && (
                        <div className="px-4 pb-4 pt-0">
                          <pre className="whitespace-pre-wrap font-mono text-sm bg-muted/30 p-4 border border-border rounded overflow-auto max-h-[400px]">
                            {section.content || 'No content for this section.'}
                          </pre>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Minutes Content */}
          <div className="card-trust p-6">
            <div className="flex items-center gap-2 mb-4">
              <FileText className="w-4 h-4 text-navy dark:text-gold" />
              <h2 className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
                {hasSections ? 'Full Minutes Content' : 'Minutes Content'}
              </h2>
            </div>
            
            {isEditing ? (
              <Textarea
                value={editedText}
                onChange={(e) => setEditedText(e.target.value)}
                className="min-h-[500px] font-mono text-sm"
                placeholder="Meeting minutes content..."
                data-testid="minutes-content-textarea"
              />
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none">
                <pre className="whitespace-pre-wrap font-mono text-sm bg-muted/30 p-6 border border-border overflow-auto max-h-[600px]">
                  {minutes.decisions_text || 'No content recorded.'}
                </pre>
              </div>
            )}
          </div>
        </div>
      </main>
      <MobileBottomNav />

      {/* PDF Preview Modal */}
      <PDFPreviewModal
        show={pdfPreview.show}
        onClose={() => setPdfPreview({ show: false, loading: false, data: null, filename: '' })}
        loading={pdfPreview.loading}
        pdfBase64={pdfPreview.data}
        filename={pdfPreview.filename}
      />
    </div>
  );
}