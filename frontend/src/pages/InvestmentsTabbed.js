/**
 * InvestmentsPage with Tabs — wraps InvestmentsPage and PerformanceDashboard
 * Tab state driven by ?tab= URL param (holdings | performance)
 *
 * Layout note: This wrapper does NOT render its own Sidebar/layout.
 * The child pages render their own Sidebar + main-content + page-container.
 * We pass the tab state down so the child page can render the Tabs
 * inside its own page-container, avoiding a double-sidebar layout bug.
 */
import { useSearchParams } from 'react-router-dom';
import InvestmentsPage from '@/pages/InvestmentsPage';
import PerformanceDashboard from '@/pages/PerformanceDashboard';

export default function InvestmentsTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'holdings';

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  if (tab === 'performance') {
    return <PerformanceDashboard tab={tab} onTabChange={handleTabChange} />;
  }
  return <InvestmentsPage tab={tab} onTabChange={handleTabChange} />;
}