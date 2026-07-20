import { Component } from 'react';

/**
 * PageAgentErrorBoundary — renders null on error so the host page
 * isn't blocked if the Page Agent integration crashes during render.
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
  }
  render() {
    if (this.state.hasError) return null;
    return this.props.children;
  }
}