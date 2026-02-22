"""
Email Service for TrustOffice
Postmark integration for transactional emails
"""

import os
import logging
from typing import Optional, Dict, Any, List
from postmarker.core import PostmarkClient
from email_templates import render_template, TEMPLATES

logger = logging.getLogger(__name__)

# Configuration
POSTMARK_SERVER_TOKEN = os.environ.get('POSTMARK_SERVER_TOKEN', '')
FROM_EMAIL = os.environ.get('POSTMARK_FROM_EMAIL', 'no-reply@contact.trustoffice.app')
FROM_NAME = os.environ.get('POSTMARK_FROM_NAME', 'TrustOffice')
APP_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://trustoffice.app').rstrip('/api').rstrip('/')


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
    
    def get_available_templates(self) -> List[str]:
        """Get list of available template names"""
        return list(TEMPLATES.keys())


# Create singleton instance
email_service = EmailService()
