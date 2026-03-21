import { useState, useEffect } from 'react';
import { useAuth } from '@/context/AuthContext';
import { Sidebar } from '@/components/Sidebar';
import { MobileBottomNav } from '@/components/MobileBottomNav';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchWithAuth } from '@/utils/api';
import { 
  Calendar, 
  Plus, 
  CheckCircle2, 
  Clock, 
  AlertTriangle,
  ChevronDown,
  X
} from 'lucide-react';
import { format, parseISO, isAfter, isBefore, addDays } from 'date-fns';
import { toast } from 'sonner';

const TASK_TYPES = [
  { value: 'annual_review', label: 'Annual Review' },
  { value: 'quarterly_review', label: 'Quarterly Review' },
  { value: 'compensation_review', label: 'Compensation Review' },
  { value: 'distribution_review', label: 'Distribution Review' },
  { value: 'insurance_compliance', label: 'Insurance Compliance' },
  { value: 'custom', label: 'Custom Task' }
];

export default function CalendarPage() {
  const { selectedTrust } = useAuth();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [showModal, setShowModal] = useState(false);
  const [newTask, setNewTask] = useState({
    task_type: 'quarterly_review',
    due_date: format(addDays(new Date(), 30), 'yyyy-MM-dd'),
    description: ''
  });

  useEffect(() => {
    if (selectedTrust) {
      loadTasks();
    }
  }, [selectedTrust]);

  const loadTasks = async () => {
    if (!selectedTrust) return;
    setLoading(true);
    try {
      const response = await fetchWithAuth(`/tasks?trust_id=${selectedTrust.trust_id}`);
      if (response.ok) {
        setTasks(await response.json());
      }
    } catch (error) {
      console.error('Failed to load tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTask = async () => {
    if (!selectedTrust) return;
    try {
      const response = await fetchWithAuth('/tasks', {
        method: 'POST',
        body: JSON.stringify({
          trust_id: selectedTrust.trust_id,
          ...newTask
        })
      });
      if (response.ok) {
        toast.success('Task created');
        setShowModal(false);
        setNewTask({
          task_type: 'quarterly_review',
          due_date: format(addDays(new Date(), 30), 'yyyy-MM-dd'),
          description: ''
        });
        loadTasks();
      }
    } catch (error) {
      toast.error('Failed to create task');
    }
  };

  const handleCompleteTask = async (taskId) => {
    try {
      const response = await fetchWithAuth(`/tasks/${taskId}/complete`, {
        method: 'PATCH'
      });
      if (response.ok) {
        toast.success('Task completed');
        loadTasks();
      }
    } catch (error) {
      toast.error('Failed to complete task');
    }
  };

  const handleUncompleteTask = async (taskId) => {
    try {
      const response = await fetchWithAuth(`/tasks/${taskId}/uncomplete`, {
        method: 'PATCH'
      });
      if (response.ok) {
        toast.info('Task marked incomplete');
        loadTasks();
      }
    } catch (error) {
      toast.error('Failed to update task');
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!confirm('Delete this task?')) return;
    try {
      const response = await fetchWithAuth(`/tasks/${taskId}`, {
        method: 'DELETE'
      });
      if (response.ok) {
        toast.success('Task deleted');
        loadTasks();
      }
    } catch (error) {
      toast.error('Failed to delete task');
    }
  };

  const filteredTasks = tasks.filter(task => {
    if (filter === 'all') return true;
    if (filter === 'upcoming') return task.status === 'upcoming';
    if (filter === 'overdue') return task.status === 'overdue';
    if (filter === 'completed') return task.status === 'completed';
    return true;
  });

  const formatDate = (dateString) => {
    try {
      return format(parseISO(dateString), 'MMM d, yyyy');
    } catch {
      return dateString;
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle2 className="w-5 h-5 text-success" />;
      case 'overdue': return <AlertTriangle className="w-5 h-5 text-error" />;
      default: return <Clock className="w-5 h-5 text-navy" />;
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'completed': return 'border-l-success';
      case 'overdue': return 'border-l-error';
      default: return 'border-l-navy';
    }
  };

  const counts = {
    all: tasks.length,
    upcoming: tasks.filter(t => t.status === 'upcoming').length,
    overdue: tasks.filter(t => t.status === 'overdue').length,
    completed: tasks.filter(t => t.status === 'completed').length
  };

  return (
    <div className="main-layout" data-testid="calendar-page">
      <Sidebar />
      <main className="main-content dot-grid">
        <div className="page-container">
          {/* Page Header */}
          <div className="page-header flex items-center justify-between">
            <div>
              <h1 className="page-title">Governance Calendar</h1>
              <p className="page-subtitle">
                {selectedTrust?.name || 'Select a trust'} • Manage compliance tasks
              </p>
            </div>
            <Button 
              onClick={() => setShowModal(true)} 
              className="btn-primary"
              data-testid="create-task-btn"
            >
              <Plus className="w-4 h-4 mr-2" /> New Task
            </Button>
          </div>

          {/* Filter Tabs */}
          <div className="flex gap-2 mb-6">
            {['all', 'upcoming', 'overdue', 'completed'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-2 font-mono text-xs uppercase tracking-widest transition-colors ${
                  filter === f 
                    ? 'bg-navy text-white' 
                    : 'bg-white border border-navy/20 text-navy hover:bg-navy/5'
                }`}
                data-testid={`filter-${f}`}
              >
                {f} ({counts[f]})
              </button>
            ))}
          </div>

          {/* Tasks List */}
          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="card-trust">
                  <div className="skeleton h-6 w-48 mb-2"></div>
                  <div className="skeleton h-4 w-32"></div>
                </div>
              ))}
            </div>
          ) : filteredTasks.length === 0 ? (
            <div className="card-trust text-center py-12">
              <Calendar className="w-12 h-12 text-navy/30 mx-auto mb-4" />
              <h3 className="font-serif text-xl text-navy mb-2">No Tasks Found</h3>
              <p className="text-muted-foreground mb-4">
                {filter === 'all' 
                  ? 'Create your first governance task to get started' 
                  : `No ${filter} tasks`}
              </p>
              {filter === 'all' && (
                <Button onClick={() => setShowModal(true)} className="btn-secondary">
                  Create Task
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {filteredTasks.map(task => (
                <div 
                  key={task.task_id}
                  className={`card-trust border-l-4 ${getStatusClass(task.status)}`}
                  data-testid={`task-${task.task_id}`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-4">
                      {getStatusIcon(task.status)}
                      <div>
                        <h3 className="font-medium text-navy">
                          {task.task_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </h3>
                        {task.description && (
                          <p className="text-sm text-muted-foreground mt-1">{task.description}</p>
                        )}
                        <div className="flex items-center gap-4 mt-2">
                          <span className="font-mono text-xs text-muted-foreground">
                            Due: {formatDate(task.due_date)}
                          </span>
                          {task.completed_at && (
                            <span className="font-mono text-xs text-success">
                              Completed: {formatDate(task.completed_at)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {task.status !== 'completed' ? (
                        <Button 
                          onClick={() => handleCompleteTask(task.task_id)}
                          size="sm"
                          className="btn-primary"
                          data-testid={`complete-task-${task.task_id}`}
                        >
                          Complete
                        </Button>
                      ) : (
                        <Button 
                          onClick={() => handleUncompleteTask(task.task_id)}
                          size="sm"
                          variant="outline"
                          className="btn-secondary"
                        >
                          Undo
                        </Button>
                      )}
                      <Button 
                        onClick={() => handleDeleteTask(task.task_id)}
                        size="sm"
                        variant="ghost"
                        className="text-error hover:text-error hover:bg-error/10"
                      >
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
      <MobileBottomNav />

      {/* Create Task Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 w-full max-w-md corner-mark" data-testid="create-task-modal">
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-serif text-xl text-navy">Create Task</h2>
              <button onClick={() => setShowModal(false)} className="text-navy hover:text-gold">
                <X className="w-5 h-5" />
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
                  {TASK_TYPES.map(type => (
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
                <Button onClick={() => setShowModal(false)} variant="outline" className="flex-1 btn-secondary">
                  Cancel
                </Button>
                <Button onClick={handleCreateTask} className="flex-1 btn-primary" data-testid="submit-task-btn">
                  Create Task
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
