"""
Demo router - Demo data seeding for new users
Migrated from server.py
"""
from fastapi import APIRouter, Depends
from datetime import datetime, timezone, timedelta
import uuid

from dependencies import get_current_user
from database import db

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed")
async def seed_demo_data(user: dict = Depends(get_current_user)):
    """Seed demo data for new users with 2 sample trusts and related data"""
    existing = await db.trusts.count_documents({"user_id": user["user_id"]})
    if existing > 0:
        return {"message": "User already has trusts", "seeded": False}
    
    now = datetime.now(timezone.utc)
    
    # ==================== TRUST 1: Smith Family Trust (Full featured with Benevolence) ====================
    trust1_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "trust_type": "family",
        "jurisdiction": "Delaware",
        "benevolence_enabled": True,
        "tax_status": "501c3",
        "description": "Irrevocable family trust for asset protection and generational wealth transfer.",
        "review_cadence": "quarterly",
        "role": "Trustee",
        "created_at": now.isoformat()
    })
    
    # ==================== TRUST 2: Johnson Education Trust ====================
    trust2_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust2_id,
        "user_id": user["user_id"],
        "name": "Johnson Education Trust",
        "trust_type": "family",
        "jurisdiction": "California",
        "benevolence_enabled": False,
        "description": "Education trust for grandchildren's college expenses.",
        "review_cadence": "annual",
        "role": "Trustee",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITIES for Trust 1 ====================
    trust1_entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": trust1_entity_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "entity_type": "Trust",
        "legal_name": "The Smith Family Irrevocable Trust",
        "formation_date": "2020-01-15",
        "governing_law": "Delaware",
        "ein": "12-3456789",
        "trustee_names": "John Smith, Jane Smith",
        "beneficiary_standard": "Health, Education, Maintenance, and Support",
        "article_ref_distribution": "Article IV, Section 4.1",
        "article_ref_compensation": "Article V, Section 5.2",
        "article_ref_amendment": "Article VIII",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat()
    })
    
    holding_llc_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": holding_llc_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Holdings LLC",
        "entity_type": "Holding LLC",
        "legal_name": "Smith Holdings, LLC",
        "formation_date": "2020-03-01",
        "governing_law": "Delaware",
        "ein": "98-7654321",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "Smith Family Trust (100%)",
        "manager_names": "John Smith",
        "article_ref_authority": "Section 3.2",
        "article_ref_profit_distribution": "Section 5.1",
        "created_at": now.isoformat()
    })
    
    real_estate_llc_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": real_estate_llc_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Real Estate LLC",
        "entity_type": "Operating LLC",
        "legal_name": "Smith Real Estate Holdings, LLC",
        "formation_date": "2021-06-15",
        "governing_law": "Delaware",
        "ein": "55-1234567",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "Smith Holdings LLC (100%)",
        "manager_names": "John Smith",
        "article_ref_authority": "Section 3.1",
        "article_ref_profit_distribution": "Section 4.2",
        "created_at": now.isoformat()
    })
    
    investment_corp_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": investment_corp_id,
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Investments Inc",
        "entity_type": "Corporation",
        "legal_name": "Smith Investments, Inc.",
        "formation_date": "2022-01-10",
        "governing_law": "Nevada",
        "ein": "88-9876543",
        "trustee_names": "",
        "beneficiary_standard": "",
        "article_ref_distribution": "",
        "article_ref_compensation": "",
        "article_ref_amendment": "",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "John Smith (President), Jane Smith (Secretary)",
        "article_ref_authority": "Bylaws Article III",
        "article_ref_profit_distribution": "Bylaws Article V",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITY RELATIONSHIPS (Hierarchy) for Trust 1 ====================
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": trust1_entity_id,
        "child_entity_id": holding_llc_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Trust is sole member of holding LLC",
        "created_at": now.isoformat()
    })
    
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": holding_llc_id,
        "child_entity_id": real_estate_llc_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Holding LLC is sole member of real estate entity",
        "created_at": now.isoformat()
    })
    
    await db.entity_relationships.insert_one({
        "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "parent_entity_id": holding_llc_id,
        "child_entity_id": investment_corp_id,
        "relationship_type": "owns",
        "ownership_percentage": 100,
        "notes": "Holding LLC is sole shareholder of investment corp",
        "created_at": now.isoformat()
    })
    
    # ==================== ENTITIES for Trust 2 ====================
    trust2_entity_id = f"entity_{uuid.uuid4().hex[:12]}"
    await db.entities.insert_one({
        "entity_id": trust2_entity_id,
        "trust_id": trust2_id,
        "user_id": user["user_id"],
        "name": "Johnson Education Trust",
        "entity_type": "Trust",
        "legal_name": "The Johnson Education Trust",
        "formation_date": "2023-01-01",
        "governing_law": "California",
        "ein": "77-1234567",
        "trustee_names": "John Smith",
        "beneficiary_standard": "Education expenses for grandchildren",
        "article_ref_distribution": "Article III",
        "article_ref_compensation": "Article IV",
        "article_ref_amendment": "Article VI",
        "oversight_required": False,
        "member_names": "",
        "manager_names": "",
        "article_ref_authority": "",
        "article_ref_profit_distribution": "",
        "created_at": now.isoformat()
    })
    
    # ==================== GOVERNANCE TASKS ====================
    await db.governance_tasks.insert_many([
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=60)).isoformat(),
         "completed_at": None, "description": "Annual trust administration review", "created_at": now.isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "quarterly_review", "due_date": (now + timedelta(days=30)).isoformat(),
         "completed_at": None, "description": "Q1 2026 quarterly review", "created_at": now.isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "compensation_review", "due_date": (now - timedelta(days=5)).isoformat(),
         "completed_at": None, "description": "Review trustee compensation for 2026 (OVERDUE)", "created_at": (now - timedelta(days=30)).isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "distribution_review", "due_date": (now + timedelta(days=15)).isoformat(),
         "completed_at": (now - timedelta(days=2)).isoformat(), "description": "Review Q4 distributions - COMPLETED", "created_at": (now - timedelta(days=20)).isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=90)).isoformat(),
         "completed_at": None, "description": "Annual education trust review", "created_at": now.isoformat()}
    ])
    
    # ==================== MINUTES ====================
    await db.minutes_records.insert_many([
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "quarterly", "meeting_date": (now - timedelta(days=15)).isoformat(),
         "participants_text": "John Smith (Trustee), Jane Smith (Trustee), Robert Attorney (Advisor)",
         "decisions_text": "Reviewed Q4 2025 performance. Approved education distribution for Emily. Confirmed investment strategy remains aligned with trust objectives.",
         "created_at": (now - timedelta(days=15)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=60)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Accept Beach Condo Unit 4B into trust corpus. Value: $425,000. Schedule A amended.",
         "generated_from_template": "acceptance_of_property",
         "template_data": {"property_description": "Beach Condo Unit 4B", "estimated_value": 425000},
         "created_at": (now - timedelta(days=60)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=45)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Approve $25,000 benevolent grant to Grace Community Church for youth ministry programs.",
         "generated_from_template": "benevolence_approval",
         "template_data": {"beneficiary_name": "Grace Community Church", "amount": 25000},
         "created_at": (now - timedelta(days=45)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "distribution", "meeting_date": (now - timedelta(days=30)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "Approved $15,000 distribution to Emily Smith for spring semester tuition. Solvency confirmed.",
         "created_at": (now - timedelta(days=30)).isoformat()},
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=90)).isoformat(),
         "participants_text": "John Smith",
         "decisions_text": "Annual review of education trust. 529 account performing well. Reviewed beneficiary designations.",
         "created_at": (now - timedelta(days=90)).isoformat()}
    ])
    
    # ==================== DISTRIBUTIONS ====================
    await db.distribution_records.insert_many([
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 15000, "date": (now - timedelta(days=10)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(a)",
         "notes": "Spring 2026 semester tuition - State University", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=10)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=10)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 2500, "date": (now - timedelta(days=3)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(b)",
         "notes": "Monthly living allowance - PENDING APPROVAL", "solvency_confirmed": False,
         "recusal_acknowledged": False, "approved_by": None, "approved_at": None,
         "minutes_record_id": None, "created_at": (now - timedelta(days=3)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Michael Smith", "amount": 8000, "date": (now - timedelta(days=45)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.2",
         "notes": "Medical expenses - dental surgery", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=44)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=45)).isoformat()},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "beneficiary_name": "Sarah Johnson", "amount": 12000, "date": (now - timedelta(days=20)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article III",
         "notes": "College tuition - freshman year", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=20)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=20)).isoformat()}
    ])
    
    # ==================== SCHEDULE A (Trust Corpus) ====================
    await db.schedule_a_items.insert_many([
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "real_property", "description": "Primary Family Residence - 123 Oak Street",
         "identifier": "Deed #2020-12345", "location": "Wilmington, Delaware",
         "approximate_value": 650000, "date_conveyed": "2020-01-15",
         "notes": "Original trust corpus - 4BR/3BA Colonial", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "real_property", "description": "Vacation Property - Beach Condo Unit 4B",
         "identifier": "Deed #2021-67890", "location": "Rehoboth Beach, Delaware",
         "approximate_value": 425000, "date_conveyed": "2021-06-01",
         "notes": "Added via property acceptance minutes - 2BR oceanfront", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "Schwab Brokerage Account - Growth Portfolio",
         "identifier": "Acct #****7890", "location": "Charles Schwab",
         "approximate_value": 1250000, "date_conveyed": "2020-01-15",
         "notes": "Primary investment account - diversified equity/bond mix", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "First National Bank - Operating Account",
         "identifier": "Acct #****1234", "location": "First National Bank, DE",
         "approximate_value": 85000, "date_conveyed": "2020-02-01",
         "notes": "Trust checking account for distributions", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "business_interests", "description": "Smith Holdings LLC - 100% Membership Interest",
         "identifier": "Member Certificate #001", "location": "Delaware",
         "approximate_value": 500000, "date_conveyed": "2020-03-01",
         "notes": "Wholly-owned holding company", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "personal_property", "description": "2022 Mercedes-Benz S-Class",
         "identifier": "VIN: WDDUG8FB2NA******", "location": "Wilmington, Delaware",
         "approximate_value": 95000, "date_conveyed": "2022-04-15",
         "notes": "Trust vehicle", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "category": "other_property", "description": "Fine Art Collection - Various Works",
         "identifier": "Appraised Inventory #2023-001", "location": "Family Residence",
         "approximate_value": 175000, "date_conveyed": "2020-01-15",
         "notes": "12 paintings and 3 sculptures", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "529 Education Savings Account",
         "identifier": "Acct #****5678", "location": "Fidelity Investments",
         "approximate_value": 250000, "date_conveyed": "2023-01-15",
         "notes": "College savings - aggressive growth allocation", "created_at": now.isoformat()},
        {"item_id": f"item_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "category": "financial_accounts", "description": "Trust Operating Account",
         "identifier": "Acct #****9999", "location": "Wells Fargo",
         "approximate_value": 15000, "date_conveyed": "2023-01-15",
         "notes": "Operating account for expenses", "created_at": now.isoformat()}
    ])
    
    # ==================== BENEVOLENCE RECORDS (Trust 1 only - has benevolence enabled) ====================
    await db.benevolence_records.insert_many([
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Grace Community Church", "beneficiary_type": "organization", "purpose": "spiritual",
         "purpose_description": "Annual ministry support for youth programs and community outreach",
         "amount": 25000, "date": (now - timedelta(days=45)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "5th consecutive year of support", "created_at": (now - timedelta(days=45)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Johnson Family", "beneficiary_type": "family", "purpose": "medical",
         "purpose_description": "Cancer treatment expenses - chemotherapy and hospital bills",
         "amount": 15000, "date": (now - timedelta(days=30)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Referred by Pastor Williams", "created_at": (now - timedelta(days=30)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Maria Rodriguez", "beneficiary_type": "individual", "purpose": "education",
         "purpose_description": "Community college tuition for nursing program",
         "amount": 4500, "date": (now - timedelta(days=20)).isoformat(),
         "approved_by": ["John Smith"], "approval_method": "majority", "status": "approved",
         "minutes_id": None, "notes": "Single mother pursuing RN degree", "created_at": (now - timedelta(days=20)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Local Food Bank", "beneficiary_type": "organization", "purpose": "food_necessities",
         "purpose_description": "Thanksgiving meal packages for 200 families",
         "amount": 5000, "date": (now - timedelta(days=90)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Annual holiday contribution", "created_at": (now - timedelta(days=90)).isoformat()},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Thomas Williams", "beneficiary_type": "individual", "purpose": "housing",
         "purpose_description": "Emergency rent assistance - 2 months rent after job loss",
         "amount": 3200, "date": (now - timedelta(days=7)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "New job starting next month", "created_at": (now - timedelta(days=7)).isoformat()}
    ])
    
    # ==================== COMPENSATION PLANS ====================
    await db.compensation_plans.insert_many([
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()},
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()}
    ])
    
    # ==================== COMPENSATION PAYMENTS ====================
    await db.compensation_payments.insert_many([
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "payment_date": (now - timedelta(days=90)).isoformat(),
         "notes": "Q4 2025 compensation", "created_at": (now - timedelta(days=90)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "payment_date": (now - timedelta(days=90)).isoformat(),
         "notes": "Q4 2025 compensation", "created_at": (now - timedelta(days=90)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "payment_date": (now - timedelta(days=5)).isoformat(),
         "notes": "Q1 2026 compensation", "created_at": (now - timedelta(days=5)).isoformat()},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "payment_date": (now - timedelta(days=5)).isoformat(),
         "notes": "Q1 2026 compensation", "created_at": (now - timedelta(days=5)).isoformat()}
    ])
    
    # ==================== NOTIFICATION PREFERENCES ====================
    await db.notification_preferences.insert_one({
        "user_id": user["user_id"],
        "minutes_created": True,
        "distribution_created": True,
        "distribution_approved": True,
        "task_reminders": True,
        "task_overdue": True,
        "subscription_updates": True,
        "weekly_digest": True
    })
    
    return {"message": "Demo data created with 2 trusts", "seeded": True, "trust_ids": [trust1_id, trust2_id]}
