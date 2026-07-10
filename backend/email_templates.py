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
      <p>&copy; {year} TrustOffice. All rights reserved.</p>
      <p>This is an automated message from your trust governance system.</p>
    </div>
  </div>
</body>
</html>
"""


def get_trust_limit_text(plan_type: str, legacy_trust_limit: int | None = None) -> str:
    """
    Return the tier-aware trust limit text for subscription emails.

    Tiers:
      - trustee:  '1 trust or entity'
      - estate:  'Up to 5 trusts & entities'
      - advisor: 'Unlimited trusts & entities'
      - Legacy grandfathered (monthly/annual with legacy_trust_limit=10):
          'Up to 10 trusts & entities (grandfathered)'
    """
    pt = (plan_type or "").lower().strip()

    # Grandfathered users (any tier with legacy_trust_limit > 1) get special text
    if legacy_trust_limit and legacy_trust_limit > 1:
        return f"Up to {legacy_trust_limit} trusts & entities (grandfathered)"

    if pt == "trustee":
        return "1 trust or entity"
    elif pt == "estate":
        return "Up to 5 trusts & entities"
    elif pt == "advisor":
        return "Unlimited trusts & entities"
    elif pt in ("monthly", "annual"):
        # Legacy plans without explicit limit
        return "Up to 10 trusts & entities (grandfathered)"
    else:
        # Unknown plan — use conservative default
        return "Up to 10 trusts & entities"

# ================== TEMPLATE DEFINITIONS ==================

TEMPLATES = {
    # Password Reset Email
    "password_reset": {
        "subject": "Reset Your TrustOffice Password",
        "html": lambda data: _base_template(f"""
            <h2>Password Reset Request</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>We received a request to reset your TrustOffice password. Click the button below to create a new password:</p>
            
            <p style="text-align: center; margin: 30px 0;">
              <a href="{data.get('reset_url', '#')}" class="button">Reset Password</a>
            </p>
            
            <div class="alert">
              <strong>This link expires in 1 hour.</strong> If you didn't request a password reset, you can safely ignore this email.
            </div>
            
            <p style="font-size: 12px; color: #666;">
              If the button doesn't work, copy and paste this link into your browser:<br>
              <span style="word-break: break-all;">{data.get('reset_url', '#')}</span>
            </p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Password Reset Request

Hi {data.get('user_name', 'there')},

We received a request to reset your TrustOffice password. 

Reset your password here: {data.get('reset_url', '#')}

This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email.

Best regards,
The TrustOffice Team
        """
    },

    # Lead Welcome Email — sent when someone signs up for Trustee 101 or downloads a checklist
    "lead_welcome": {
        "subject": lambda data: f"Welcome to Trustee 101, {data.get('name', 'there')}!",
        "html": lambda data: _base_template(f"""
            <h2>Welcome to Trustee 101 🎉</h2>
            <p>Hi {data.get('name', 'there')},</p>
            <p>Thanks for signing up! You now have access to <strong>Trustee 101</strong> — a free 9-lesson course designed to help you navigate your role as a trustee with confidence.</p>

            <h3>Your First Lesson</h3>
            <p>Start with <strong>Lesson 1: What Is a Trust?</strong> — a 7-minute overview that lays the foundation for everything that follows.</p>

            <p style="text-align: center; margin: 30px 0;">
              <a href="{data.get('course_url', '#')}" class="button">Start Lesson 1</a>
            </p>

            <h3>What You'll Learn</h3>
            <ul>
                <li>The trustee's role and legal duties</li>
                <li>Your first 7 days as a trustee</li>
                <li>HEMS — the standard for trust distributions</li>
                <li>The commingling trap (and how to avoid it)</li>
                <li>Trust taxes, investments, and beneficiary communication</li>
            </ul>

            <p>Each lesson takes 5–16 minutes. Go at your own pace.</p>

            <p>If you ever have questions, just reply to this email.</p>

            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Welcome to Trustee 101!

Hi {data.get('name', 'there')},

Thanks for signing up! You now have access to Trustee 101 — a free 9-lesson course designed to help you navigate your role as a trustee with confidence.

Start with Lesson 1: What Is a Trust? — a 7-minute overview.

Start here: {data.get('course_url', '#')}

What You'll Learn:
- The trustee's role and legal duties
- Your first 7 days as a trustee
- HEMS — the standard for trust distributions
- The commingling trap (and how to avoid it)
- Trust taxes, investments, and beneficiary communication

