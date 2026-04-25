import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function NotFoundPage() {
  return (
    <div className="min-h-screen bg-subtle-bg flex items-center justify-center">
      <div className="text-center">
        <h1 className="font-serif text-6xl text-navy mb-4">404</h1>
        <p className="text-muted-foreground mb-6">Page not found</p>
        <Link to="/">
          <Button className="btn-primary">Go Home</Button>
        </Link>
      </div>
    </div>
  );
}