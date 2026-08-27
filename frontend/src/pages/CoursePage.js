import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import PageHelpButton from '@/components/PageHelpButton';
import { Button } from '@/components/ui/button';
import { fetchWithAuth, API } from '@/utils/api';
import {
  PlayCircle,
  Lock,
  Download,
  CheckCircle2,
  Clock,
  BookOpen,
  FileText,
  Loader2,
  Sparkles,
} from 'lucide-react';

const BUNNY_LIBRARY_ID = '609821';
const VIDEO_EMBED_BASE = `https://iframe.mediadelivery.net/embed/${BUNNY_LIBRARY_ID}/`;

export default function CoursePage() {
  const { user, subscription } = useAuth();
  const [curriculum, setCurriculum] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedLesson, setSelectedLesson] = useState(null);

  // Course is open to all logged-in users (route is behind ProtectedRoute)
  const isActive = true;

  useEffect(() => {
    fetchCurriculum();
  }, []);

  const fetchCurriculum = async () => {
    try {
      const res = await fetch(`${API}/courses/trustee-101/curriculum`);
      if (!res.ok) throw new Error('Failed to load curriculum');
      const data = await res.json();
      setCurriculum(data);
      // Auto-select first free lesson
      if (data.lessons && data.lessons.length > 0) {
        setSelectedLesson(data.lessons[0]);
      }
    } catch (err) {
      console.error('CoursePage: Failed to load curriculum:', err);
    } finally {
      setLoading(false);
    }
  };

  const canAccessLesson = (lesson) => {
    if (lesson.free) return true;
    return isActive;
  };

  const handleLessonClick = (lesson) => {
    if (!canAccessLesson(lesson)) return;
    setSelectedLesson(lesson);
    logActivity('video_open', `Opened lesson ${lesson.lesson}: ${lesson.title}`);
  };

  // Fire-and-forget report of marketing activity (matches CRM lead by email).
  const logActivity = (action_type, detail) => {
    const email = user?.email;
    if (!email) return;
    try {
      fetch(`/api/admin/leads/activity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, action_type, detail }),
      }).catch(() => {});
    } catch { /* non-blocking */ }
  };

  if (loading) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center min-h-screen lg:ml-64 pt-16 lg:pt-0">
          <Loader2 className="w-8 h-8 animate-spin text-navy" />
        </main>
      </div>
    );
  }

  if (!curriculum) {
    return (
      <div className="flex">
        <Sidebar />
        <main className="flex-1 flex items-center justify-center min-h-screen lg:ml-64 pt-16 lg:pt-0">
          <p className="text-muted-foreground">Unable to load course. Please try again later.</p>
        </main>
      </div>
    );
  }

  const { lessons, course, tagline, free_lessons } = curriculum;
  const completedLessons = lessons.filter((l) => canAccessLesson(l)).length;

  return (
    <div className="flex">
      <Sidebar />
      <main className="flex-1 overflow-y-auto bg-subtle-bg min-h-screen pb-20 md:pb-0 lg:ml-64 pt-16 lg:pt-0">
        <div className="main-content dot-grid mobile-layout-offset">
          <div className="page-container">
            {/* Page Header */}
            <div className="page-header flex items-center justify-between">
              <div>
                <h1 className="page-title">{course}</h1>
                <p className="page-subtitle">{tagline}</p>
              </div>
              <div className="flex flex-wrap gap-3 mt-4 md:mt-0 items-center">
                <PageHelpButton
                  items={[
                    { text: `${course} — a guided video course for trustees (${lessons.length} lessons)` },
                    { text: `Watch lessons in order; ${free_lessons.length} are free and the rest unlock with a subscription` },
                    { text: 'Each lesson includes a downloadable PDF worksheet where noted' },
                  ]}
                  taPrompt={`Walk me through the ${course} course page and how to watch the lessons`}
                />
              </div>
            </div>

            {/* Course stats */}
            <div className="flex flex-wrap items-center gap-4 mb-6 text-sm">
              <span className="flex items-center gap-1.5 text-navy">
                <CheckCircle2 className="w-4 h-4 text-gold" />
                {lessons.length} lessons
              </span>
              <span className="flex items-center gap-1.5 text-navy">
                <Sparkles className="w-4 h-4 text-gold" />
                {free_lessons.length} free
              </span>
              <span className="flex items-center gap-1.5 text-navy">
                <CheckCircle2 className="w-4 h-4 text-gold" />
                {completedLessons} unlocked
              </span>
            </div>

            {/* Video Player + Lesson Detail */}
            {selectedLesson && (
              <div className="mb-8">
                <div className="card-trust overflow-hidden">
                  {/* Video Player */}
                  <div className="relative w-full" style={{ paddingTop: '56.25%' }}>
                    <iframe
                      src={`${VIDEO_EMBED_BASE}${selectedLesson.video_guid}?autoplay=false&loop=false&muted=false&preload=true&responsive=true`}
                      className="absolute inset-0 w-full h-full"
                      allow="accelerometer; gyroscope; autoplay; encrypted-media; picture-in-picture"
                      allowFullScreen
                      loading="lazy"
                      title={selectedLesson.title}
                    />
                  </div>

                  {/* Lesson Info Bar */}
                  <div className="p-5 md:p-6 border-t border-navy/20">
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs font-mono uppercase tracking-widest text-gold">
                            Lesson {selectedLesson.lesson}
                          </span>
                          {selectedLesson.free ? (
                            <span className="text-xs font-mono uppercase tracking-wider bg-success/10 text-success px-2 py-0.5">
                              Free
                            </span>
                          ) : (
                            <span className="text-xs font-mono uppercase tracking-wider bg-gold/20 text-gold px-2 py-0.5">
                              Subscriber
                            </span>
                          )}
                        </div>
                        <h2 className="font-serif text-xl text-navy mb-1">{selectedLesson.title}</h2>
                        <div className="flex items-center gap-3 text-sm text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" />
                            {selectedLesson.duration}
                          </span>
                          {selectedLesson.pdf_url && (
                            <a
                              href={`https://trustoffice.app${selectedLesson.pdf_url}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={() => logActivity('pdf_download', `Downloaded PDF: ${selectedLesson.title}`)}
                              className="flex items-center gap-1 text-navy hover:text-navy/70 transition-colors"
                            >
                              <Download className="w-3.5 h-3.5" />
                              Download PDF
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>


              </div>
            )}

            {/* Lesson List */}
            <div className="mb-4">
              <h3 className="font-serif text-lg text-navy mb-4">All Lessons</h3>
              <div className="space-y-2">
                {lessons.map((lesson) => {
                  const accessible = canAccessLesson(lesson);
                  const isSelected = selectedLesson?.lesson === lesson.lesson;
                  return (
                    <Button
                      key={lesson.lesson}
                      variant="ghost"
                      onClick={() => handleLessonClick(lesson)}
                      disabled={!accessible}
                      className={`w-full text-left p-4 flex items-center gap-4 transition-all border justify-start h-auto font-normal normal-case tracking-normal ${
                        isSelected
                          ? 'border-gold bg-gold/5'
                          : accessible
                          ? 'border-navy/20 bg-white hover:border-navy/30 hover:bg-navy/5'
                          : 'border-navy/20 bg-slate-50 cursor-not-allowed opacity-60'
                      }`}
                    >
                      {/* Lesson Number / Icon */}
                      <div
                        className={`flex-shrink-0 w-10 h-10 flex items-center justify-center font-mono text-sm ${
                          isSelected
                            ? 'bg-gold text-navy'
                            : accessible
                            ? 'bg-navy/10 text-navy'
                            : 'bg-slate-200 text-slate-400'
                        }`}
                      >
                        {accessible ? (
                          isSelected ? (
                            <PlayCircle className="w-5 h-5" />
                          ) : (
                            String(lesson.lesson).padStart(2, '0')
                          )
                        ) : (
                          <Lock className="w-4 h-4" />
                        )}
                      </div>

                      {/* Lesson Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className={`font-medium truncate ${
                            isSelected ? 'text-navy' : accessible ? 'text-navy' : 'text-slate-500'
                          }`}>
                            {lesson.title}
                          </p>
                          {lesson.free && (
                            <span className="text-xs font-mono uppercase tracking-wider bg-success/10 text-success px-1.5 py-0.5 flex-shrink-0">
                              Free
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {lesson.duration}
                          </span>
                          {lesson.pdf_url && accessible && (
                            <span className="flex items-center gap-1">
                              <FileText className="w-3 h-3" />
                              PDF included
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Action indicator */}
                      <div className="flex-shrink-0">
                        {accessible ? (
                          <span className={`text-xs font-mono uppercase tracking-widest ${
                            isSelected ? 'text-gold' : 'text-muted-foreground'
                          }`}>
                            {isSelected ? 'Playing' : 'Watch'}
                          </span>
                        ) : (
                          <span className="text-xs font-mono uppercase tracking-widest text-slate-400">
                            Locked
                          </span>
                        )}
                      </div>
                    </Button>
                  );
                })}
              </div>
            </div>

            {/* All lessons open — no paywall */}
          </div>
        </div>

        <MobileBottomNav />
      </main>
    </div>
  );
}
