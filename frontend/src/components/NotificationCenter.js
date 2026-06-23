import { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, CheckCheck, RefreshCw } from 'lucide-react';
import { fetchWithAuth } from '@/utils/api';

const NOTIFICATION_ICONS = {
  new_lead: '🆕',
  lead_stage_change: '🔄',
  booked_call: '📞',
  lead_converted: '✅',
  task_overdue: '⏰',
};

function relativeTime(isoString) {
  if (!isoString) return '';
  const now = new Date();
  const date = new Date(isoString);
  const diffMs = now - date;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays === 1) return 'Yesterday';
  return `${diffDays}d ago`;
}

export default function NotificationCenter({ onNotificationClick }) {
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const prevCountRef = useRef(null); // null = initial load not done yet
  const dropdownRef = useRef(null);

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchWithAuth('/admin/notifications?limit=20');
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.notifications);
        const prevCount = prevCountRef.current;
        prevCountRef.current = data.unread_count;
        setUnreadCount(data.unread_count);

        // Browser push notification when count increases and tab is hidden
        // prevCount === null means initial load — skip push for that
        if (prevCount !== null && data.unread_count > prevCount && document.hidden) {
          const latest = data.notifications.find(n => !n.read);
          if (latest && 'Notification' in window && Notification.permission === 'granted') {
            new Notification('TrustOffice: ' + latest.title, {
              body: latest.body,
              icon: '/assets/trustoffice-logo.svg',
              tag: latest.notification_id,
            });
          }
        }
      }
    } catch (e) {
      console.error('Failed to fetch notifications:', e);
    }
    setLoading(false);
  }, []);

  // Poll every 30 seconds
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Request notification permission on bell click (browser requires user gesture)
  const handleBellClick = () => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
    setOpen(!open);
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [open]);

  const handleMarkAllRead = async () => {
    try {
      const res = await fetchWithAuth('/admin/notifications/mark-all-read', { method: 'POST' });
      if (res.ok) {
        setUnreadCount(0);
        setNotifications(n => n.map(x => ({ ...x, read: true })));
      } else {
        console.error('Failed to mark all read');
      }
    } catch (e) {
      console.error('Failed to mark all read:', e);
    }
  };

  const handleNotificationClick = async (n) => {
    if (!n.read) {
      try {
        await fetchWithAuth(`/admin/notifications/${n.notification_id}/read`, { method: 'POST' });
        setNotifications(prev =>
          prev.map(x => x.notification_id === n.notification_id ? { ...x, read: true } : x)
        );
        setUnreadCount(prev => Math.max(0, prev - 1));
      } catch (e) {
        console.error('Failed to mark notification read:', e);
      }
    }
    setOpen(false);
    if (onNotificationClick) {
      onNotificationClick(n);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={handleBellClick}
        className="relative p-2 text-white/60 hover:text-white transition-colors"
        title="Notifications"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
        aria-expanded={open}
        data-testid="notification-bell"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-rust text-white text-[10px] font-mono rounded-full w-5 h-5 flex items-center justify-center">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute left-0 bottom-full mb-2 w-96 bg-white border border-navy/10 shadow-lg z-50"
          role="menu"
        >
          {/* Header */}
          <div className="flex items-center justify-between p-3 border-b border-navy/10">
            <span className="label-trust text-navy">Notifications</span>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchNotifications}
                className="text-navy/40 hover:text-navy transition-colors"
                title="Refresh"
                aria-label="Refresh notifications"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="flex items-center gap-1 text-xs text-navy/60 hover:text-navy transition-colors"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Mark all read
                </button>
              )}
            </div>
          </div>

          {/* List */}
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-sm text-navy/40">
                No notifications yet
              </div>
            ) : (
              notifications.map(n => (
                <div
                  key={n.notification_id || n.created_at}
                  className={`p-3 border-b border-navy/5 cursor-pointer hover:bg-navy/5 transition-colors ${
                    !n.read ? 'bg-gold/5' : ''
                  }`}
                  onClick={() => handleNotificationClick(n)}
                  role="menuitem"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleNotificationClick(n); }}
                >
                  <div className="flex items-start gap-3">
                    <span className="text-base flex-shrink-0 mt-0.5">
                      {NOTIFICATION_ICONS[n.type] || '📌'}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <p className={`text-sm ${n.read ? 'text-navy/70' : 'font-medium text-navy'}`}>
                          {n.title}
                        </p>
                        {!n.read && (
                          <div className="w-2 h-2 bg-rust rounded-full flex-shrink-0 mt-1.5" />
                        )}
                      </div>
                      <p className="text-xs text-navy/60 mt-0.5 line-clamp-2">{n.body}</p>
                      <p className="text-[10px] text-navy/40 mt-1 font-mono">
                        {relativeTime(n.created_at)}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
