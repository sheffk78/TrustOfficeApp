"""
Email Templates for TrustOffice
Centralized email templates for easy editing
"""

from typing import Dict, Any
from datetime import datetime

# Base template style
BASE_STYLE = """
<style>
  body { font-family: 'Helvetica Neue', Arial, sans-serif; color: #333; line-height: 1.6; margin: 0; padding: 0; }
  .container { max-width: 600px; margin: 0 auto; padding: 20px; }
  .header { background-color: #010079; padding: 30px; text-align: center; }
  .header h1 { color: #D5AD36; margin: 0; font-size: 24px; }
  .header p { color: #ffffff; margin: 10px 0 0 0; font-size: 14px; }
  .content { padding: 30px; background-color: #ffffff; }
  .content h2 { color: #010079; margin-top: 0; }
  .button { display: inline-block; background-color: #010079; color: #ffffff; padding: 12px 24px; text-decoration: none; font-weight: bold; margin: 20px 0; }
  .button:hover { background-color: #0100a0; }
  .footer { background-color: #f5f5f5; padding: 20px; text-align: center; font-size: 12px; color: #666; }
  .task-card { background-color: #f9f9f9; border-left: 4px solid #D5AD36; padding: 15px; margin: 15px 0; }
  .task-card h3 { margin: 0 0 10px 0; color: #010079; }
  .task-card p { margin: 5px 0; }
  .alert { background-color: #fff3cd; border: 1px solid #ffc107; padding: 15px; margin: 15px 0; }
  .success { background-color: #d4edda; border: 1px solid #28a745; padding: 15px; margin: 15px 0; }
  .label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
  .value { font-size: 16px; color: #010079; font-weight: bold; }
</style>
"""

def _base_template(content: str, year: int = None) -> str:
    """Wrap content in base template structure"""
    if year is None:
        year = datetime.now().year
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {BASE_STYLE}
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>TrustOffice</h1>
      <p>Trust Governance Workspace</p>
    </div>
    <div class="content">
      {content}
    </div>
    <div class="footer">
      <p>© {year} TrustOffice. All rights reserved.</p>
      <p>This is an automated message from your trust governance system.</p>
    </div>
  </div>
</body>
</html>
"""

# ================== TEMPLATE DEFINITIONS ==================

TEMPLATES = {
    # Welcome / Onboarding Email
    "welcome": {
        "subject": "Welcome to TrustOffice - Let's Get Started",
        "html": lambda data: _base_template(f"""
            <h2>Welcome to TrustOffice, {data.get('user_name', 'there')}!</h2>
            <p>Thank you for joining TrustOffice – your trusted companion for managing trust governance with confidence and clarity.</p>
            
            <div class="success">
              <strong>Your account is ready!</strong> You now have access to powerful tools for tracking minutes, distributions, and maintaining governance health.
            </div>
            
            <h3>Get Started in 4 Easy Steps:</h3>
            <ol>
              <li><strong>Create Your First Trust</strong> – Set up your trust profile with basic information</li>
              <li><strong>Add Entities</strong> – Include any LLCs or related structures</li>
              <li><strong>Set Up Your Governance Calendar</strong> – Schedule important review dates</li>
              <li><strong>Generate Your First Minutes</strong> – Document your first meeting</li>
            </ol>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/dashboard" class="button">Go to Dashboard</a>
            </p>
            
            <p>If you have any questions, don't hesitate to reach out to our support team.</p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Welcome to TrustOffice, {data.get('user_name', 'there')}!

Thank you for joining TrustOffice – your trusted companion for managing trust governance with confidence and clarity.

Your account is ready! You now have access to powerful tools for tracking minutes, distributions, and maintaining governance health.

Get Started in 4 Easy Steps:
1. Create Your First Trust – Set up your trust profile with basic information
2. Add Entities – Include any LLCs or related structures
3. Set Up Your Governance Calendar – Schedule important review dates
4. Generate Your First Minutes – Document your first meeting

Go to Dashboard: {data.get('app_url', '#')}/dashboard

If you have any questions, don't hesitate to reach out to our support team.

Best regards,
The TrustOffice Team
        """
    },

    # Task Reminder Email
    "task_reminder": {
        "subject": lambda data: f"Reminder: {data.get('task_type', 'Task')} Due {data.get('due_date', 'Soon')}",
        "html": lambda data: _base_template(f"""
            <h2>Governance Task Reminder</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>This is a friendly reminder about an upcoming governance task for <strong>{data.get('trust_name', 'your trust')}</strong>.</p>
            
            <div class="task-card">
              <h3>{data.get('task_type', 'Governance Task').replace('_', ' ').title()}</h3>
              <p class="label">Due Date</p>
              <p class="value">{data.get('due_date', 'N/A')}</p>
              {f'<p>{data.get("description", "")}</p>' if data.get('description') else ''}
            </div>
            
            <div class="alert">
              <strong>Don't forget!</strong> Completing this task on time helps maintain your governance health score.
            </div>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/calendar" class="button">View Calendar</a>
            </p>
            
            <p>Best regards,<br>TrustOffice</p>
        """),
        "text": lambda data: f"""
