import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  GraduationCap,
  Lock,
  AlertTriangle,
  PlayCircle,
  FileText,
  Clock,
} from 'lucide-react';

// ───────────────────────────────────────────────────────────
// Lesson data — 27-lesson curriculum with video/PDF where available
// ───────────────────────────────────────────────────────────
const LESSON_DATA = {
  1: {
    number: 1,
    title: 'The Highest Standard in American Law',
    module: 1,
    moduleTitle: 'The Weight of the Role',
    duration: '~7 min',
    description:
      'Learn what "fiduciary" really means and why trustees are held to the highest legal standard in American law.',
    videoGuid: 'b095719e-96c6-4a0a-a845-5f003777ff2f',
    pdfUrl: null,
  },
  2: {
    number: 2,
    title: 'Should You Accept? What Happens When the Grantor Dies',
    module: 2,
    moduleTitle: 'The Paper Trail',
    duration: '~5 min',
    description:
      'When someone asks you to be a trustee, you have a choice. Understand what happens if you say yes — or no.',
    videoGuid: '670222ba-cde6-4772-b3af-dac84fd91db0',
    pdfUrl: null,
  },
  3: {
    number: 3,
    title: "The Trustee's First Seven Days",
    module: 3,
    moduleTitle: 'Write It Down',
    duration: '~5 min',
    description:
      'Your first week sets the tone for everything. A step-by-step guide to the critical first actions every new trustee must take.',
    videoGuid: 'c34cbf6b-fc5d-4c5e-bd33-cb5e6c84b422',
    pdfUrl: null,
  },
  4: {
    number: 4,
    title: 'Documenting Every Decision',
    module: 2,
    moduleTitle: 'The Paper Trail',
    duration: '~6 min',
    description:
      'Every trustee decision needs a paper trail. Learn why documentation is your best defense and how to do it right.',
    videoGuid: null,
    pdfUrl: null,
  },
  5: {
    number: 5,
    title: 'Keeping Proper Records',
    module: 2,
    moduleTitle: 'The Paper Trail',
    duration: '~5 min',
    description:
      'Good records protect you and the beneficiaries. Here\'s how to maintain trust records that stand up to scrutiny.',
    videoGuid: null,
    pdfUrl: null,
  },
  6: {
    number: 6,
    title: 'What Goes Wrong Without Paper',
    module: 2,
    moduleTitle: 'The Paper Trail',
    duration: '~5 min',
    description:
      'Real-world stories of what happens when trustees don\'t document their actions — and how to avoid the same fate.',
    videoGuid: null,
    pdfUrl: null,
  },
  7: {
    number: 7,
    title: 'The Art of Trust Minutes',
    module: 3,
    moduleTitle: 'Write It Down',
    duration: '~6 min',
    description:
      'Trust minutes are your most powerful governance tool. Learn how to write them clearly and completely.',
    videoGuid: null,
    pdfUrl: null,
  },
  8: {
    number: 8,
    title: 'Frequency and Format',
    module: 3,
    moduleTitle: 'Write It Down',
    duration: '~5 min',
    description:
      'How often should you document? What format works best? Practical guidance for consistent, defensible record-keeping.',
    videoGuid: null,
    pdfUrl: null,
  },
  9: {
    number: 9,
    title: 'What to Include and Exclude',
    module: 3,
    moduleTitle: 'Write It Down',
    duration: '~5 min',
    description:
      'Not everything belongs in your trust records. Learn what must be included, what should be left out, and why.',
    videoGuid: null,
    pdfUrl: null,
  },
  10: {
    number: 10,
    title: 'Understanding Beneficiary Rights',
    module: 4,
    moduleTitle: 'Who Gets What',
    duration: '~6 min',
    description:
      'HEMS decoded: Understand the Health, Education, Maintenance, and Support standard that governs most discretionary trusts.',
    videoGuid: '41982ee9-6c8a-4fe7-babd-29671b44a82c',
    pdfUrl: '/pdfs/lesson10-hems-decision-framework.pdf',
  },
  11: {
    number: 11,
    title: 'Discretionary vs Mandatory Distributions',
    module: 4,
    moduleTitle: 'Who Gets What',
    duration: '~5 min',
    description:
      'Not all distributions are created equal. Understand the difference between mandatory and discretionary, and when each applies.',
    videoGuid: null,
    pdfUrl: null,
  },
  12: {
    number: 12,
    title: 'Fairness Is Not Equality',
    module: 4,
    moduleTitle: 'Who Gets What',
    duration: '~5 min',
    description:
      'Treating beneficiaries "equally" can actually be unfair. Learn why the trust document, not equality, should guide your decisions.',
    videoGuid: null,
    pdfUrl: null,
  },
  13: {
    number: 13,
    title: 'Separate Accounts, Separate Lives',
    module: 5,
    moduleTitle: 'The Commingling Trap',
    duration: '~6 min',
    description:
      'The six rules of separation that every trustee must follow. One violation can create a legal nightmare.',
    videoGuid: '27edf118-8dc1-41b8-b32a-0c5057a55fec',
    pdfUrl: '/pdfs/lesson13-separation-checklist.pdf',
  },
  14: {
    number: 14,
    title: 'What Commingling Looks Like',
    module: 5,
    moduleTitle: 'The Commingling Trap',
    duration: '~5 min',
    description:
      'Real examples of how commingling happens — often without the trustee even realizing it. Learn to spot the warning signs.',
    videoGuid: null,
    pdfUrl: null,
  },
  15: {
    number: 15,
    title: 'How to Untangle It',
    module: 5,
    moduleTitle: 'The Commingling Trap',
    duration: '~5 min',
    description:
      'If commingling has already occurred, all is not lost. Here are the steps to untangle mixed assets and protect the trust.',
    videoGuid: null,
    pdfUrl: null,
  },
  16: {
    number: 16,
    title: 'Trust Tax Basics',
    module: 6,
    moduleTitle: 'Taxes and Deadlines',
    duration: '~6 min',
    description:
      'Trust taxation is different from personal taxation. Learn the basics every trustee needs to know.',
    videoGuid: null,
    pdfUrl: null,
  },
  17: {
    number: 17,
    title: 'Key Filing Deadlines',
    module: 6,
    moduleTitle: 'Taxes and Deadlines',
    duration: '~5 min',
    description:
      'Miss a deadline and the penalties can be severe. Here are the critical dates every trustee must track.',
    videoGuid: null,
    pdfUrl: null,
  },
  18: {
    number: 18,
    title: 'Working With Professionals',
    module: 6,
    moduleTitle: 'Taxes and Deadlines',
    duration: '~5 min',
    description:
      'You don\'t have to go it alone. How to find, hire, and work with CPAs, attorneys, and other trust professionals.',
    videoGuid: null,
    pdfUrl: null,
  },
  19: {
    number: 19,
    title: 'The Prudent Investor Rule',
    module: 7,
    moduleTitle: 'Invest and Delegate',
    duration: '~6 min',
    description:
      'The Prudent Investor Rule is your legal standard for managing trust assets. Here\'s how to follow it.',
    videoGuid: null,
    pdfUrl: null,
  },
  20: {
    number: 20,
    title: 'When and How to Delegate',
    module: 7,
    moduleTitle: 'Invest and Delegate',
    duration: '~5 min',
    description:
      'Delegation is not abdication. Learn the right way to hand off responsibilities while maintaining oversight.',
    videoGuid: null,
    pdfUrl: null,
  },
  21: {
    number: 21,
    title: 'Monitoring What You Hand Off',
    module: 7,
    moduleTitle: 'Invest and Delegate',
    duration: '~5 min',
    description:
      'You delegated — now what? Active monitoring is still your responsibility. Here\'s how to stay on top of it.',
    videoGuid: null,
    pdfUrl: null,
  },
  22: {
    number: 22,
    title: 'Transparency Builds Trust',
    module: 8,
    moduleTitle: 'Communication That Prevents Lawsuits',
    duration: '~6 min',
    description:
      'Most trust disputes start with poor communication. Learn how transparency prevents problems before they start.',
    videoGuid: null,
    pdfUrl: null,
  },
  23: {
    number: 23,
    title: 'Annual Reports and Beyond',
    module: 8,
    moduleTitle: 'Communication That Prevents Lawsuits',
    duration: '~5 min',
    description:
      'Annual reports are more than a formality. Here\'s how to create reports that inform, protect, and satisfy your duties.',
    videoGuid: null,
    pdfUrl: null,
  },
  24: {
    number: 24,
    title: 'Handling Beneficiary Disputes',
    module: 8,
    moduleTitle: 'Communication That Prevents Lawsuits',
    duration: '~5 min',
    description:
      'When beneficiaries disagree, the trustee is in the crossfire. Learn strategies for handling disputes fairly and legally.',
    videoGuid: null,
    pdfUrl: null,
  },
  25: {
    number: 25,
    title: 'Emotional Dynamics of Trusteeship',
    module: 9,
    moduleTitle: 'When Family and Trust Collide',
    duration: '~6 min',
    description:
      'Trusteeship is emotional work. Understanding the family dynamics at play helps you make better decisions.',
    videoGuid: null,
    pdfUrl: null,
  },
  26: {
    number: 26,
    title: 'Conflict of Interest Scenarios',
    module: 9,
    moduleTitle: 'When Family and Trust Collide',
    duration: '~5 min',
    description:
      'Self-dealing, favoritism, and hidden conflicts — learn to identify and avoid the conflicts that sink trustees.',
    videoGuid: null,
    pdfUrl: null,
  },
  27: {
    number: 27,
    title: 'Building a Legacy of Trust',
    module: 9,
    moduleTitle: 'When Family and Trust Collide',
    duration: '~5 min',
    description:
      'The capstone lesson: bringing it all together to build a legacy of trust, competence, and integrity.',
    videoGuid: null,
    pdfUrl: null,
  },
};