Each lesson takes 5-16 minutes. Go at your own pace.

Best regards,
The TrustOffice Team
""",
    },

    # Lead Re-engagement Email — sent 3 days after capture if no lessons watched
    "lead_reengagement": {
        "subject": lambda data: f"Your first lesson is waiting, {data.get('name', 'there')}",
        "html": lambda data: _base_template(f"""
            <h2>Your First Lesson Is Waiting</h2>
            <p>Hi {data.get('name', 'there')},</p>
            <p>You signed up for <strong>Trustee 101</strong> a few days ago, but we noticed you haven't started your first lesson yet.</p>

            <p>No pressure — but the first lesson (<strong>What Is a Trust?</strong>) only takes 7 minutes, and it's the foundation for everything else.</p>

            <p style="text-align: center; margin: 30px 0;">
              <a href="{data.get('course_url', '#')}" class="button">Watch Lesson 1 Now</a>
            </p>

            <p>Here's a quick preview of what you'll learn:</p>
            <ul>
                <li>What a trust actually is (in plain English)</li>
                <li>Why trustees have legal duties — and what they are</li>
                <li>How to avoid the most common trustee mistakes</li>
            </ul>

            <p>If you have questions or need help getting started, just reply to this email.</p>

            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Your First Lesson Is Waiting

Hi {data.get('name', 'there')},

You signed up for Trustee 101 a few days ago, but we noticed you haven't started your first lesson yet.

No pressure — but the first lesson (What Is a Trust?) only takes 7 minutes, and it's the foundation for everything else.

Watch Lesson 1 Now: {data.get('course_url', '#')}

Here's a quick preview:
- What a trust actually is (in plain English)
- Why trustees have legal duties — and what they are
- How to avoid the most common trustee mistakes

Best regards,
The TrustOffice Team
""",
    },

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

    # Welcome + Set Password Email (for admin-created accounts)
    "welcome_set_password": {
        "subject": "Welcome to TrustOffice - Set Up Your Account",
        "html": lambda data: _base_template(f"""
            <h2>Welcome to TrustOffice, {data.get('user_name', 'there')}!</h2>
            <p>An account has been created for you on TrustOffice — your trusted companion for managing trust governance with confidence and clarity.</p>
            
            <div class="success">
              <strong>Your account is ready!</strong> To get started, you need to set your password.
            </div>
            
            <p style="text-align: center; margin: 30px 0;">
              <a href="{data.get('set_password_url', '#')}" class="button">Set Your Password</a>
            </p>
            
            <div class="alert">
              <strong>This link expires in 24 hours.</strong> After setting your password, you can log in and start managing your trusts.
            </div>
            
            <h3>What you can do with TrustOffice:</h3>
            <ul>
              <li><strong>Track Minutes</strong> — Document trust meetings and decisions</li>
              <li><strong>Manage Distributions</strong> — Record and approve trust distributions</li>
              <li><strong>Governance Calendar</strong> — Stay on top of important dates</li>
              <li><strong>Compliance Dashboard</strong> — Monitor trust health at a glance</li>
            </ul>
            
            <p style="font-size: 12px; color: #666;">
              If the button doesn't work, copy and paste this link into your browser:<br>
              <span style="word-break: break-all;">{data.get('set_password_url', '#')}</span>
            </p>
            
            <p>If you have any questions, don't hesitate to reach out to our support team.</p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Welcome to TrustOffice, {data.get('user_name', 'there')}!

An account has been created for you on TrustOffice — your trusted companion for managing trust governance.

To get started, set your password here: {data.get('set_password_url', '#')}

This link expires in 24 hours. After setting your password, you can log in and start managing your trusts.

