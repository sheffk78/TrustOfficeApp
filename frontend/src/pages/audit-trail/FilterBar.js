import { FILTER_OPTIONS } from './constants';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

export default function FilterBar({ filter, onChange }) {
  return (
    <Tabs value={filter} onValueChange={onChange} className="w-full">
      <TabsList className="mb-6 bg-muted/50 flex w-full gap-1 overflow-x-auto whitespace-nowrap">
        {FILTER_OPTIONS.map((opt) => (
          <TabsTrigger key={opt.value} value={opt.value} className="flex items-center gap-2">
            {opt.label}
            {opt.icon && <opt.icon className="w-4 h-4" />}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}