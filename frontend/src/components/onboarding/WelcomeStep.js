import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle2 } from './onboardingConstants';

/**
 * Step 4 of the onboarding wizard — the welcome / quick-start screen shown
 * after the trust is fully created and confirmed.
 */
export default function WelcomeStep({ createdTrustName }) {
  return (
    <div className="mt-8">
      <div className="card-trust corner-mark text-center mb-8">
        <div className="w-16 h-16 bg-success/10 flex items-center justify-center mx-auto mb-6 rounded-full">
          <CheckCircle2 className="w-8 h-8 text-success" />
        </div>

        <h1 className="font-serif text-3xl text-navy mb-2">
          {createdTrustName ? `${createdTrustName} is Ready!` : "You're All Set!"}
        </h1>
        <p className="text-muted-foreground mb-8">
          Your trust is created. Head to your dashboard to see your next steps.
        </p>

        <div className="text-left mb-8">
          <h3 className="text-xl font-serif text-navy dark:text-foreground mb-2">You're all set!</h3>
          <p className="text-muted-foreground mb-4">Your dashboard will guide you through the next steps to get your trust fully configured.</p>
          <Link to="/dashboard" className="btn-primary inline-flex items-center gap-2 h-12 px-6 text-base">
            Go to Dashboard <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        <div className="bg-cyan-50 border border-cyan-200 p-4 mb-6 text-left">
          <p className="text-sm text-cyan-900">
            <strong>Next up:</strong> Name a <strong>successor trustee</strong> — the person who steps in to manage your trust if you can't. You can add their contact details and a letter of guidance in <strong>Settings → Successor Trustee</strong>.
          </p>
        </div>

        <div className="bg-navy/5 border border-navy/10 p-4 mb-6">
          <p className="text-sm text-navy text-left">
            <strong>Tip:</strong> You can also explore the app with demo data to see all features in action. Demo data is separate from your real trust and can be deleted anytime in Settings.
          </p>
        </div>
      </div>
    </div>
  );
}
