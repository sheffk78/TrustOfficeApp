"""
Email Service for TrustOffice
Postmark integration for transactional emails
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from postmarker.core import PostmarkClient
from email_templates import render_template, TEMPLATES

logger = logging.getLogger(__name__)

# Configuration
POSTMARK_SERVER_TOKEN = os.environ.get('POSTMARK_SERVER_TOKEN', '')
FROM_EMAIL = os.environ.get('POSTMARK_FROM_EMAIL', 'no-reply@contact.trustoffice.app')
FROM_NAME = os.environ.get('POSTMARK_FROM_NAME', 'TrustOffice')
APP_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000').rstrip('/')


class EmailService:
    """
    Email service using Postmark for transactional emails.
    Supports templated emails with centralized template management.
    """
    
    def __init__(self, server_token: str = None):
        self.server_token = server_token or POSTMARK_SERVER_TOKEN
        self.from_email = FROM_EMAIL
        self.from_name = FROM_NAME
        self.app_url = APP_URL
        self._client = None
        
    @property
    def client(self) -> Optional[PostmarkClient]:
        """Lazy-load Postmark client"""
        if not self._client and self.server_token:
            self._client = PostmarkClient(server_token=self.server_token)
        return self._client
    
    @property
    def is_configured(self) -> bool:
        """Check if email service is properly configured"""
        return bool(self.server_token)
    
    def _get_from_address(self) -> str:
        """Format from address"""
        return f"{self.from_name} <{self.from_email}>"
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str = None,
        to_name: str = None,
        tag: str = None,
        metadata: Dict[str, str] = None,
        track_opens: bool = True
    ) -> Dict[str, Any]:
        """
        Send a single email via Postmark.
        
        Args:
            to_email: Recipient email address
            subject: Email subject line
            html_body: HTML content of the email
            text_body: Plain text content (optional)
            to_name: Recipient name (optional)
            tag: Tag for tracking/filtering in Postmark
            metadata: Custom metadata (max 10 fields)
            track_opens: Whether to track email opens
            
        Returns:
            Dict with message_id and status
        """
        if not self.is_configured:
            logger.warning("Email service not configured - skipping email send")
            return {"status": "skipped", "reason": "not_configured"}
        
        try:
            # Format recipient
            to_address = f"{to_name} <{to_email}>" if to_name else to_email
            
            # Build payload
            payload = {
                "From": self._get_from_address(),
                "To": to_address,
                "Subject": subject,
                "HtmlBody": html_body,
                "TrackOpens": track_opens
            }
            
            if text_body:
                payload["TextBody"] = text_body
            
            if tag:
                payload["Tag"] = tag
                
            if metadata:
                # Validate metadata limits (max 10 fields, key max 20 chars, value max 80 chars)
                valid_metadata = {}
                for key, value in list(metadata.items())[:10]:
                    valid_metadata[key[:20]] = str(value)[:80]
                payload["Metadata"] = valid_metadata
            
            # Send email
            response = self.client.emails.send(**payload)
            
            logger.info(
                "Email sent successfully",
                extra={
                    "message_id": response.get("MessageID"),
                    "to": to_email,
                    "subject": subject,
                    "tag": tag
                }
            )
            
            return {
                "status": "sent",
                "message_id": response.get("MessageID"),
                "submitted_at": response.get("SubmittedAt")
            }
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}", extra={"to": to_email, "subject": subject})
            return {"status": "failed", "error": str(e)}
    
    async def send_templated_email(
        self,
        to_email: str,
        template_name: str,
        template_data: Dict[str, Any],
        to_name: str = None,
        tag: str = None,
        metadata: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Send an email using a predefined template.
        
        Args:
            to_email: Recipient email address
            template_name: Name of the template to use
            template_data: Data to populate the template
            to_name: Recipient name (optional)
            tag: Tag for tracking (defaults to template name)
            metadata: Custom metadata
            
        Returns:
            Dict with message_id and status
        """
        # Add app_url to template data
        template_data["app_url"] = self.app_url
        
        # Render template
        rendered = render_template(template_name, template_data)
        
        return await self.send_email(
            to_email=to_email,
            subject=rendered["subject"],
            html_body=rendered["html"],
            text_body=rendered["text"],
            to_name=to_name,
            tag=tag or template_name,
            metadata=metadata
        )
    
    # ==================== CONVENIENCE METHODS ====================
    
    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_url: str
    ) -> Dict[str, Any]:
        """Send password reset email"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="password_reset",
            template_data={
                "user_name": user_name,
                "reset_url": reset_url
            },
            to_name=user_name,
            tag="password_reset",
            metadata={"email_type": "password_reset"}
        )
    
    async def send_welcome_email(
        self,
        to_email: str,
        user_name: str = None
    ) -> Dict[str, Any]:
        """Send welcome/onboarding email to new user"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="welcome",
            template_data={
                "user_name": user_name or "there"
            },
            to_name=user_name,
            metadata={"email_type": "welcome"}
        )
    
    async def send_welcome_set_password_email(
        self,
        to_email: str,
        user_name: str,
        set_password_url: str
    ) -> Dict[str, Any]:
        """Send welcome email with set-password link for admin-created accounts"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="welcome_set_password",
            template_data={
                "user_name": user_name or "there",
                "set_password_url": set_password_url
            },
            to_name=user_name,
            tag="welcome_set_password",
            metadata={"email_type": "welcome_set_password"}
        )
    
    async def send_task_reminder(
        self,
        to_email: str,
        user_name: str,
        trust_name: str,
        task_type: str,
        due_date: str,
        description: str = None
    ) -> Dict[str, Any]:
        """Send reminder for upcoming governance task"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="task_reminder",
            template_data={
                "user_name": user_name,
                "trust_name": trust_name,
                "task_type": task_type,
                "due_date": due_date,
                "description": description
            },
            to_name=user_name,
            metadata={"email_type": "task_reminder", "task_type": task_type}
        )
    
    async def send_task_overdue(
        self,
        to_email: str,
        user_name: str,
        trust_name: str,
        task_type: str,
        due_date: str,
        days_overdue: int
    ) -> Dict[str, Any]:
        """Send notification for overdue task"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="task_overdue",
            template_data={
                "user_name": user_name,
                "trust_name": trust_name,
                "task_type": task_type,
                "due_date": due_date,
                "days_overdue": days_overdue
            },
            to_name=user_name,
            tag="task_overdue",
            metadata={"email_type": "task_overdue", "task_type": task_type}
        )
    
    async def send_minutes_notification(
        self,
        to_email: str,
        user_name: str,
        trust_name: str,
        minutes_type: str,
        meeting_date: str,
        participants: str = None,
        decisions: str = None
    ) -> Dict[str, Any]:
        """Send notification when new minutes are created"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="minutes_created",
            template_data={
                "user_name": user_name,
                "trust_name": trust_name,
                "minutes_type": minutes_type,
                "meeting_date": meeting_date,
                "participants": participants,
                "decisions": decisions
            },
            to_name=user_name,
            metadata={"email_type": "minutes_created", "minutes_type": minutes_type}
        )
    
    async def send_distribution_notification(
        self,
        to_email: str,
        user_name: str,
        trust_name: str,
        amount: float,
        beneficiary: str,
        category: str,
        date: str,
        status: str = "review"
    ) -> Dict[str, Any]:
        """Send notification when new distribution is logged"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="distribution_created",
            template_data={
                "user_name": user_name,
                "trust_name": trust_name,
                "amount": amount,
                "beneficiary": beneficiary,
                "category": category,
                "date": date,
                "status": status
            },
            to_name=user_name,
            metadata={"email_type": "distribution_created"}
        )
    
    async def send_distribution_approved_notification(
        self,
        to_email: str,
        user_name: str,
        trust_name: str,
        amount: float,
        beneficiary: str,
        approved_by: str,
        approval_date: str
    ) -> Dict[str, Any]:
        """Send notification when distribution is approved"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="distribution_approved",
            template_data={
                "user_name": user_name,
                "trust_name": trust_name,
                "amount": amount,
                "beneficiary": beneficiary,
                "approved_by": approved_by,
                "approval_date": approval_date
            },
            to_name=user_name,
            metadata={"email_type": "distribution_approved"}
        )
    
    # ==================== SUBSCRIPTION EMAIL METHODS ====================
    
    async def send_subscription_activated(
        self,
        to_email: str,
        user_name: str,
        plan_type: str,
        amount: str,
        next_billing_date: str
    ) -> Dict[str, Any]:
        """Send notification when subscription is activated"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="subscription_activated",
            template_data={
                "user_name": user_name,
                "plan_type": plan_type,
                "amount": amount,
                "next_billing_date": next_billing_date
            },
            to_name=user_name,
            tag="subscription",
            metadata={"email_type": "subscription_activated", "plan": plan_type}
        )
    
    async def send_subscription_canceled(
        self,
        to_email: str,
        user_name: str,
        access_until: str
    ) -> Dict[str, Any]:
        """Send notification when subscription is canceled"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="subscription_canceled",
            template_data={
                "user_name": user_name,
                "access_until": access_until
            },
            to_name=user_name,
            tag="subscription",
            metadata={"email_type": "subscription_canceled"}
        )
    
    async def send_subscription_renewed(
        self,
        to_email: str,
        user_name: str,
        plan_type: str,
        amount: str,
        next_billing_date: str
    ) -> Dict[str, Any]:
        """Send notification when subscription is renewed"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="subscription_renewed",
            template_data={
                "user_name": user_name,
                "plan_type": plan_type,
                "amount": amount,
                "next_billing_date": next_billing_date
            },
            to_name=user_name,
            tag="subscription",
            metadata={"email_type": "subscription_renewed", "plan": plan_type}
        )
    
    async def send_payment_failed(
        self,
        to_email: str,
        user_name: str,
        amount: str,
        retry_date: str = None
    ) -> Dict[str, Any]:
        """Send notification when payment fails"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="payment_failed",
            template_data={
                "user_name": user_name,
                "amount": amount,
                "retry_date": retry_date or "within the next few days"
            },
            to_name=user_name,
            tag="subscription",
            metadata={"email_type": "payment_failed"}
        )
    
    async def send_subscription_upgraded(
        self,
        to_email: str,
        user_name: str,
        old_plan: str,
        new_plan: str
    ) -> Dict[str, Any]:
        """Send notification when subscription is upgraded"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="subscription_upgraded",
            template_data={
                "user_name": user_name,
                "old_plan": old_plan,
                "new_plan": new_plan
            },
            to_name=user_name,
            tag="subscription",
            metadata={"email_type": "subscription_upgraded", "new_plan": new_plan}
        )
    
    async def send_admin_new_purchase_notification(
        self,
        customer_email: str,
        customer_name: str,
        plan_type: str,
        amount: str
    ) -> Dict[str, Any]:
        """Send notification to admin when there's a new subscription purchase"""
        admin_email = "contact@trustoffice.app"
        
        subject = f"New TrustOffice Subscription: {plan_type.title()} Plan"
        
        html_body = f"""
        <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #010079;">New Subscription Purchase</h2>
            <p>A new customer has subscribed to TrustOffice!</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: bold;">Customer Email:</td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">{customer_email}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: bold;">Customer Name:</td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">{customer_name or 'Not provided'}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: bold;">Plan:</td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">{plan_type.title()}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eee; font-weight: bold;">Amount:</td>
                    <td style="padding: 10px; border-bottom: 1px solid #eee;">${amount}</td>
                </tr>
            </table>
        </div>
        """
        
        text_body = f"""
New TrustOffice Subscription Purchase

Customer Email: {customer_email}
Customer Name: {customer_name or 'Not provided'}
Plan: {plan_type.title()}
Amount: ${amount}
        """
        
        return await self.send_email(
            to_email=admin_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            tag="admin_notification",
            metadata={"email_type": "new_purchase", "plan_type": plan_type}
        )
    
    def get_available_templates(self) -> List[str]:
        """Get list of available template names"""
        return list(TEMPLATES.keys())

    async def send_lead_welcome(
        self,
        to_email: str,
        name: str,
        course_url: str
    ) -> Dict[str, Any]:
        """Send welcome email to new lead (Trustee 101 signup or checklist download)"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="lead_welcome",
            template_data={
                "name": name or "there",
                "course_url": course_url
            },
            to_name=name,
            tag="lead_welcome",
            metadata={"email_type": "lead_welcome"}
        )

    async def send_lead_reengagement(
        self,
        to_email: str,
        name: str,
        course_url: str
    ) -> Dict[str, Any]:
        """Send re-engagement email to lead who hasn't started the course"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="lead_reengagement",
            template_data={
                "name": name or "there",
                "course_url": course_url
            },
            to_name=name,
            tag="lead_reengagement",
            metadata={"email_type": "lead_reengagement"}
        )

    # ==================== NURTURE SEQUENCE METHODS ====================

    NURTURE_TEMPLATES = {
        1: {"postmark_id": 45387225, "name": "nurture_1_checklist"},
        2: {"postmark_id": 45387227, "name": "nurture_2_piercing"},
        3: {"postmark_id": 45387209, "name": "nurture_3_irs"},
        4: {"postmark_id": 45387191, "name": "nurture_4_real_estate"},
        5: {"postmark_id": 45387229, "name": "nurture_5_conversion"},
    }

    async def send_nurture_email(
        self,
        to_email: str,
        name: str,
        step: int,
        download_url: str = None,
    ) -> Dict[str, Any]:
        """Send a nurture sequence email via Postmark template API.

        Args:
            to_email: Recipient email
            name: Recipient name
            step: Nurture step (1-5)
            download_url: Optional download URL for step 1
        """
        if step not in self.NURTURE_TEMPLATES:
            return {"status": "failed", "error": f"Invalid nurture step: {step}"}

        template = self.NURTURE_TEMPLATES[step]
        template_model = {
            "name": name or "there",
            "app_url": self.app_url,
        }
        if download_url:
            template_model["download_url"] = download_url

        if not self.is_configured:
            logger.warning("Email service not configured - skipping nurture email")
            return {"status": "skipped", "reason": "not_configured"}

        try:
            to_address = f"{name} <{to_email}>" if name else to_email
            response = self.client.emails.send_with_template(
                TemplateId=template["postmark_id"],
                TemplateModel=template_model,
                From=self._get_from_address(),
                To=to_address,
                TrackOpens=True,
                Tag=template["name"],
                Metadata={"email_type": template["name"], "nurture_step": str(step)},
            )
            logger.info(
                f"Nurture email {step} sent to {to_email}",
                extra={"message_id": response.get("MessageID"), "step": step},
            )
            return {"status": "sent", "message_id": response.get("MessageID")}
        except Exception as e:
            logger.error(f"Failed to send nurture email {step} to {to_email}: {e}")
            return {"status": "failed", "error": str(e)}

    async def send_nurture_sequence(
        self,
        to_email: str,
        name: str,
        download_url: str = None,
    ) -> Dict[str, Any]:
        """Send the full 5-email nurture sequence.

        Called when a lead is first captured. Emails 1-5 are sent
        on a schedule managed by the background job system.
        This method sends Email 1 immediately.
        """
        return await self.send_nurture_email(
            to_email=to_email,
            name=name,
            step=1,
            download_url=download_url,
        )

    async def send_certificate_notice(
        self,
        to_email: str,
        beneficiary_name: str,
        trust_name: str,
        certificate_number: str,
        units: int,
        unit_label: str = "Certificate Unit",
        percentage: float = 0,
        issue_date: str = None,
        notes: str = None,
        from_user_name: str = None
    ) -> Dict[str, Any]:
        """Send certificate of trust units notice to a beneficiary"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="certificate_notice",
            template_data={
                "beneficiary_name": beneficiary_name,
                "trust_name": trust_name,
                "certificate_number": certificate_number,
                "units": units,
                "unit_label": unit_label,
                "percentage": percentage,
                "issue_date": issue_date or datetime.now().strftime("%Y-%m-%d"),
                "notes": notes,
                "sender_name": from_user_name or "Trustee"
            },
            to_name=beneficiary_name,
            tag="certificate_notice",
            metadata={"email_type": "certificate_notice"}
        )

    async def send_distribution_notice_to_beneficiary(
        self,
        to_email: str,
        beneficiary_name: str,
        trust_name: str,
        amount: float,
        date: str,
        category: str = None,
        status: str = None,
        notes: str = None,
        from_user_name: str = None
    ) -> Dict[str, Any]:
        """Send distribution notice directly to a beneficiary"""
        return await self.send_templated_email(
            to_email=to_email,
            template_name="distribution_notice",
            template_data={
                "beneficiary_name": beneficiary_name,
                "trust_name": trust_name,
                "amount": amount,
                "date": date,
                "category": category or "Distribution",
                "status": status or "approved",
                "notes": notes,
                "sender_name": from_user_name or "Trustee"
            },
            to_name=beneficiary_name,
            tag="distribution_notice",
            metadata={"email_type": "distribution_notice"}
        )


# Create singleton instance
email_service = EmailService()
