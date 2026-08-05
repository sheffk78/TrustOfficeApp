/**
 * MeetingInfoFields — common "Meeting Information" card used by every template.
 * Extracted from MinutesTemplateFormPage to reduce the main component's CCN.
 *
 * Props:
 *  - formData, setFormData
 *  - templateType (controls whether the time field is shown)
 *  - trustees_present handlers: onAddTrustee, onRemoveTrustee, onTrusteeChange
 */
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Plus, Trash2 } from 'lucide-react';

export const MeetingInfoFields = ({
  formData,
  setFormData,
  templateType,
  trusteesPresent,
  onAddTrustee,
  onRemoveTrustee,
  onTrusteeChange,
}) => {
  const showMeetingTime = templateType !== 'initial_trustee_meeting';
  const isInPerson = formData.meeting_type === 'in_person';
  const canRemoveTrustee = trusteesPresent.length > 1;

  return (
    <div className="card-trust corner-mark p-6">
      <h2 className="font-serif text-xl text-navy mb-4 pb-2 border-b border-navy/20">Meeting Information</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <div>
          <Label className="label-trust">Minute Number</Label>
          <Input
            value={formData.minute_number}
            onChange={(e) => setFormData({ ...formData, minute_number: e.target.value })}
            className="mt-1 input-trust"
            placeholder="e.g., 2024-001"
          />
        </div>
        <div>
          <Label className="label-trust">Meeting Date</Label>
          <Input
            type="date"
            value={formData.meeting_date}
            onChange={(e) => setFormData({ ...formData, meeting_date: e.target.value })}
            className="mt-1 input-trust"
          />
        </div>
        {showMeetingTime && (
          <div>
            <Label className="label-trust">Meeting Time</Label>
            <Input
              type="time"
              value={formData.meeting_time}
              onChange={(e) => setFormData({ ...formData, meeting_time: e.target.value })}
              className="mt-1 input-trust"
            />
          </div>
        )}
        <div>
          <Label className="label-trust">Meeting Type</Label>
          <Select value={formData.meeting_type} onValueChange={(v) => setFormData({ ...formData, meeting_type: v })}>
            <SelectTrigger className="mt-1 h-10">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="unanimous_written_consent">Unanimous Written Consent</SelectItem>
              <SelectItem value="in_person">In Person</SelectItem>
              <SelectItem value="video_conference">Video/Phone Conference</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {isInPerson && (
          <div className="md:col-span-2">
            <Label className="label-trust">Meeting Location</Label>
            <Input
              value={formData.meeting_location}
              onChange={(e) => setFormData({ ...formData, meeting_location: e.target.value })}
              className="mt-1 input-trust"
              placeholder="123 Main Street, City, State"
            />
          </div>
        )}
        <div className="md:col-span-2">
          <Label className="label-trust">Trust Formation Date</Label>
          <Input
            type="date"
            value={formData.trust_formation_date}
            onChange={(e) => setFormData({ ...formData, trust_formation_date: e.target.value })}
            className="mt-1 input-trust"
          />
        </div>
      </div>

      {/* Trustees Present */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-2">
          <Label className="label-trust">Trustees Present</Label>
          <Button type="button" variant="ghost" size="sm" onClick={onAddTrustee}>
            <Plus className="w-4 h-4 mr-1" />
            Add Trustee
          </Button>
        </div>
        <div className="space-y-2">
          {trusteesPresent.map((trustee, index) => (
            <div key={index} className="flex gap-2">
              <Input
                value={trustee}
                onChange={(e) => onTrusteeChange(index, e.target.value)}
                className="input-trust"
                placeholder="Trustee name"
              />
              {canRemoveTrustee && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10 shrink-0 text-muted-foreground hover:text-red-600 hover:bg-red-50"
                  onClick={() => onRemoveTrustee(index)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};