const BUNNY_EMBED_BASE = 'https://iframe.mediadelivery.net/embed/609821';
const TOTAL_LESSONS = 27;

export default function LessonPlayerPage() {
  const { lessonNumber } = useParams();
  const navigate = useNavigate();
  const { user, subscription, subscriptionExpired, isReadOnly } = useAuth();
  const [accessChecked, setAccessChecked] = useState(false);
  const [hasAccess, setHasAccess] = useState(false);
  const [accessLoading, setAccessLoading] = useState(true);

  const lessonNum = parseInt(lessonNumber, 10);
  const lesson = LESSON_DATA[lessonNum];
  const prevLesson = lessonNum > 1 ? LESSON_DATA[lessonNum - 1] : null;
  const nextLesson = lessonNum < TOTAL_LESSONS ? LESSON_DATA[lessonNum + 1] : null;

  const isSubscribed = subscription?.is_active && !subscriptionExpired && !isReadOnly;
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  const hasFullAccess = isSubscribed || isAdmin;

  // Free preview lessons (Module 1: lessons 1-3)
  const isFreeLesson = lessonNum >= 1 && lessonNum <= 3;

  // Check lesson access via backend
  useEffect(() => {
    const checkAccess = async () => {
      if (!lesson) {
        setAccessLoading(false);
        return;
      }
      try {
        const email = user?.email || '';
        const res = await fetch(
          `${import.meta.env.VITE_API_URL || ''}/api/courses/trustee-101/lesson/${lessonNum}/access?email=${encodeURIComponent(email)}`,
          {
            headers: {
              Authorization: `Bearer ${localStorage.getItem('auth_token')}`,
            },
          }
        );
        if (res.ok) {
          const data = await res.json();
          setHasAccess(data.has_access);
        } else {
          // Fallback: free lessons always accessible, paid require subscription
          setHasAccess(isFreeLesson || hasFullAccess);
        }
      } catch {
        // Fallback on network error
        setHasAccess(isFreeLesson || hasFullAccess);
      }
      setAccessChecked(true);
      setAccessLoading(false);
    };
    checkAccess();
  }, [lessonNum, lesson, user?.email, isFreeLesson, hasFullAccess]);

  // Invalid lesson number
  if (!lesson) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <MobileBottomNav />
        <div className="lg:ml-64 p-4 sm:p-6 lg:p-8">
          <div className="max-w-3xl mx-auto text-center py-20">
            <AlertTriangle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
            <h2 className="font-serif text-2xl text-navy mb-2">Lesson Not Found</h2>
            <p className="text-muted-foreground mb-6">
              This lesson doesn't exist in the curriculum.
            </p>
            <Button className="btn-primary" onClick={() => navigate('/course')}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Course
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Access loading
  if (accessLoading) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <MobileBottomNav />
        <div className="lg:ml-64 p-4 sm:p-6 lg:p-8">
          <div className="max-w-3xl mx-auto flex items-center justify-center py-20">
            <div className="w-8 h-8 border-2 border-navy border-t-transparent animate-spin mr-3" />
            <span className="text-muted-foreground">Checking access...</span>
          </div>
        </div>
      </div>
    );
  }

  // No access
  if (accessChecked && !hasAccess) {
    return (
      <div className="min-h-screen bg-subtle-bg">
        <Sidebar />
        <MobileBottomNav />
        <div className="lg:ml-64 p-4 sm:p-6 lg:p-8">
          <div className="max-w-3xl mx-auto text-center py-20">
            <div className="w-16 h-16 bg-[#010079]/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <Lock className="w-8 h-8 text-[#010079]" />
            </div>
            <h2 className="font-serif text-2xl text-navy mb-2">Lesson Locked</h2>
            <p className="text-muted-foreground mb-2">
              Lesson {lesson.number}: {lesson.title}
            </p>
            <p className="text-sm text-muted-foreground mb-6">
              Subscribe to unlock all 27 lessons and become a confident trustee.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
              <Button className="btn-primary" onClick={() => navigate('/pricing')}>
                View Plans
              </Button>
              <Button variant="outline" onClick={() => navigate('/course')}>
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Course
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <MobileBottomNav />

      <div className="lg:ml-64 p-4 sm:p-6 lg:p-8">
        <div className="max-w-4xl mx-auto">
          {/* Breadcrumb */}
          <button
            onClick={() => navigate('/course')}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-navy transition-colors mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Course</span>
          </button>

          {/* Module tag */}
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Module {lesson.module}
            </span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">{lesson.moduleTitle}</span>
          </div>

          {/* Lesson title */}
          <h1 className="font-serif text-2xl sm:text-3xl text-navy mb-2">
            Lesson {lesson.number}: {lesson.title}
          </h1>

          {/* Meta row */}
          <div className="flex items-center gap-4 text-sm text-muted-foreground mb-6">
            <span className="flex items-center gap-1">
              <Clock className="w-4 h-4" />
              {lesson.duration}
            </span>
            <span>Lesson {lesson.number} of {TOTAL_LESSONS}</span>
            {isFreeLesson && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-success/10 text-success">
                Free Preview
              </span>
            )}
          </div>

          {/* Video / Coming Soon area */}
          <div className="bg-white border border-border rounded-lg overflow-hidden mb-6">
            {lesson.videoGuid ? (
              <div className="relative w-full" style={{ paddingBottom: '56.25%' }}>
                <iframe
                  src={`${BUNNY_EMBED_BASE}/${lesson.videoGuid}?autoplay=false&loop=false&muted=false&preload=true&responsive=true`}
                  className="absolute inset-0 w-full h-full"
                  allow="autoplay; fullscreen"
                  allowFullScreen
                  title={`Lesson ${lesson.number}: ${lesson.title}`}
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
                <div className="w-16 h-16 bg-[#010079]/5 rounded-full flex items-center justify-center mb-4">
                  <PlayCircle className="w-8 h-8 text-[#010079]/40" />
                </div>
                <h3 className="font-serif text-xl text-navy mb-2">Coming Soon</h3>
                <p className="text-muted-foreground text-sm max-w-md">
                  {lesson.title} is part of our curriculum and will be available soon.
                  In the meantime, explore the lessons that are ready below.
                </p>
                <Button
                  variant="outline"
                  className="mt-4"
                  onClick={() => navigate('/course')}
                >
                  View Available Lessons
                </Button>
              </div>
            )}
          </div>

          {/* PDF Download */}
          {lesson.pdfUrl && (
            <div className="bg-white border border-border rounded-lg p-4 mb-6">
              <a
                href={lesson.pdfUrl}
                download
                className="flex items-center gap-3 text-navy hover:text-[#D5AD36] transition-colors"
              >
                <div className="w-10 h-10 bg-[#D5AD36]/10 rounded-lg flex items-center justify-center">
                  <FileText className="w-5 h-5 text-[#D5AD36]" />
                </div>
                <div>
                  <p className="text-sm font-medium">Download Lesson Resource</p>
                  <p className="text-xs text-muted-foreground">PDF · Decision Framework</p>
                </div>
                <Download className="w-4 h-4 ml-auto" />
              </a>
            </div>
          )}

          {/* Description */}
          <div className="bg-white border border-border rounded-lg p-6 mb-6">
            <h3 className="font-serif text-lg text-navy mb-2">About This Lesson</h3>
            <p className="text-muted-foreground leading-relaxed">{lesson.description}</p>
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between gap-4 mb-6">
            {prevLesson ? (
              <Button
                variant="outline"
                onClick={() => navigate(`/course/lesson/${prevLesson.number}`)}
                className="flex items-center gap-2"
              >
                <ChevronLeft className="w-4 h-4" />
                <span className="hidden sm:inline">Lesson {prevLesson.number}</span>
                <span className="sm:hidden">Previous</span>
              </Button>
            ) : (
              <div />
            )}

            {nextLesson ? (
              <Button
                className="btn-primary flex items-center gap-2"
                onClick={() => navigate(`/course/lesson/${nextLesson.number}`)}
              >
                <span className="hidden sm:inline">Lesson {nextLesson.number}: {nextLesson.title}</span>
                <span className="sm:hidden">Next</span>
                <ChevronRight className="w-4 h-4" />
              </Button>
            ) : (
              <Button
                className="btn-primary flex items-center gap-2"
                onClick={() => navigate('/course')}
              >
                <GraduationCap className="w-4 h-4" />
                Complete Course
              </Button>
            )}
          </div>

          {/* Disclaimer */}
          <div className="bg-[#010079]/5 border border-[#010079]/10 rounded-lg p-4 mb-8">
            <p className="text-xs text-muted-foreground leading-relaxed">
              <strong className="text-navy">Disclaimer:</strong> This content is provided for
              educational purposes only and does not constitute legal advice. Always consult a
              qualified attorney for your specific situation.
            </p>
          </div>

          {/* Bottom spacing for mobile nav */}
          <div className="h-20 lg:h-8" />
        </div>
      </div>
    </div>
  );
}