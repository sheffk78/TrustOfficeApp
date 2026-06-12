import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  Play,
  Lock,
  CheckCircle2,
  Clock,
  GraduationCap,
  Award
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const COURSE_DATA = [
  {
    module: 1,
    title: 'The Weight of the Role',
    lessons: [
      { number: 1, title: 'The Highest Standard in American Law', duration: '~7 min' },
      { number: 2, title: 'Should You Accept? What Happens When the Grantor Dies', duration: '~5 min' },
      { number: 3, title: "The Trustee's First Seven Days", duration: '~5 min' },
    ],
  },
  {
    module: 2,
    title: 'The Paper Trail',
    lessons: [
      { number: 4, title: 'Documenting Every Decision', duration: '~6 min' },
      { number: 5, title: 'Keeping Proper Records', duration: '~5 min' },
      { number: 6, title: 'What Goes Wrong Without Paper', duration: '~5 min' },
    ],
  },
  {
    module: 3,
    title: 'Write It Down',
    lessons: [
      { number: 7, title: 'The Art of Trust Minutes', duration: '~6 min' },
      { number: 8, title: 'Frequency and Format', duration: '~5 min' },
      { number: 9, title: 'What to Include and Exclude', duration: '~5 min' },
    ],
  },
  {
    module: 4,
    title: 'Who Gets What',
    lessons: [
      { number: 10, title: 'Understanding Beneficiary Rights', duration: '~6 min' },
      { number: 11, title: 'Discretionary vs Mandatory Distributions', duration: '~5 min' },
      { number: 12, title: 'Fairness Is Not Equality', duration: '~5 min' },
    ],
  },
  {
    module: 5,
    title: 'The Commingling Trap',
    lessons: [
      { number: 13, title: 'Separate Accounts, Separate Lives', duration: '~6 min' },
      { number: 14, title: 'What Commingling Looks Like', duration: '~5 min' },
      { number: 15, title: 'How to Untangle It', duration: '~5 min' },
    ],
  },
  {
    module: 6,
    title: 'Taxes and Deadlines',
    lessons: [
      { number: 16, title: 'Trust Tax Basics', duration: '~6 min' },
      { number: 17, title: 'Key Filing Deadlines', duration: '~5 min' },
      { number: 18, title: 'Working With Professionals', duration: '~5 min' },
    ],
  },
  {
    module: 7,
    title: 'Invest and Delegate',
    lessons: [
      { number: 19, title: 'The Prudent Investor Rule', duration: '~6 min' },
      { number: 20, title: 'When and How to Delegate', duration: '~5 min' },
      { number: 21, title: 'Monitoring What You Hand Off', duration: '~5 min' },
    ],
  },
  {
    module: 8,
    title: 'Communication That Prevents Lawsuits',
    lessons: [
      { number: 22, title: 'Transparency Builds Trust', duration: '~6 min' },
      { number: 23, title: 'Annual Reports and Beyond', duration: '~5 min' },
      { number: 24, title: 'Handling Beneficiary Disputes', duration: '~5 min' },
    ],
  },
  {
    module: 9,
    title: 'When Family and Trust Collide',
    lessons: [
      { number: 25, title: 'Emotional Dynamics of Trusteeship', duration: '~6 min' },
      { number: 26, title: 'Conflict of Interest Scenarios', duration: '~5 min' },
      { number: 27, title: 'Building a Legacy of Trust', duration: '~5 min' },
    ],
  },
];

const FREE_PREVIEW_LESSONS = [1, 2, 3]; // Module 1 is free preview

