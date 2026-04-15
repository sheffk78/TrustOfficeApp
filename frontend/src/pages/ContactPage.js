import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { 
  Send, 
  CheckCircle, 
  ArrowLeft, 
  Mail, 
  Building2,
  User,
  MessageSquare,
  Loader2,
  ExternalLink
} from 'lucide-react';

export default function ContactPage() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
    company: '',
    message: ''
  });
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [errors, setErrors] = useState({});

  const validateForm = () => {
    const newErrors = {};
    
    if (!formData.name.trim()) {
      newErrors.name = 'Name is required';
    }
    
    if (!formData.email.trim()) {
      newErrors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = 'Please enter a valid email address';
    }
    
    if (!formData.message.trim()) {
      newErrors.message = 'Message is required';
    } else if (formData.message.trim().length < 10) {
      newErrors.message = 'Message must be at least 10 characters';
    }
    
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!validateForm()) {
      return;
    }
    
    setLoading(true);
    
    try {
      const response = await fetch(`${process.env.REACT_APP_BACKEND_URL || ''}/api/contact`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: formData.name.trim(),
          email: formData.email.trim().toLowerCase(),
          company: formData.company.trim() || null,
          message: formData.message.trim()
        })
      });
      
      const data = await response.json();
      
      if (response.ok) {
        setSubmitted(true);
        toast.success('Message sent successfully!');
      } else {
        if (response.status === 429) {
          toast.error('Too many requests', {
            description: 'Please wait a moment before submitting again.'
          });
        } else {
          toast.error(data.detail || 'Failed to send message');
        }
      }
    } catch (error) {
      console.error('Contact form error:', error);
      toast.error('Failed to send message. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field) => (e) => {
    setFormData(prev => ({ ...prev, [field]: e.target.value }));
    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }
  };

  // Success state
  if (submitted) {
    return (
      <div className="min-h-screen bg-cream flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <div className="bg-white border border-navy/10 rounded-lg p-8 text-center shadow-sm">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-8 h-8 text-green-600" />
            </div>
            
            <h1 className="font-serif text-2xl text-navy mb-3">Message Sent!</h1>
            <p className="text-muted-foreground mb-6">
              Thank you for reaching out. We've received your message and will get back to you within 1-2 business days.
            </p>
            <p className="text-sm text-muted-foreground mb-8">
              A confirmation email has been sent to <span className="font-medium text-navy">{formData.email}</span>
            </p>
            
            <div className="space-y-3">
              <Button
                onClick={() => {
                  setSubmitted(false);
                  setFormData({ name: '', email: '', company: '', message: '' });
                }}
                variant="outline"
                className="w-full"
              >
                Send Another Message
              </Button>
              
              <a
                href="https://trustoffice.app"
                className="flex items-center justify-center gap-2 text-sm text-navy hover:text-gold transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to trustoffice.app
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-cream">
      {/* Header */}
      <header className="bg-navy text-white py-4 px-6">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <a href="https://trustoffice.app" className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <div className="w-8 h-8 border-2 border-gold flex items-center justify-center">
              <span className="font-serif text-gold text-sm">T</span>
            </div>
            <span className="font-serif text-lg">TrustOffice</span>
          </a>
          
          <Link
            to="/login"
            className="text-sm text-white/80 hover:text-white transition-colors flex items-center gap-1"
          >
            Sign In
            <ExternalLink className="w-3 h-3" />
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="py-12 px-4">
        <div className="max-w-2xl mx-auto">
          {/* Back Link */}
          <a
            href="https://trustoffice.app"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-navy transition-colors mb-8"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to trustoffice.app
          </a>

          {/* Contact Form Card */}
          <div className="bg-white border border-navy/10 rounded-lg shadow-sm">
            <div className="p-6 border-b border-navy/10">
              <h1 className="font-serif text-2xl text-navy mb-2">Contact Us</h1>
              <p className="text-muted-foreground">
                Have questions about TrustOffice? We'd love to hear from you. Fill out the form below and our team will get back to you within 1-2 business days.
              </p>
            </div>
            
            <form onSubmit={handleSubmit} className="p-6 space-y-6">
              {/* Name Field */}
              <div className="space-y-2">
                <Label htmlFor="name" className="flex items-center gap-2">
                  <User className="w-4 h-4 text-muted-foreground" />
                  Name <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="name"
                  type="text"
                  placeholder="Your full name"
                  value={formData.name}
                  onChange={handleChange('name')}
                  className={errors.name ? 'border-red-500' : ''}
                  data-testid="contact-name"
                />
                {errors.name && (
                  <p className="text-sm text-red-500">{errors.name}</p>
                )}
              </div>

              {/* Email Field */}
              <div className="space-y-2">
                <Label htmlFor="email" className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-muted-foreground" />
                  Email <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="you@example.com"
                  value={formData.email}
                  onChange={handleChange('email')}
                  className={errors.email ? 'border-red-500' : ''}
                  data-testid="contact-email"
                />
                {errors.email && (
                  <p className="text-sm text-red-500">{errors.email}</p>
                )}
              </div>

              {/* Company Field (Optional) */}
              <div className="space-y-2">
                <Label htmlFor="company" className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-muted-foreground" />
                  Company <span className="text-muted-foreground text-xs">(optional)</span>
                </Label>
                <Input
                  id="company"
                  type="text"
                  placeholder="Your company or organization"
                  value={formData.company}
                  onChange={handleChange('company')}
                  data-testid="contact-company"
                />
              </div>

              {/* Message Field */}
              <div className="space-y-2">
                <Label htmlFor="message" className="flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-muted-foreground" />
                  Message <span className="text-red-500">*</span>
                </Label>
                <Textarea
                  id="message"
                  placeholder="How can we help you?"
                  value={formData.message}
                  onChange={handleChange('message')}
                  className={`min-h-[150px] resize-none ${errors.message ? 'border-red-500' : ''}`}
                  data-testid="contact-message"
                />
                {errors.message && (
                  <p className="text-sm text-red-500">{errors.message}</p>
                )}
              </div>

              {/* Submit Button */}
              <Button
                type="submit"
                disabled={loading}
                className="w-full btn-primary"
                data-testid="contact-submit"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Sending...
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    Send Message
                  </>
                )}
              </Button>
            </form>
          </div>

          {/* Additional Info */}
          <div className="mt-8 text-center text-sm text-muted-foreground">
            <p>
              You can also reach us directly at{' '}
              <a href="mailto:contact@trustoffice.app" className="text-navy hover:text-gold transition-colors">
                contact@trustoffice.app
              </a>
            </p>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-6 px-4 border-t border-navy/10 bg-white">
        <div className="max-w-4xl mx-auto text-center text-sm text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} TrustOffice. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
