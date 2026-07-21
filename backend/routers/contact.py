"""
Contact router - Public contact form submissions
"""
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, EmailStr, field_validator
from datetime import datetime, timezone
from typing import Optional
import uuid
import logging
import re
from collections import defaultdict
import time

from database import db
from email_service import email_service
from routers.admin import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["contact"])

# Rate limiting: track submissions by IP
rate_limit_store = defaultdict(list)
RATE_LIMIT_WINDOW = 300  # 5 minutes
RATE_LIMIT_MAX_REQUESTS = 3  # Max 3 submissions per 5 minutes


class ContactSubmission(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: str
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Name is required')
        if len(v) < 2:
            raise ValueError('Name must be at least 2 characters')
        if len(v) > 100:
            raise ValueError('Name must be less than 100 characters')
        return v
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        v = v.strip()
        if not v:
            raise ValueError('Message is required')
        if len(v) < 10:
            raise ValueError('Message must be at least 10 characters')
        if len(v) > 5000:
            raise ValueError('Message must be less than 5000 characters')
        return v
    
    @field_validator('company')
    @classmethod
    def validate_company(cls, v):
        if v:
            v = v.strip()
            if len(v) > 200:
                raise ValueError('Company name must be less than 200 characters')
        return v if v else None


def check_rate_limit(ip: str) -> bool:
    """
    Check if IP has exceeded rate limit.
    Returns True if rate limit exceeded, False otherwise.
    """
    now = time.time()
    
    # Clean old entries
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]
    
    # Check if over limit
    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    
    # Add current request
    rate_limit_store[ip].append(now)
    return False


