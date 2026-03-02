"""
AI Service - AI-powered features for TrustOffice
Provides minutes drafting and governance suggestions using Claude

Note: Requires CLAUDE_API_KEY or EMERGENT_LLM_KEY environment variable.
This app runs on Emergent which provides the key automatically.
- Minutes drafting uses claude-sonnet-4-5 for complex document generation
- Governance suggestions uses claude-haiku-4-5 for quick recommendations

=== MANUAL TESTING ===
To test minutes drafting, send POST to /api/ai/minutes-draft with body:
  {"minutes_type":"quarterly","meeting_date":"2026-01-15","participants":["Trustee Name"],
   "decisions_outline":["Reviewed assets","Approved distribution"],"trust_name":"Family Trust"}
Then verify the draft appears in the Minutes UI.

To test governance suggestions, load the Dashboard with some existing minutes/tasks
and confirm suggestions populate the AI Recommendations card.
"""
import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import HTTPException

from claude_client import call_claude_sonnet, call_claude_haiku, ClaudeClientError

logger = logging.getLogger(__name__)

# Standard error message for client - does not expose internal details
AI_UNAVAILABLE_MESSAGE = "AI assistant is currently unavailable. Please try again later."


# ==================== MINUTES DRAFTING ====================

class MinutesDraftRequest(BaseModel):
    """Request model for AI-powered minutes drafting"""
    minutes_type: str = Field(..., description="Type: annual, quarterly, distribution, compensation, solvency, special")
    meeting_date: str = Field(..., description="ISO date of the meeting")
    participants: List[str] = Field(..., description="List of meeting participants")
    decisions_outline: List[str] = Field(..., description="Short bullet descriptions of decisions made")
    trust_name: str = Field(..., description="Name of the trust")
    jurisdiction: Optional[str] = Field(None, description="Trust jurisdiction (e.g., Delaware)")
    beneficiary_standard: Optional[str] = Field(None, description="Standard for distributions (e.g., HEMS)")
    additional_context: Optional[str] = Field(None, description="Freeform notes or additional context")


class MinutesDraftResponse(BaseModel):
    """Response model for AI-generated minutes draft"""
    draft_body: str = Field(..., description="The main minutes text body")
    suggested_title: str = Field(..., description="Suggested title for the minutes")
    cautions: List[str] = Field(default_factory=list, description="Warnings or notes for the trustee")


MINUTES_DRAFTING_SYSTEM_PROMPT = """You are a governance drafting assistant for trustees using TrustOffice.
You draft non-jurisdiction-specific minutes using formal, neutral language and WHEREAS/RESOLVED style based only on the provided data.
You do not give legal advice, cite statutes, or invent facts.
You must output clear, professional text that the trustee can edit.

IMPORTANT: You must respond with valid JSON only, no additional text or markdown.
The JSON must have exactly these keys:
- "draft_body": string (the full minutes document text)
- "suggested_title": string (a short title for the minutes)
- "cautions": array of strings (any warnings or notes for the trustee to review)"""


