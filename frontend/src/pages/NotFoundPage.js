import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold text-navy mb-4">404</h1>
        <p className="text-muted-foreground mb-6">Page not found</p>
        <Link to="/dashboard" className="text-navy hover:underline">
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}