@router.post("")
async def submit_contact_form(submission: ContactSubmission, request: Request):
    """
    Handle public contact form submissions.
    - Stores in MongoDB
    - Sends notification to team
    - Sends confirmation to submitter
    - Rate limited to prevent spam
    """
    # Get client IP for rate limiting
    client_ip = request.client.host
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    
    # Check rate limit
    if check_rate_limit(client_ip):
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=429,
            detail="Too many submissions. Please wait a few minutes and try again."
        )
    
    now = datetime.now(timezone.utc)
    submission_id = f"contact_{uuid.uuid4().hex[:12]}"
    
    # Store submission in MongoDB
    contact_doc = {
        "submission_id": submission_id,
        "name": submission.name,
        "email": submission.email.lower(),
        "company": submission.company,
        "message": submission.message,
        "ip_address": client_ip,
        "user_agent": request.headers.get("User-Agent", ""),
        "status": "new",
        "created_at": now.isoformat(),
        "responded_at": None
    }
    
    await db.contact_submissions.insert_one(contact_doc)
    logger.info(f"Contact submission saved: {submission_id} from {submission.email}")
    
    # Send notification email to team
    if email_service.is_configured:
        try:
            await email_service.send_email(
                to_email="contact@trustoffice.app",
                subject=f"[TrustOffice Contact] New message from {submission.name}",
                html_body=f"""
                <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: #1a1f36; padding: 20px; text-align: center;">
                        <h1 style="color: #c9a227; margin: 0; font-size: 24px;">New Contact Submission</h1>
                    </div>
                    
                    <div style="padding: 30px; background-color: #f8f6f1;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd; font-weight: bold; width: 120px;">Name:</td>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd;">{submission.name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd; font-weight: bold;">Email:</td>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd;">
                                    <a href="mailto:{submission.email}" style="color: #1a1f36;">{submission.email}</a>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd; font-weight: bold;">Company:</td>
                                <td style="padding: 10px 0; border-bottom: 1px solid #ddd;">{submission.company or 'Not provided'}</td>
                            </tr>
                            <tr>
                                <td style="padding: 10px 0; font-weight: bold; vertical-align: top;">Message:</td>
                                <td style="padding: 10px 0;">
                                    <div style="background-color: #fff; padding: 15px; border-radius: 4px; white-space: pre-wrap;">{submission.message}</div>
                                </td>
                            </tr>
                        </table>
                        
                        <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
                            <p>Submission ID: {submission_id}</p>
                            <p>Received: {now.strftime('%B %d, %Y at %I:%M %p UTC')}</p>
                            <p>IP Address: {client_ip}</p>
                        </div>
                    </div>
                    
                    <div style="padding: 15px; text-align: center; background-color: #1a1f36;">
                        <a href="mailto:{submission.email}?subject=Re: Your TrustOffice inquiry" 
                           style="display: inline-block; background-color: #c9a227; color: #1a1f36; padding: 10px 25px; text-decoration: none; font-weight: bold; border-radius: 4px;">
                            Reply to {submission.name}
                        </a>
                    </div>
                </div>
                """,
                text_body=f"""
New Contact Form Submission
===========================

Name: {submission.name}
Email: {submission.email}
Company: {submission.company or 'Not provided'}

Message:
{submission.message}

---
Submission ID: {submission_id}
Received: {now.strftime('%B %d, %Y at %I:%M %p UTC')}
                """,
                tag="contact-notification"
            )
            logger.info(f"Team notification sent for submission {submission_id}")
        except Exception as e:
            logger.error(f"Failed to send team notification: {e}")
    
    # Send confirmation email to submitter
    if email_service.is_configured:
        try:
            await email_service.send_email(
                to_email=submission.email,
                to_name=submission.name,
                subject="We received your message - TrustOffice",
                html_body=f"""
                <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;">
                    <div style="background-color: #1a1f36; padding: 30px; text-align: center;">
                        <div style="width: 50px; height: 50px; border: 2px solid #c9a227; display: inline-flex; align-items: center; justify-content: center; margin-bottom: 15px;">
                            <span style="color: #c9a227; font-size: 24px; font-family: Georgia, serif;">T</span>
                        </div>
                        <h1 style="color: #fff; margin: 0; font-size: 24px;">Thank You for Reaching Out</h1>
                    </div>
                    
                    <div style="padding: 30px; background-color: #f8f6f1;">
                        <p style="color: #1a1f36; font-size: 16px; line-height: 1.6;">
                            Hi {submission.name},
                        </p>
                        
                        <p style="color: #1a1f36; font-size: 16px; line-height: 1.6;">
                            Thank you for contacting TrustOffice. We've received your message and our team will review it shortly.
                        </p>
                        
                        <p style="color: #1a1f36; font-size: 16px; line-height: 1.6;">
                            You can expect to hear back from us within <strong>1-2 business days</strong>.
                        </p>
                        
                        <div style="background-color: #fff; padding: 20px; border-radius: 4px; margin: 25px 0;">
                            <p style="margin: 0 0 10px 0; font-weight: bold; color: #1a1f36;">Your Message:</p>
                            <p style="margin: 0; color: #666; white-space: pre-wrap; font-style: italic;">"{submission.message[:200]}{"..." if len(submission.message) > 200 else ""}"</p>
                        </div>
                        
                        <p style="color: #1a1f36; font-size: 16px; line-height: 1.6;">
                            In the meantime, feel free to explore our platform or check out our resources.
                        </p>
                        
                        <div style="text-align: center; margin-top: 30px;">
                            <a href="https://app.trustoffice.app" 
                               style="display: inline-block; background-color: #1a1f36; color: #fff; padding: 12px 30px; text-decoration: none; font-weight: bold; border-radius: 4px;">
                                Visit TrustOffice
                            </a>
                        </div>
                    </div>
                    
                    <div style="padding: 20px; text-align: center; background-color: #1a1f36; color: #999; font-size: 12px;">
                        <p style="margin: 0;">
                            This is an automated confirmation. Please do not reply to this email.
                        </p>
                        <p style="margin: 10px 0 0 0;">
                            Reference: {submission_id}
                        </p>
                    </div>
                </div>
                """,
                text_body=f"""
Hi {submission.name},

Thank you for contacting TrustOffice. We've received your message and our team will review it shortly.

You can expect to hear back from us within 1-2 business days.

Your Message:
"{submission.message[:200]}{"..." if len(submission.message) > 200 else ""}"

In the meantime, feel free to explore our platform at https://app.trustoffice.app

---
This is an automated confirmation. Please do not reply to this email.
Reference: {submission_id}
                """,
                tag="contact-confirmation"
            )
            logger.info(f"Confirmation email sent to {submission.email}")
        except Exception as e:
            logger.error(f"Failed to send confirmation email: {e}")
    
    return {
        "success": True,
        "message": "Thank you for your message. We'll be in touch soon!",
        "submission_id": submission_id
    }


@router.get("/submissions")
async def get_contact_submissions(
    status: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
    admin: dict = Depends(require_admin)
):
    """
    Admin endpoint to retrieve contact submissions.
    """
    limit = min(limit, 100)  # Cap to prevent bulk data extraction
    query = {}
    if status:
        query["status"] = status
    
    submissions = await db.contact_submissions.find(
        query,
        {"_id": 0}
    ).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    total = await db.contact_submissions.count_documents(query)
    
    return {
        "submissions": submissions,
        "total": total,
        "limit": limit,
        "skip": skip
    }
