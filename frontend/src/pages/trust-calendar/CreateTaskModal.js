import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { TASK_TYPES } from './calendarConfig';

// Create-task modal: task type select, due date, optional description.
// Controlled via newTask state + setNewTask from the parent.
//
// Props:
//   newTask     – { task_type, due_date, description }
//   setNewTask   – (next) => void
//   onClose      – () => void
//   onCreate     – () => void
export default function CreateTaskModal({ newTask, setNewTask, onClose, onCreate }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-white p-6 w-full max-w-md corner-mark"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
        role="dialog"
        aria-modal="true"
        aria-label="Create task"
        data-testid="create-task-modal"
      >
        <div className="flex items-center justify-between mb-6">
          <h2 className="font-serif text-xl text-navy">Create Task</h2>
          <button onClick={onClose} className="text-navy hover:text-navy/70" aria-label="Close dialog">
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="label-trust mb-2 block">Task Type</label>
            <select
              value={newTask.task_type}
              onChange={(e) => setNewTask({ ...newTask, task_type: e.target.value })}
              className="input-trust w-full"
              data-testid="task-type-select"
            >
              {TASK_TYPES.map((type) => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="label-trust mb-2 block">Due Date</label>
            <Input
              type="date"
              value={newTask.due_date}
              onChange={(e) => setNewTask({ ...newTask, due_date: e.target.value })}
              className="input-trust"
              data-testid="task-due-date"
            />
          </div>

          <div>
            <label className="label-trust mb-2 block">Description (Optional)</label>
            <Input
              value={newTask.description}
              onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
              placeholder="Add task description..."
              className="input-trust"
              data-testid="task-description"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <Button onClick={onClose} variant="outline" className="flex-1 btn-secondary">
              Cancel
            </Button>
            <Button onClick={onCreate} className="flex-1 btn-primary" data-testid="submit-task-btn">
              Create Task
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}