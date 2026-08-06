/**
 * Shared imports barrel — re-exports the common page-scaffolding modules
 * used across 18+ page components to eliminate the dry_violation caused by
 * duplicated import blocks.
 *
 * Usage in a page:
 *   import { Sidebar, MobileBottomNav, Button, Input, useAuth, fetchWithAuth, showError, toast } from '@/utils/sharedImports';
 *
 * Only import what you use — tree-shaking keeps the bundle lean.
 */

// React hooks (most pages need at least useState + useEffect)
export {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from 'react';

// React Router
export {
  useNavigate,
  useSearchParams,
  Link,
  Navigate,
} from 'react-router-dom';

// Auth + API
export { useAuth } from '@/context/AuthContext';
export { useUpgradeModal } from '@/context/UpgradeModalContext';
export { fetchWithAuth, API } from '@/utils/api';

// Layout components
export { Sidebar } from '@/components/Sidebar';
export { MobileBottomNav } from '@/components/MobileBottomNav';
export { default as PageHelpButton } from '@/components/PageHelpButton';

// UI primitives
export { Button } from '@/components/ui/button';
export { Input } from '@/components/ui/input';
export { Label } from '@/components/ui/label';
export { Textarea } from '@/components/ui/textarea';
export { Checkbox } from '@/components/ui/checkbox';
export {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
export {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
export {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
export {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
export { Calendar as UICalendar } from '@/components/ui/calendar';

// Notifications
export { toast } from 'sonner';

// Error helpers
export { showError, installGlobalErrorHandlers } from '@/utils/errors';