Governance Task Reminder

Hi {data.get('user_name', 'there')},

This is a friendly reminder about an upcoming governance task for {data.get('trust_name', 'your trust')}.

Task: {data.get('task_type', 'Governance Task').replace('_', ' ').title()}
Due Date: {data.get('due_date', 'N/A')}
{data.get('description', '')}

Don't forget! Completing this task on time helps maintain your governance health score.

View Calendar: {data.get('app_url', '#')}/calendar

Best regards,
TrustOffice
        """
    },

    # Overdue Task Email
    "task_overdue": {
        "subject": lambda data: f"Action Required: Overdue Task for {data.get('trust_name', 'Your Trust')}",
        "html": lambda data: _base_template(f"""
            <h2 style="color: #dc3545;">Overdue Task Alert</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>A governance task for <strong>{data.get('trust_name', 'your trust')}</strong> is now overdue and requires your immediate attention.</p>
            
            <div class="task-card" style="border-left-color: #dc3545;">
              <h3>{data.get('task_type', 'Governance Task').replace('_', ' ').title()}</h3>
              <p class="label">Was Due</p>
              <p class="value" style="color: #dc3545;">{data.get('due_date', 'N/A')}</p>
              <p class="label">Days Overdue</p>
              <p class="value">{data.get('days_overdue', 0)} days</p>
            </div>
            
            <div class="alert" style="background-color: #f8d7da; border-color: #dc3545;">
              <strong>Impact:</strong> Your governance health score is affected by overdue tasks. Complete this task to improve your score.
            </div>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/calendar" class="button" style="background-color: #dc3545;">Complete Task Now</a>
            </p>
            
            <p>Best regards,<br>TrustOffice</p>
        """),
        "text": lambda data: f"""
OVERDUE TASK ALERT

Hi {data.get('user_name', 'there')},

A governance task for {data.get('trust_name', 'your trust')} is now overdue and requires your immediate attention.

Task: {data.get('task_type', 'Governance Task').replace('_', ' ').title()}
Was Due: {data.get('due_date', 'N/A')}
Days Overdue: {data.get('days_overdue', 0)} days

Impact: Your governance health score is affected by overdue tasks. Complete this task to improve your score.

Complete Task Now: {data.get('app_url', '#')}/calendar

Best regards,
TrustOffice
        """
    },

    # New Minutes Notification
    "minutes_created": {
        "subject": lambda data: f"New Minutes Recorded: {data.get('minutes_type', 'Meeting')} - {data.get('trust_name', '')}",
        "html": lambda data: _base_template(f"""
            <h2>New Minutes Recorded</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>New meeting minutes have been recorded for <strong>{data.get('trust_name', 'your trust')}</strong>.</p>
            
            <div class="success">
              <strong>Minutes Summary</strong>
            </div>
            
            <table style="width: 100%; border-collapse: collapse;">
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">
                  <span class="label">Type</span><br>
                  <span class="value">{data.get('minutes_type', 'Meeting').replace('_', ' ').title()}</span>
                </td>
                <td style="padding: 10px; border-bottom: 1px solid #eee;">
                  <span class="label">Meeting Date</span><br>
                  <span class="value">{data.get('meeting_date', 'N/A')}</span>
                </td>
              </tr>
              <tr>
                <td colspan="2" style="padding: 10px;">
                  <span class="label">Participants</span><br>
                  <span>{data.get('participants', 'N/A')}</span>
                </td>
              </tr>
            </table>
            
            {f'<p><strong>Key Decisions:</strong><br>{data.get("decisions", "")}</p>' if data.get('decisions') else ''}
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/minutes" class="button">View Minutes</a>
            </p>
            
            <p>Best regards,<br>TrustOffice</p>
        """),
        "text": lambda data: f"""
New Minutes Recorded

Hi {data.get('user_name', 'there')},

New meeting minutes have been recorded for {data.get('trust_name', 'your trust')}.

Minutes Summary:
- Type: {data.get('minutes_type', 'Meeting').replace('_', ' ').title()}
- Meeting Date: {data.get('meeting_date', 'N/A')}
- Participants: {data.get('participants', 'N/A')}

{f"Key Decisions: {data.get('decisions', '')}" if data.get('decisions') else ''}

