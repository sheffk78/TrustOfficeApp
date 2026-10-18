"""
Agent Mailer - thin email wrapper for the internal proactive agent.

Uses the repo's existing EmailService when available. Falls back to a clean
Postmark client reading POSTMARK_API_KEY (or POSTMARK_SERVER_TOKEN) when not.
Every send/draft is logged to agent_activity by the caller.

SAFETY:
- Drafts are produced by default.
- A send only happens when the caller passes send=True. The agent runner checks
  customer.agent_consent and fails closed.
"""

import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AgentMailer:
    """Email facade for agent-generated drafts and sends."""

    def __init__(self):
        self._email_service = None
        self._postmark_client = None

    @property
    def _service(self):
        """Lazy-load the repo's EmailService if Postmark is configured."""
        if self._email_service is None:
            try:
                from email_service import EmailService
                svc = EmailService()
                if svc.is_configured:
                    self._email_service = svc
            except Exception as e:
                logger.debug(f"Could not load email_service: {e}")
                self._email_service = False
        return self._email_service or None

    @property
    def _postmark(self):
        """Lazy-load direct Postmark client if no EmailService available."""
        if self._postmark_client is None:
            token = os.environ.get("POSTMARK_API_KEY") or os.environ.get("POSTMARK_SERVER_TOKEN")
            if token:
                try:
                    from postmarker.core import PostmarkClient
                    self._postmark_client = PostmarkClient(server_token=token)
                except Exception as e:
                    logger.warning(f"Postmark client init failed: {e}")
                    self._postmark_client = False
            else:
                self._postmark_client = False
        return self._postmark_client or None

    def is_configured(self) -> bool:
        return bool(self._service) or bool(self._postmark)

    async def send_or_draft(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None,
        to_name: Optional[str] = None,
        tag: str = "agent",
        send: bool = False,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a draft. If send=True and a mailer is configured, send it.
        Returns a dict with {status: "draft"|"sent"|"failed", message_id?, error?}.
        """
        result: Dict[str, Any] = {
            "status": "draft",
            "to_email": to_email,
            "subject": subject,
            "tag": tag,
        }

        if not send:
            return result

        if not self.is_configured():
            result["status"] = "failed"
            result["error"] = "No email provider configured"
            return result

        try:
            svc = self._service
            if svc:
                res = await svc.send_email(
                    to_email=to_email,
                    subject=subject,
                    html_body=html_body,
                    text_body=text_body,
                    to_name=to_name,
                    tag=tag,
                    metadata=metadata,
                )
            else:
                from_address = os.environ.get("POSTMARK_FROM_EMAIL", "no-reply@contact.trustoffice.app")
                from_name = os.environ.get("POSTMARK_FROM_NAME", "TrustOffice")
                payload = {
                    "From": f"{from_name} <{from_address}>",
                    "To": f"{to_name} <{to_email}>" if to_name else to_email,
                    "Subject": subject,
                    "HtmlBody": html_body,
                    "TrackOpens": True,
                }
                if text_body:
                    payload["TextBody"] = text_body
                if tag:
                    payload["Tag"] = tag
                res = self._postmark.emails.send(**payload)

            if isinstance(res, dict):
                if res.get("status") in ("sent", "skipped", "failed"):
                    result["status"] = res.get("status")
                    if "message_id" in res:
                        result["message_id"] = res["message_id"]
                    if "error" in res:
                        result["error"] = res["error"]
                else:
                    result["status"] = "sent"
                    result["message_id"] = res.get("MessageID")
            else:
                result["status"] = "sent"
                result["message_id"] = getattr(res, "MessageID", None)
        except Exception as e:
            logger.error(f"Agent mailer failed to send to {to_email}: {e}")
            result["status"] = "failed"
            result["error"] = str(e)

        return result
