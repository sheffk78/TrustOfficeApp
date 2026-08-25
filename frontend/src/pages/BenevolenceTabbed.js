/**
 * BenevolenceTabbed — wraps BenevolencePage and BenevolencePolicyPage
 * Tab state driven by ?tab= URL param (distributions | policy)
 *
 * Layout note: This wrapper does NOT render its own Sidebar/layout.
 * The child pages (BenevolencePage, BenevolencePolicyPage) each render
 * their own Sidebar + main-content + page-container. We pass the tab
 * state down so the child page can render the Tabs inside its own
 * page-container, avoiding a double-sidebar layout bug.
 */
import { useSearchParams } from 'react-router-dom';
import BenevolencePage from '@/pages/BenevolencePage';
import BenevolencePolicyPage from '@/pages/BenevolencePolicyPage';

export default function BenevolenceTabbed() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') || 'distributions';

  const handleTabChange = (newTab) => {
    setSearchParams({ tab: newTab });
  };

  if (tab === 'policy') {
    return <BenevolencePolicyPage tab={tab} onTabChange={handleTabChange} />;
  }
  return <BenevolencePage tab={tab} onTabChange={handleTabChange} />;
}