export default function CoursePage() {
  const { subscription, subscriptionExpired, isReadOnly, user } = useAuth();
  const navigate = useNavigate();
  const [expandedModules, setExpandedModules] = useState({ 1: true }); // Module 1 expanded by default

  const isSubscribed = subscription?.is_active && !subscriptionExpired && !isReadOnly;
  const isAdmin = user?.is_admin || user?.email?.toLowerCase() === 'contact@trustoffice.app';
  const hasFullAccess = isSubscribed || isAdmin;
  const completedCount = 0; // placeholder — will be dynamic later

  const toggleModule = (moduleNumber) => {
    setExpandedModules((prev) => ({
      ...prev,
      [moduleNumber]: !prev[moduleNumber],
    }));
  };

  const isLessonUnlocked = (lessonNumber) => {
    if (hasFullAccess) return true;
    return FREE_PREVIEW_LESSONS.includes(lessonNumber);
  };

  const isLessonFree = (lessonNumber) => {
    return FREE_PREVIEW_LESSONS.includes(lessonNumber);
  };

  const getLessonIcon = (lessonNumber) => {
    if (isLessonUnlocked(lessonNumber)) {
      if (isLessonFree(lessonNumber)) {
        return <CheckCircle2 className="w-5 h-5 text-success" />;
      }
      return <Play className="w-5 h-5 text-[#D5AD36]" />;
    }
    return <Lock className="w-5 h-5 text-muted-foreground" />;
  };

  return (
    <div className="min-h-screen bg-subtle-bg">
      <Sidebar />
      <MobileBottomNav />

      <div className="lg:ml-64 p-4 sm:p-6 lg:p-8">
        {/* Header */}
        <div className="max-w-3xl mx-auto mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-12 h-12 bg-[#010079] rounded-lg flex items-center justify-center">
              <GraduationCap className="w-6 h-6 text-[#D5AD36]" />
            </div>
            <div>
              <h1 className="font-serif text-2xl sm:text-3xl text-navy">Trustee 101</h1>
              <p className="text-sm text-muted-foreground">27 lessons across 9 modules</p>
            </div>
          </div>

          {/* Progress Bar */}
          <div className="mt-6 bg-white border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="label-trust text-xs uppercase tracking-widest">Your Progress</span>
              <span className="text-sm font-medium text-navy">{completedCount}/27 completed</span>
            </div>
            <div className="w-full bg-subtle-bg rounded-full h-2">
              <div
                className="bg-[#D5AD36] h-2 rounded-full transition-all duration-300"
                style={{ width: `${(completedCount / 27) * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* Module List */}
        <div className="max-w-3xl mx-auto space-y-3">
          {COURSE_DATA.map((mod) => (
            <div
              key={mod.module}
              className="bg-white border border-border rounded-lg overflow-hidden"
            >
              {/* Module Header */}
              <button
                onClick={() => toggleModule(mod.module)}
                className="w-full flex items-center justify-between p-4 hover:bg-subtle-bg/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {expandedModules[mod.module] ? (
                    <ChevronDown className="w-5 h-5 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="w-5 h-5 text-muted-foreground" />
                  )}
                  <div className="text-left">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
                        Module {mod.module}
                      </span>
                      {mod.module === 1 && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-success/10 text-success">
                          Free Preview
                        </span>
                      )}
                    </div>
                    <h3 className="font-serif text-lg text-navy">{mod.title}</h3>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Clock className="w-4 h-4" />
                  <span>{mod.lessons.length} lessons</span>
                </div>
              </button>

              {/* Lessons */}
              {expandedModules[mod.module] && (
                <div className="border-t border-border">
                  {mod.lessons.map((lesson) => {
                    const unlocked = isLessonUnlocked(lesson.number);
                    const free = isLessonFree(lesson.number);

                    return (
                      <div
                        key={lesson.number}
                        className={`flex items-center justify-between px-4 py-3 border-b border-border last:border-b-0 ${
                          unlocked
                            ? 'hover:bg-subtle-bg/30 cursor-pointer'
                            : 'opacity-60 cursor-not-allowed'
                        }`}
                        onClick={() => {
                          if (unlocked) {
                            navigate(`/course/lesson/${lesson.number}`);
                          }
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full flex items-center justify-center bg-subtle-bg">
                            {getLessonIcon(lesson.number)}
                          </div>
                          <div>
                            <p className={`text-sm font-medium ${unlocked ? 'text-navy' : 'text-muted-foreground'}`}>
                              Lesson {lesson.number}: {lesson.title}
                            </p>
                            <p className="text-xs text-muted-foreground flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {lesson.duration}
                            </p>
                          </div>
                        </div>
                        {!unlocked && (
                          <span className="text-xs text-muted-foreground font-mono">🔒 Locked</span>
                        )}
                        {free && !hasFullAccess && (
                          <span className="text-xs text-success font-medium">Free</span>
                        )}
                        {unlocked && !free && (
                          <span className="text-xs text-[#D5AD36] font-medium">Available</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <div className="max-w-3xl mx-auto mt-8">
          <div className="bg-white border border-border rounded-lg p-6 text-center">
            {hasFullAccess ? (
              <>
                <div className="w-12 h-12 mx-auto mb-4 bg-[#010079]/5 rounded-full flex items-center justify-center">
                  <Award className="w-6 h-6 text-[#010079]" />
                </div>
                <h3 className="font-serif text-xl text-navy mb-2">Start from Module 1</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  All 27 lessons are unlocked. Begin your trustee education today.
                </p>
                <Button
                  className="btn-primary"
                  onClick={() => {
                    navigate('/course/lesson/1');
                  }}
                >
                  <Play className="w-4 h-4 mr-2" />
                  Start Course
                </Button>
              </>
            ) : (
              <>
                <div className="w-12 h-12 mx-auto mb-4 bg-[#D5AD36]/10 rounded-full flex items-center justify-center">
                  <Lock className="w-6 h-6 text-[#D5AD36]" />
                </div>
                <h3 className="font-serif text-xl text-navy mb-2">Subscribe to Unlock All Lessons</h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Module 1 is free. Subscribe to access all 27 lessons and become a confident trustee.
                </p>
                <Button
                  className="btn-primary"
                  onClick={() => navigate('/pricing')}
                >
                  <BookOpen className="w-4 h-4 mr-2" />
                  View Plans
                </Button>
              </>
            )}
          </div>
        </div>

        {/* Bottom spacing for mobile nav */}
        <div className="h-20 lg:h-8" />
      </div>
    </div>
  );
}