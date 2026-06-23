"""
Update test leads with course progress, activities, and notifications.
Run inside Railway container where MongoDB is accessible.
"""
import asyncio
import uuid
import os
import sys
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

from datetime import datetime, timezone, timedelta
from database import db

async def main():
    now = datetime.now(timezone.utc)
    
    # Update course progress for engaged leads
    updates = {
        'james.engaged@example.com': {'lessons_watched': 2, 'stage': 'engaged', 'last_login': (now - timedelta(days=1)).isoformat()},
        'lisa.hot@example.com': {'lessons_watched': 5, 'stage': 'engaged', 'last_login': (now - timedelta(hours=3)).isoformat()},
        'robert.idle@example.com': {'lessons_watched': 3, 'stage': 'engaged', 'last_login': (now - timedelta(days=5)).isoformat()},
        'amanda.call@example.com': {'lessons_watched': 1, 'stage': 'engaged', 'booked_call': True, 'booked_call_at': (now - timedelta(days=1)).isoformat(), 'last_login': (now - timedelta(days=1)).isoformat()},
        'carlos.call@example.com': {'booked_call': True, 'booked_call_at': (now - timedelta(hours=6)).isoformat()},
        'patricia.warm@example.com': {'stage': 'warm'},
        'david.pricing@example.com': {'stage': 'warm'},
    }
    
    for email, data in updates.items():
        data['updated_at'] = now.isoformat()
        result = await db.leads.update_one({'email': email}, {'$set': data})
        if result.modified_count > 0:
            print(f'  Updated {email}')
        else:
            lead = await db.leads.find_one({'email': email})
            if lead:
                print(f'  Found {email} but no changes needed')
            else:
                print(f'  NOT FOUND: {email}')
    
    # Add activity logs
    activities = [
        ('james.engaged@example.com', 'stage_change', 'Stage changed: new → engaged (watched 2 lessons)', now - timedelta(days=3)),
        ('james.engaged@example.com', 'email', 'Sent welcome email', now - timedelta(days=5)),
        ('lisa.hot@example.com', 'stage_change', 'Stage changed: new → engaged (watched 1 lesson)', now - timedelta(days=8)),
        ('lisa.hot@example.com', 'email', 'Sent welcome email', now - timedelta(days=10)),
        ('lisa.hot@example.com', 'email', 'Sent course nudge email', now - timedelta(days=6)),
        ('robert.idle@example.com', 'stage_change', 'Stage changed: new → engaged (watched 3 lessons)', now - timedelta(days=10)),
        ('robert.idle@example.com', 'email', 'Sent welcome email', now - timedelta(days=14)),
        ('amanda.call@example.com', 'booked_call', 'Booked a TrustOffice Discovery Call', now - timedelta(days=1)),
        ('amanda.call@example.com', 'email', 'Sent welcome email', now - timedelta(days=3)),
        ('carlos.call@example.com', 'booked_call', 'Booked a TrustOffice Discovery Call', now - timedelta(hours=6)),
        ('patricia.warm@example.com', 'email', 'Sent welcome email', now - timedelta(days=10)),
        ('david.pricing@example.com', 'email', 'Sent welcome email', now - timedelta(days=21)),
    ]
    
    for email, atype, content, ts in activities:
        lead = await db.leads.find_one({'email': email})
        if lead:
            await db.lead_activities.insert_one({
                'activity_id': f'act_{uuid.uuid4().hex[:12]}',
                'lead_id': lead['lead_id'],
                'action_type': atype,
                'content': content,
                'created_at': ts.isoformat(),
            })
    
    # Add notifications for booked calls
    for email, name in [('amanda.call@example.com', 'Amanda Foster'), ('carlos.call@example.com', 'Carlos Rivera')]:
        lead = await db.leads.find_one({'email': email})
        if lead:
            await db.notifications.insert_one({
                'notification_id': f'notif_{uuid.uuid4().hex[:12]}',
                'type': 'booked_call',
                'priority': 'high',
                'title': f'Discovery call booked: {name}',
                'body': 'Booked a TrustOffice Discovery Call',
                'lead_id': lead['lead_id'],
                'lead_email': email,
                'lead_name': name,
                'read': False,
                'created_at': now.isoformat(),
                'read_at': None,
            })
    
    # Add note to manual lead
    lead = await db.leads.find_one({'email': 'manual.lead@example.com'})
    if lead:
        await db.lead_activities.insert_one({
            'activity_id': f'act_{uuid.uuid4().hex[:12]}',
            'lead_id': lead['lead_id'],
            'action_type': 'note_added',
            'content': 'Referred by existing customer — follow up personally',
            'created_at': (now - timedelta(days=2)).isoformat(),
        })
    
    # Summary
    total = await db.leads.count_documents({})
    by_stage = {}
    for s in ['new','engaged','warm','converted','lost']:
        by_stage[s] = await db.leads.count_documents({'stage': s})
    notif_count = await db.notifications.count_documents({})
    print(f'\nTotal: {total} leads, {notif_count} notifications')
    for s,c in by_stage.items():
        print(f'  {s}: {c}')

asyncio.run(main())