async def draft_minutes_from_structured_input(req: MinutesDraftRequest) -> MinutesDraftResponse:
    """
    Generate a draft of meeting minutes using Claude Sonnet.
    
    Takes structured input about a trust meeting and generates
    professional minutes with WHEREAS/RESOLVED language.
    """
    # Build the user content with all structured input
    participants_str = ", ".join(req.participants) if req.participants else "No participants listed"
    decisions_str = "\n".join([f"- {d}" for d in req.decisions_outline]) if req.decisions_outline else "No decisions recorded"
    
    user_content = f"""Please draft meeting minutes with the following details:

MEETING INFORMATION:
- Type: {req.minutes_type}
- Date: {req.meeting_date}
- Trust: {req.trust_name}
- Jurisdiction: {req.jurisdiction or "Not specified"}
- Beneficiary Standard: {req.beneficiary_standard or "Not specified"}

PARTICIPANTS:
{participants_str}

DECISIONS TO DOCUMENT:
{decisions_str}

ADDITIONAL CONTEXT:
{req.additional_context or "None provided"}

Generate a formal minutes document using WHEREAS/RESOLVED structure where appropriate.
Include proper opening and closing language typical for trust administration minutes.

Respond with a JSON object containing:
- "draft_body": the complete minutes text
- "suggested_title": a short descriptive title
- "cautions": any warnings or items the trustee should review"""

    try:
        response = await call_claude_sonnet(
            system_prompt=MINUTES_DRAFTING_SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=1200,
            temperature=0.2
        )
        
        # Parse the JSON response
        try:
            # Clean the response (remove markdown code blocks if present)
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            data = json.loads(cleaned)
            
            return MinutesDraftResponse(
                draft_body=data.get("draft_body", ""),
                suggested_title=data.get("suggested_title", f"{req.minutes_type.title()} Meeting Minutes"),
                cautions=data.get("cautions", [])
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Raw response: {response[:500]}")
            # Return the raw response as draft_body if JSON parsing fails
            return MinutesDraftResponse(
                draft_body=response,
                suggested_title=f"{req.minutes_type.title()} Meeting Minutes - {req.meeting_date}",
                cautions=["AI response was not in expected format. Please review and edit carefully."]
            )
            
    except ClaudeClientError as e:
        logger.error(f"Claude API error in minutes drafting: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=AI_UNAVAILABLE_MESSAGE)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in minutes drafting response: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=AI_UNAVAILABLE_MESSAGE)
    except Exception as e:
        logger.error(f"Unexpected error in minutes drafting: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=AI_UNAVAILABLE_MESSAGE)


# ==================== GOVERNANCE SUGGESTIONS ====================

class GovernanceCriterion(BaseModel):
    """A single governance health criterion"""
    name: str
    description: str
    points: int
    max_points: int
    achieved: bool


class RecentActivity(BaseModel):
    """A recent activity item"""
    type: str = Field(..., description="Type: minutes, distribution, compensation, task, benevolence")
    date: str
    label: str


class GovernanceSuggestionsRequest(BaseModel):
    """Request model for AI-powered governance suggestions"""
    health_score: float = Field(..., description="Current governance health score (0-100)")
    criteria: List[GovernanceCriterion] = Field(..., description="Governance health criteria breakdown")
    recent_activity: List[RecentActivity] = Field(default_factory=list, description="Recent trust activity")
    trust_name: str = Field(..., description="Name of the trust")


class GovernanceSuggestion(BaseModel):
    """A single governance improvement suggestion"""
    title: str = Field(..., description="Short title for the suggestion")
    description: str = Field(..., description="Detailed description of the recommendation")
    route: str = Field(..., description="App route to address this (e.g., /minutes/new)")
    estimated_points_gain: Optional[int] = Field(None, description="Estimated points improvement")


class GovernanceSuggestionsResponse(BaseModel):
    """Response model for AI-generated governance suggestions"""
    suggestions: List[GovernanceSuggestion] = Field(..., description="List of actionable suggestions")


GOVERNANCE_SUGGESTIONS_SYSTEM_PROMPT = """You are a governance coach for trustees using TrustOffice.
You see a governance health score, its criteria, and recent activity.
You output 2-4 short, concrete, non-legal-advice recommendations to improve governance discipline.
Each suggestion should map to one app route (like /minutes/new, /calendar, /distributions, /schedule-a, /benevolence).
Do not mention laws, jurisdictions, or legal conclusions.

Available routes:
- /minutes/new - Create new meeting minutes
- /minutes/templates - Use guided minutes templates
- /calendar - View and manage governance tasks
- /distributions - Manage distributions to beneficiaries
- /schedule-a - Update trust asset ledger
- /benevolence - Manage benevolent distributions
- /compensation - Review trustee compensation
- /governance - View governance health details
- /entities - Manage trust entities
- /trust-units - Manage trust certificates

IMPORTANT: You must respond with valid JSON only, no additional text or markdown.
The JSON must have exactly this structure:
{
  "suggestions": [
    {
      "title": "short title",
      "description": "detailed recommendation",
      "route": "/route/path",
      "estimated_points_gain": number or null
    }
  ]
}"""


async def generate_governance_suggestions(req: GovernanceSuggestionsRequest) -> GovernanceSuggestionsResponse:
    """
    Generate governance improvement suggestions using Claude Haiku.
    
    Analyzes the current governance health score and criteria to
    provide actionable recommendations for trustees.
    """
    # Build criteria summary focusing on underperforming areas
    underperforming = [c for c in req.criteria if not c.achieved]
    criteria_summary = ""
    
    if underperforming:
        criteria_summary = "AREAS NEEDING ATTENTION:\n"
        for c in underperforming:
            criteria_summary += f"- {c.name}: {c.description} (0/{c.max_points} points)\n"
    else:
        criteria_summary = "All criteria are currently met. Focus on maintaining good governance practices.\n"
    
    # Build recent activity summary
    activity_summary = ""
    if req.recent_activity:
        activity_summary = "RECENT ACTIVITY:\n"
        for a in req.recent_activity[:5]:  # Limit to 5 items
            activity_summary += f"- [{a.type}] {a.date}: {a.label}\n"
    else:
        activity_summary = "No recent activity recorded.\n"
    
    user_content = f"""Please provide governance improvement suggestions for this trust:

TRUST: {req.trust_name}
CURRENT HEALTH SCORE: {req.health_score:.0f}/100

{criteria_summary}
{activity_summary}

Generate 2-4 specific, actionable suggestions to improve governance discipline.
Each suggestion should:
1. Have a clear, short title
2. Include a specific action the trustee can take
3. Map to the most relevant app route
4. Estimate points gain where applicable

Respond with JSON containing a "suggestions" array."""

    try:
        response = await call_claude_haiku(
            system_prompt=GOVERNANCE_SUGGESTIONS_SYSTEM_PROMPT,
            user_content=user_content,
            max_tokens=400,
            temperature=0.3
        )
        
        # Parse the JSON response
        try:
            # Clean the response
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            data = json.loads(cleaned)
            
            suggestions = []
            for s in data.get("suggestions", []):
                suggestions.append(GovernanceSuggestion(
                    title=s.get("title", "Governance Improvement"),
                    description=s.get("description", ""),
                    route=s.get("route", "/governance"),
                    estimated_points_gain=s.get("estimated_points_gain")
                ))
            
            return GovernanceSuggestionsResponse(suggestions=suggestions)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.debug(f"Raw response: {response[:500]}")
            # Return a fallback suggestion
            return GovernanceSuggestionsResponse(suggestions=[
                GovernanceSuggestion(
                    title="Review Governance Health",
                    description="Visit the Governance page to review your current health score and see detailed criteria.",
                    route="/governance",
                    estimated_points_gain=None
                )
            ])
            
    except ClaudeClientError as e:
        logger.error(f"Claude API error in governance suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in governance suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate suggestions. Please try again.")
