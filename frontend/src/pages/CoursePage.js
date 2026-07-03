import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
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
  const { subscription } = useAuth();
  const [curriculum, setCurriculum] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedLesson, setSelectedLesson] = useState(null);

  const isActive = subscription?.is_active ?? false;

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
        {/* Header */}
        <div className="bg-navy text-white px-6 py-8 md:py-12">
          <div className="max-w-5xl mx-auto">
            <div className="flex items-center gap-2 text-gold text-sm font-mono uppercase tracking-widest mb-2">
              <BookOpen className="w-4 h-4" />
              <span>Trustee 101</span>
            </div>
            <h1 className="font-serif text-3xl md:text-4xl mb-2">{course}</h1>
            <p className="text-white/70 text-base md:text-lg max-w-2xl">{tagline}</p>
            <div className="flex flex-wrap items-center gap-4 mt-4 text-sm">
              <span className="flex items-center gap-1.5 text-white/80">
                <CheckCircle2 className="w-4 h-4 text-gold" />
                {lessons.length} lessons
              </span>
              <span className="flex items-center gap-1.5 text-white/80">
                <Sparkles className="w-4 h-4 text-gold" />
                {free_lessons.length} free
              </span>
              <span className="flex items-center gap-1.5 text-white/80">
                <CheckCircle2 className="w-4 h-4 text-gold" />
                {completedLessons} unlocked
              </span>
            </div>
          </div>
        </div>

        <div className="max-w-5xl mx-auto px-4 md:px-6 py-6 md:py-8">
          {/* Video Player + Lesson Detail */}
          {selectedLesson && (
            <div className="mb-8">
              <div className="card-trust bg-white border border-slate-200 overflow-hidden">
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
                <div className="p-5 md:p-6 border-t border-slate-200">
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

              {/* Upgrade prompt for non-subscribers on paid lessons */}
              {!isActive && selectedLesson && !selectedLesson.free && (
                <div className="mt-4 p-4 card-trust bg-gold/5 border border-gold/30 rounded">
                  <p className="text-sm text-navy">
                    This lesson is part of the subscriber course.{' '}
                    <a
                      href="/subscription"
                      className="font-medium text-gold hover:underline"
                    >
                      Subscribe at $79/mo
                    </a>{' '}
                    to unlock all 9 lessons and downloadable PDFs.
                  </p>
                </div>
              )}
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
                  <button
                    key={lesson.lesson}
                    onClick={() => handleLessonClick(lesson)}
                    disabled={!accessible}
                    className={`w-full text-left p-4 flex items-center gap-4 transition-all border ${
                      isSelected
                        ? 'border-gold bg-gold/5'
                        : accessible
                        ? 'border-slate-200 bg-white hover:border-navy/30 hover:bg-navy/5'
                        : 'border-slate-200 bg-slate-50 cursor-not-allowed opacity-60'
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
                  </button>
                );
              })}
            </div>
          </div>

          {/* Subscribe CTA for non-subscribers */}
          {!isActive && (
            <div className="mt-8 p-6 card-trust bg-navy text-white text-center">
              <h3 className="font-serif text-xl text-white mb-2">
                Unlock All 9 Lessons
              </h3>
              <p className="text-white/70 text-sm mb-4 max-w-md mx-auto">
                Get full access to the Trustee 101 course, downloadable PDFs, and the complete TrustOffice governance platform.
              </p>
              <a
                href="/subscription"
                className="btn-gold inline-flex items-center justify-center gap-2 text-sm"
              >
                Subscribe at $79/mo
              </a>
              <p className="text-white/40 text-xs mt-3">
                $79/mo is a trust expense. Paid from the trust, for the trust.
              </p>
            </div>
          )}
        </div>

        <MobileBottomNav />
      </main>
    </div>
  );
}