View Minutes: {data.get('app_url', '#')}/minutes

Best regards,
TrustOffice
        """
    },

    # New Distribution Notification
    "distribution_created": {
        "subject": lambda data: f"New Distribution Logged: ${data.get('amount', '0')} - {data.get('trust_name', '')}",
        "html": lambda data: _base_template(f"""
            <h2>New Distribution Logged</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>A new distribution has been logged for <strong>{data.get('trust_name', 'your trust')}</strong>.</p>
            
            <div class="task-card">
              <h3>Distribution Details</h3>
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Amount</span></td>
                  <td style="padding: 5px 0;"><span class="value">${data.get('amount', '0'):,.2f}</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Beneficiary</span></td>
                  <td style="padding: 5px 0;">{data.get('beneficiary', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Category</span></td>
                  <td style="padding: 5px 0;">{data.get('category', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Date</span></td>
                  <td style="padding: 5px 0;">{data.get('date', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Status</span></td>
                  <td style="padding: 5px 0;"><strong>{data.get('status', 'Pending').upper()}</strong></td>
                </tr>
              </table>
            </div>
            
            {f'<div class="alert"><strong>Action Required:</strong> This distribution requires approval.</div>' if data.get('status') == 'review' else ''}
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/distributions" class="button">View Distributions</a>
            </p>
            
            <p>Best regards,<br>TrustOffice</p>
        """),
        "text": lambda data: f"""
New Distribution Logged

Hi {data.get('user_name', 'there')},

A new distribution has been logged for {data.get('trust_name', 'your trust')}.

Distribution Details:
- Amount: ${data.get('amount', '0'):,.2f}
- Beneficiary: {data.get('beneficiary', 'N/A')}
- Category: {data.get('category', 'N/A')}
- Date: {data.get('date', 'N/A')}
- Status: {data.get('status', 'Pending').upper()}

{'Action Required: This distribution requires approval.' if data.get('status') == 'review' else ''}

View Distributions: {data.get('app_url', '#')}/distributions

Best regards,
TrustOffice
        """
    },

    # Distribution Approved Notification
    "distribution_approved": {
        "subject": lambda data: f"Distribution Approved: ${data.get('amount', '0')} for {data.get('beneficiary', '')}",
        "html": lambda data: _base_template(f"""
            <h2>Distribution Approved</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>A distribution for <strong>{data.get('trust_name', 'your trust')}</strong> has been approved.</p>
            
            <div class="success">
              <h3 style="margin: 0; color: #155724;">✓ Approved</h3>
            </div>
            
            <div class="task-card">
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Amount</span></td>
                  <td style="padding: 5px 0;"><span class="value">${data.get('amount', '0'):,.2f}</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Beneficiary</span></td>
                  <td style="padding: 5px 0;">{data.get('beneficiary', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Approved By</span></td>
                  <td style="padding: 5px 0;">{data.get('approved_by', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Approval Date</span></td>
                  <td style="padding: 5px 0;">{data.get('approval_date', 'N/A')}</td>
                </tr>
              </table>
            </div>
            
            <p>Solvency Confirmed: ✓<br>Recusal Acknowledged: ✓</p>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/distributions" class="button">View Distributions</a>
            </p>
            
            <p>Best regards,<br>TrustOffice</p>
        """),
        "text": lambda data: f"""
Distribution Approved

Hi {data.get('user_name', 'there')},

A distribution for {data.get('trust_name', 'your trust')} has been approved.

Distribution Details:
- Amount: ${data.get('amount', '0'):,.2f}
- Beneficiary: {data.get('beneficiary', 'N/A')}
- Approved By: {data.get('approved_by', 'N/A')}
- Approval Date: {data.get('approval_date', 'N/A')}

Solvency Confirmed: Yes
Recusal Acknowledged: Yes

View Distributions: {data.get('app_url', '#')}/distributions

Best regards,
TrustOffice
        """
    }
}


def get_template(template_name: str) -> Dict[str, Any]:
    """Get a template by name"""
    if template_name not in TEMPLATES:
        raise ValueError(f"Template '{template_name}' not found")
    return TEMPLATES[template_name]


def render_template(template_name: str, data: Dict[str, Any]) -> Dict[str, str]:
    """
    Render a template with data.
    Returns dict with 'subject', 'html', and 'text' keys.
    """
    template = get_template(template_name)
    
    # Render subject (can be string or function)
    if callable(template["subject"]):
        subject = template["subject"](data)
    else:
        subject = template["subject"]
    
    # Render HTML body
    html = template["html"](data)
    
    # Render text body
    text = template["text"](data)
    
    return {
        "subject": subject,
        "html": html,
        "text": text
    }
