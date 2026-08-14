import { Component } from 'react';
import { reportErrorToBackend } from '@/utils/errors';

/**
 * PageAgentErrorBoundary — renders a small fallback message on error so
 * the host page isn't blocked if the Page Agent integration crashes
 * during render. Reports the crash to the backend.
 *
 * Shared between OnboardingConfirmStep and DistributionsPage.
 */
export default class PageAgentErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError() {
    return { hasError: true };
  }
  componentDidCatch(error) {
    console.error('[PageAgentErrorBoundary] render crashed:', error);
    reportErrorToBackend(error, { operation: 'page_agent_render', page: window.location.pathname, severity: 'major' });
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="text-sm text-muted-foreground p-2">
          This section failed to load.
        </div>
      );
    }
    return this.props.children;
  }
}