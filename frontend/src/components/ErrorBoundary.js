import React from 'react';

/**
 * Error Boundary component — catches unhandled JS errors in child components
 * and displays a fallback UI instead of crashing the entire app.
 * 
 * Usage: Wrap route-level components with <ErrorBoundary>...</ErrorBoundary>
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }

  handleReload = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-subtle-bg flex items-center justify-center p-8">
          <div className="max-w-md text-center">
            <h1 className="text-2xl font-bold text-navy mb-4">Something went wrong</h1>
            <p className="text-muted-foreground mb-6">
              An unexpected error occurred. Your data is safe — try refreshing the page.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReload}
                className="px-4 py-2 bg-navy text-white rounded hover:bg-navy/90 font-mono text-sm uppercase tracking-wider"
              >
                Try Again
              </button>
              <button
                onClick={() => window.location.href = '/'}
                className="px-4 py-2 border border-navy/20 text-navy rounded hover:bg-navy/5 font-mono text-sm uppercase tracking-wider"
              >
                Go Home
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;