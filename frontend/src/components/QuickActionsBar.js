import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Plus, CalendarPlus, CalendarDays, Pencil } from 'lucide-react';

/**
 * QuickActionsBar — horizontal action bar for the Client Dashboard.
 *
 * Props:
 *   clientId: string — the client ID (used for deadline view link)
 *   onEdit: () => void — called when "Edit Client" is clicked
 *   onAddTrust: () => void — called when "Add Trust to Client" is clicked
 */
export default function QuickActionsBar({ clientId, onEdit, onAddTrust }) {
  return (
    <div
      className="flex flex-wrap items-center gap-2 mb-6 btn-group-mobile"
      data-testid="quick-actions-bar"
    >
      <Button
        onClick={onAddTrust}
        className="btn-primary"
        size="sm"
        data-testid="add-trust-btn"
      >
        <Plus className="w-4 h-4 mr-1.5" />
        Add Trust to Client
      </Button>

      <Link to="/calendar">
        <Button
          variant="outline"
          size="sm"
          className="btn-secondary"
          data-testid="schedule-meeting-btn"
        >
          <CalendarPlus className="w-4 h-4 mr-1.5" />
          Schedule Meeting
        </Button>
      </Link>

      <Link to="/calendar">
        <Button
          variant="outline"
          size="sm"
          className="btn-secondary"
          data-testid="view-deadlines-btn"
        >
          <CalendarDays className="w-4 h-4 mr-1.5" />
          View All Deadlines
        </Button>
      </Link>

      <Button
        onClick={onEdit}
        variant="outline"
        size="sm"
        className="btn-secondary"
        data-testid="edit-client-btn"
      >
        <Pencil className="w-4 h-4 mr-1.5" />
        Edit Client
      </Button>
    </div>
  );
}