What you can do with TrustOffice:
- Track Minutes — Document trust meetings and decisions
- Manage Distributions — Record and approve trust distributions
- Governance Calendar — Stay on top of important dates
- Compliance Dashboard — Monitor trust health at a glance

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
            
            {'<div class="alert"><strong>Action Required:</strong> This distribution requires approval.</div>' if data.get('status') == 'review' else ''}
            
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
    },

    # Subscription Activated
    "subscription_activated": {
        "subject": "Welcome to TrustOffice Pro!",
        "html": lambda data: _base_template(f"""
            <h2>Your Subscription is Active!</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>Thank you for subscribing to TrustOffice! Your <strong>{data.get('plan_type', 'subscription').title()}</strong> plan is now active.</p>
            
            <div class="success">
              <h3 style="margin: 0; color: #155724;">✓ Subscription Confirmed</h3>
            </div>
            
            <div class="task-card">
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Plan</span></td>
                  <td style="padding: 5px 0;"><span class="value">{data.get('plan_type', 'Monthly').title()} Plan</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Next Billing Date</span></td>
                  <td style="padding: 5px 0;">{data.get('next_billing_date', 'N/A')}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Amount</span></td>
                  <td style="padding: 5px 0;">${data.get('amount', '79')}/{'year' if data.get('plan_type') == 'annual' else 'month'}</td>
                </tr>
              </table>
            </div>
            
            <h3>You now have full access to:</h3>
            <ul>
              <li>{get_trust_limit_text(data.get('plan_type', ''), data.get('legacy_trust_limit'))}</li>
              <li>Governance health tracking</li>
              <li>Minutes & distribution management</li>
              <li>PDF generation & CSV export</li>
              <li>Priority support</li>
            </ul>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/dashboard" class="button">Go to Dashboard</a>
            </p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Your Subscription is Active!

Hi {data.get('user_name', 'there')},

Thank you for subscribing to TrustOffice! Your {data.get('plan_type', 'subscription').title()} plan is now active.

Subscription Details:
- Plan: {data.get('plan_type', 'Monthly').title()} Plan
- Next Billing Date: {data.get('next_billing_date', 'N/A')}
- Amount: ${data.get('amount', '79')}/{'year' if data.get('plan_type') == 'annual' else 'month'}

You now have full access to:
- {get_trust_limit_text(data.get('plan_type', ''), data.get('legacy_trust_limit'))}
- Governance health tracking
- Minutes & distribution management
- PDF generation & CSV export
- Priority support

Go to Dashboard: {data.get('app_url', '#')}/dashboard

Best regards,
The TrustOffice Team
        """
    },

    # Subscription Canceled
    "subscription_canceled": {
        "subject": "Your TrustOffice Subscription Has Been Canceled",
        "html": lambda data: _base_template(f"""
            <h2>Subscription Canceled</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>We're sorry to see you go. Your TrustOffice subscription has been set to cancel.</p>
            
            <div class="alert">
              <strong>Access Until:</strong> {data.get('access_until', 'N/A')}<br>
              You'll retain full access to TrustOffice until this date.
            </div>
            
            <h3>What happens next:</h3>
            <ul>
              <li>Your data will be safely retained for 90 days after cancellation</li>
              <li>You can resubscribe at any time to regain access</li>
              <li>Download your data before your access expires</li>
            </ul>
            
            <p><strong>Changed your mind?</strong> You can reactivate your subscription at any time before {data.get('access_until', 'your access expires')}.</p>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/settings/billing" class="button">Manage Subscription</a>
            </p>
            
            <p>We'd love to hear your feedback. Reply to this email to let us know how we can improve.</p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Subscription Canceled

Hi {data.get('user_name', 'there')},

We're sorry to see you go. Your TrustOffice subscription has been set to cancel.

Access Until: {data.get('access_until', 'N/A')}
You'll retain full access to TrustOffice until this date.

What happens next:
- Your data will be safely retained for 90 days after cancellation
- You can resubscribe at any time to regain access
- Download your data before your access expires

Changed your mind? You can reactivate your subscription at any time before {data.get('access_until', 'your access expires')}.

Manage Subscription: {data.get('app_url', '#')}/settings/billing

We'd love to hear your feedback. Reply to this email to let us know how we can improve.

Best regards,
The TrustOffice Team
        """
    },

    # Subscription Renewed
    "subscription_renewed": {
        "subject": "Your TrustOffice Subscription Has Been Renewed",
        "html": lambda data: _base_template(f"""
            <h2>Subscription Renewed</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>Great news! Your TrustOffice subscription has been successfully renewed.</p>
            
            <div class="success">
              <h3 style="margin: 0; color: #155724;">✓ Payment Successful</h3>
            </div>
            
            <div class="task-card">
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Plan</span></td>
                  <td style="padding: 5px 0;"><span class="value">{data.get('plan_type', 'Monthly').title()} Plan</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Amount Charged</span></td>
                  <td style="padding: 5px 0;"><span class="value">${data.get('amount', '0')}</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Next Billing Date</span></td>
                  <td style="padding: 5px 0;">{data.get('next_billing_date', 'N/A')}</td>
                </tr>
              </table>
            </div>
            
            <p>Thank you for your continued trust in TrustOffice!</p>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/settings/billing" class="button">View Billing Details</a>
            </p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Subscription Renewed

Hi {data.get('user_name', 'there')},

Great news! Your TrustOffice subscription has been successfully renewed.

Renewal Details:
- Plan: {data.get('plan_type', 'Monthly').title()} Plan
- Amount Charged: ${data.get('amount', '0')}
- Next Billing Date: {data.get('next_billing_date', 'N/A')}

Thank you for your continued trust in TrustOffice!

View Billing Details: {data.get('app_url', '#')}/settings/billing

Best regards,
The TrustOffice Team
        """
    },

    # Payment Failed
    "payment_failed": {
        "subject": "Action Required: Payment Failed for TrustOffice",
        "html": lambda data: _base_template(f"""
            <h2 style="color: #dc3545;">Payment Failed</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>We were unable to process your payment for TrustOffice.</p>
            
            <div class="alert" style="background-color: #f8d7da; border-color: #dc3545;">
              <strong>Action Required:</strong> Please update your payment method to continue using TrustOffice.
            </div>
            
            <div class="task-card" style="border-left-color: #dc3545;">
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Amount Due</span></td>
                  <td style="padding: 5px 0;"><span class="value" style="color: #dc3545;">${data.get('amount', '0')}</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Retry Date</span></td>
                  <td style="padding: 5px 0;">{data.get('retry_date', 'Soon')}</td>
                </tr>
              </table>
            </div>
            
            <h3>Common reasons for payment failure:</h3>
            <ul>
              <li>Expired card</li>
              <li>Insufficient funds</li>
              <li>Bank declined transaction</li>
            </ul>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/settings/billing" class="button" style="background-color: #dc3545;">Update Payment Method</a>
            </p>
            
            <p>If you continue to have issues, please contact your bank or our support team.</p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
PAYMENT FAILED

Hi {data.get('user_name', 'there')},

We were unable to process your payment for TrustOffice.

Action Required: Please update your payment method to continue using TrustOffice.

Payment Details:
- Amount Due: ${data.get('amount', '0')}
- Retry Date: {data.get('retry_date', 'Soon')}

Common reasons for payment failure:
- Expired card
- Insufficient funds
- Bank declined transaction

Update Payment Method: {data.get('app_url', '#')}/settings/billing

If you continue to have issues, please contact your bank or our support team.

Best regards,
The TrustOffice Team
        """
    },

    # Subscription Upgraded
    "subscription_upgraded": {
        "subject": "Your TrustOffice Plan Has Been Upgraded!",
        "html": lambda data: _base_template(f"""
            <h2>Plan Upgraded!</h2>
            <p>Hi {data.get('user_name', 'there')},</p>
            <p>Your TrustOffice plan has been successfully upgraded to <strong>{data.get('new_plan', 'Annual').title()}</strong>!</p>
            
            <div class="success">
              <h3 style="margin: 0; color: #155724;">✓ Upgrade Complete</h3>
            </div>
            
            <div class="task-card">
              <table style="width: 100%;">
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Previous Plan</span></td>
                  <td style="padding: 5px 0;">{data.get('old_plan', 'Monthly').title()}</td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">New Plan</span></td>
                  <td style="padding: 5px 0;"><span class="value">{data.get('new_plan', 'Annual').title()}</span></td>
                </tr>
                <tr>
                  <td style="padding: 5px 0;"><span class="label">Annual Savings</span></td>
                  <td style="padding: 5px 0;"><span class="value" style="color: #28a745;">$158/year</span></td>
                </tr>
              </table>
            </div>
            
            <p>Thank you for your continued commitment to good governance!</p>
            
            <p style="text-align: center;">
              <a href="{data.get('app_url', '#')}/settings/billing" class="button">View Subscription</a>
            </p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Plan Upgraded!

Hi {data.get('user_name', 'there')},

Your TrustOffice plan has been successfully upgraded to {data.get('new_plan', 'Annual').title()}!

Upgrade Details:
- Previous Plan: {data.get('old_plan', 'Monthly').title()}
- New Plan: {data.get('new_plan', 'Annual').title()}
- Annual Savings: $158/year

Thank you for your continued commitment to good governance!

View Subscription: {data.get('app_url', '#')}/settings/billing

Best regards,
The TrustOffice Team
        """
    },

    # Certificate Notice to Beneficiary
    "certificate_notice": {
        "subject": lambda data: f"Certificate of Trust Units — {data.get('trust_name', 'Your Trust')}",
        "html": lambda data: _base_template(f"""
            <h2>Certificate of Trust Units</h2>
            <p>Dear {data.get('beneficiary_name', 'Beneficiary')},</p>
            <p>This certificate confirms your unit allocation in the <strong>{data.get('trust_name', 'Trust')}</strong>.</p>

            <div class="task-card">
                <h3>Certificate Details</h3>
                <p><span class="label">Certificate Number:</span> <span class="value">{data.get('certificate_number', 'N/A')}</span></p>
                <p><span class="label">Holder:</span> <span class="value">{data.get('beneficiary_name', 'N/A')}</span></p>
                <p><span class="label">Units Allocated:</span> <span class="value">{data.get('units', 'N/A'):,}</span></p>
                <p><span class="label">Unit Label:</span> <span class="value">{data.get('unit_label', 'Certificate Unit')}</span></p>
                <p><span class="label">Percentage of Total:</span> <span class="value">{data.get('percentage', 0):.2f}%</span></p>
                <p><span class="label">Issue Date:</span> <span class="value">{data.get('issue_date', 'N/A')}</span></p>
                {f'<p><span class="label">Notes:</span> <span class="value">{data.get("notes", "")}</span></p>' if data.get('notes') else ''}
            </div>

            <p>This certificate was issued by the trustee of the trust. If you have questions about your unit allocation, please contact the trustee directly.</p>

            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Certificate of Trust Units — {data.get('trust_name', 'Your Trust')}

Dear {data.get('beneficiary_name', 'Beneficiary')},

This certificate confirms your unit allocation in the {data.get('trust_name', 'Trust')}.

Certificate Details:
- Certificate Number: {data.get('certificate_number', 'N/A')}
- Holder: {data.get('beneficiary_name', 'N/A')}
- Units Allocated: {data.get('units', 0):,}
- Unit Label: {data.get('unit_label', 'Certificate Unit')}
- Percentage of Total: {data.get('percentage', 0):.2f}%
- Issue Date: {data.get('issue_date', 'N/A')}
{'- Notes: ' + data.get('notes', '') if data.get('notes') else ''}

This certificate was issued by the trustee of the trust. If you have questions about your unit allocation, please contact the trustee directly.

Best regards,
The TrustOffice Team
        """
    },

    # Distribution Notice to Beneficiary
    "distribution_notice": {
        "subject": lambda data: f"Distribution Notice — {data.get('trust_name', 'Your Trust')}",
        "html": lambda data: _base_template(f"""
            <h2>Distribution Notice</h2>
            <p>Dear {data.get('beneficiary_name', 'Beneficiary')},</p>
            <p>This notice is to inform you of a distribution from the <strong>{data.get('trust_name', 'Trust')}</strong>.</p>
            
            <div class="task-card">
                <h3>Distribution Details</h3>
                <p><span class="label">Amount:</span> <span class="value">${{data.get('amount', '0.00'):,.2f}}</span></p>
                <p><span class="label">Date:</span> <span class="value">{data.get('date', 'N/A')}</span></p>
                <p><span class="label">Category:</span> <span class="value">{data.get('category', 'N/A')}</span></p>
                <p><span class="label">Status:</span> <span class="value">{data.get('status', 'N/A').replace('_', ' ').title()}</span></p>
                {f'<p><span class="label">Notes:</span> <span class="value">{data.get("notes", "")}</span></p>' if data.get('notes') else ''}
            </div>
            
            <p>This notice was sent by the trustee of the trust. If you have questions about this distribution, please contact the trustee directly.</p>
            
            <p>Best regards,<br>The TrustOffice Team</p>
        """),
        "text": lambda data: f"""
Distribution Notice — {data.get('trust_name', 'Your Trust')}

Dear {data.get('beneficiary_name', 'Beneficiary')},

This notice is to inform you of a distribution from the {data.get('trust_name', 'Trust')}.

Distribution Details:
- Amount: ${data.get('amount', 0):,.2f}
- Date: {data.get('date', 'N/A')}
- Category: {data.get('category', 'N/A')}
- Status: {data.get('status', 'N/A').replace('_', ' ').title() if data.get('status') else 'N/A'}
{'- Notes: ' + data.get('notes', '') if data.get('notes') else ''}

This notice was sent by the trustee of the trust. If you have questions about this distribution, please contact the trustee directly.

Best regards,
The TrustOffice Team
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
