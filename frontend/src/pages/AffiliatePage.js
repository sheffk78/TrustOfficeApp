import { Link } from 'react-router-dom';
import { 
  DollarSign, 
  Users, 
  TrendingUp, 
  CheckCircle2, 
  ArrowRight,
  Gift,
  BarChart3,
  Clock,
  Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function AffiliatePage() {
  const benefits = [
    {
      icon: DollarSign,
      title: "Generous Commissions",
      description: "Earn competitive recurring commissions for every customer you refer who subscribes."
    },
    {
      icon: Clock,
      title: "Long Cookie Duration",
      description: "Extended tracking window ensures you get credit for referrals even if they don't convert immediately."
    },
    {
      icon: BarChart3,
      title: "Real-Time Dashboard",
      description: "Track your clicks, conversions, and earnings with our comprehensive affiliate dashboard."
    },
    {
      icon: Zap,
      title: "Fast Payouts",
      description: "Get paid reliably and on time. We value our partners and ensure prompt commission payments."
    }
  ];

  const steps = [
    {
      number: "1",
      title: "Sign Up",
      description: "Join our affiliate program in minutes. No approval wait times."
    },
    {
      number: "2",
      title: "Share Your Link",
      description: "Get your unique referral link and share it with your audience."
    },
    {
      number: "3",
      title: "Earn Commissions",
      description: "Earn money every time someone subscribes through your link."
    }
  ];

  const idealPartners = [
    "Trust & Estate Attorneys",
    "Financial Advisors",
    "CPAs & Accountants",
    "Wealth Managers",
    "Legal Bloggers & Content Creators",
    "Business Consultants"
  ];

  return (
    <div className="min-h-screen bg-subtle-bg">
      {/* Header */}
      <header className="bg-navy text-white">
        <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gold rounded flex items-center justify-center">
              <span className="text-navy font-bold text-sm">TO</span>
            </div>
            <span className="font-serif text-xl">TrustOffice</span>
          </Link>
          <Link to="/login">
            <Button variant="outline" className="border-white text-white hover:bg-white hover:text-navy">
              Sign In
            </Button>
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section className="bg-navy text-white py-20">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <div className="inline-flex items-center gap-2 bg-gold/20 text-gold px-4 py-2 rounded-full mb-6">
            <Gift className="w-4 h-4" />
            <span className="text-sm font-medium">Partner Program</span>
          </div>
          <h1 className="font-serif text-4xl md:text-5xl lg:text-6xl mb-6">
            Earn Money Promoting<br />
            <span className="text-gold">TrustOffice</span>
          </h1>
          <p className="text-lg md:text-xl text-white/80 mb-8 max-w-2xl mx-auto">
            Join our affiliate program and earn generous commissions by referring trust administrators, 
            estate planners, and fiduciaries to TrustOffice.
          </p>
          <a 
            href="https://trustoffice.partneroapp.com/program" 
            target="_blank" 
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-gold text-navy px-8 py-4 rounded font-semibold text-lg hover:bg-gold/90 transition-colors"
            data-testid="affiliate-signup-hero-btn"
          >
            Become an Affiliate
            <ArrowRight className="w-5 h-5" />
          </a>
        </div>
      </section>

      {/* Benefits Section */}
      <section className="py-20 px-4">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-serif text-3xl md:text-4xl text-navy mb-4">Why Partner With Us?</h2>
            <p className="text-muted-foreground max-w-2xl mx-auto">
              We've built an affiliate program that rewards you fairly for bringing valuable customers to TrustOffice.
            </p>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {benefits.map((benefit, index) => (
              <div 
                key={index} 
                className="bg-white dark:bg-slate-900 p-6 rounded border border-slate-200 dark:border-slate-800 hover:shadow-lg transition-shadow"
              >
                <div className="w-12 h-12 bg-navy/10 rounded flex items-center justify-center mb-4">
                  <benefit.icon className="w-6 h-6 text-navy" />
                </div>
                <h3 className="font-semibold text-navy text-lg mb-2">{benefit.title}</h3>
                <p className="text-muted-foreground text-sm">{benefit.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className="py-20 px-4 bg-slate-50 dark:bg-slate-900/50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="font-serif text-3xl md:text-4xl text-navy mb-4">How It Works</h2>
            <p className="text-muted-foreground">Getting started is easy. Be earning in just three simple steps.</p>
          </div>
          
          <div className="grid md:grid-cols-3 gap-8">
            {steps.map((step, index) => (
              <div key={index} className="text-center">
                <div className="w-16 h-16 bg-navy text-white rounded-full flex items-center justify-center text-2xl font-bold mx-auto mb-4">
                  {step.number}
                </div>
                <h3 className="font-semibold text-navy text-xl mb-2">{step.title}</h3>
                <p className="text-muted-foreground">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Ideal Partners Section */}
      <section className="py-20 px-4">
        <div className="max-w-4xl mx-auto">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="font-serif text-3xl md:text-4xl text-navy mb-4">Perfect For</h2>
              <p className="text-muted-foreground mb-6">
                Our affiliate program is ideal for professionals who work with individuals and families 
                managing trusts, estates, and fiduciary responsibilities.
              </p>
              <ul className="space-y-3">
                {idealPartners.map((partner, index) => (
                  <li key={index} className="flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 text-success flex-shrink-0" />
                    <span className="text-navy font-medium">{partner}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="bg-gradient-to-br from-navy to-navy/80 text-white p-8 rounded-2xl">
              <Users className="w-12 h-12 text-gold mb-4" />
              <h3 className="font-serif text-2xl mb-4">Join Our Partner Community</h3>
              <p className="text-white/80 mb-6">
                Connect with other affiliates, get marketing resources, and access exclusive promotional materials.
              </p>
              <a 
                href="https://trustoffice.partneroapp.com/program" 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 bg-gold text-navy px-6 py-3 rounded font-semibold hover:bg-gold/90 transition-colors"
                data-testid="affiliate-signup-card-btn"
              >
                Get Started
                <ArrowRight className="w-4 h-4" />
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 bg-navy text-white">
        <div className="max-w-3xl mx-auto text-center">
          <TrendingUp className="w-16 h-16 text-gold mx-auto mb-6" />
          <h2 className="font-serif text-3xl md:text-4xl mb-4">Ready to Start Earning?</h2>
          <p className="text-white/80 text-lg mb-8">
            Join the TrustOffice affiliate program today and start earning commissions 
            by helping trust administrators streamline their governance workflows.
          </p>
          <a 
            href="https://trustoffice.partneroapp.com/program" 
            target="_blank" 
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 bg-gold text-navy px-8 py-4 rounded font-semibold text-lg hover:bg-gold/90 transition-colors"
            data-testid="affiliate-signup-cta-btn"
          >
            Join the Affiliate Program
            <ArrowRight className="w-5 h-5" />
          </a>
          <p className="text-white/60 text-sm mt-4">
            Free to join • No minimum requirements • Start earning immediately
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 text-white py-8 px-4">
        <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gold rounded flex items-center justify-center">
              <span className="text-navy font-bold text-sm">TO</span>
            </div>
            <span className="font-serif">TrustOffice</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-white/60">
            <Link to="/login" className="hover:text-white transition-colors">Sign In</Link>
            <Link to="/signup" className="hover:text-white transition-colors">Sign Up</Link>
            <Link to="/pricing" className="hover:text-white transition-colors">Pricing</Link>
          </div>
          <p className="text-white/40 text-sm">
            © {new Date().getFullYear()} TrustOffice. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
