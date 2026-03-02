"""
Demo router - Demo data seeding and cleanup for new users
Showcases all TrustOffice features including:
- Multiple trusts with different configurations
- Entity hierarchy with LLCs and corporations
- Schedule A assets (active and disposed)
- Minutes of various types
- Distributions (approved and pending)
- Benevolence records
- Compensation plans and payments
- Governance tasks (completed, upcoming, overdue)
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
import uuid

from dependencies import get_current_user, require_write_access
from database import db

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed")
async def seed_demo_data(user: dict = Depends(get_current_user)):
    """
    Seed comprehensive demo data for new users.
    Creates 2 sample trusts with rich data showcasing all features.
    """
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
    
    # ==================== ENTITIES for Trust 1 (Multi-level Hierarchy) ====================
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
    await db.entity_relationships.insert_many([
        {
            "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "parent_entity_id": trust1_entity_id,
            "child_entity_id": holding_llc_id,
            "relationship_type": "owns",
            "ownership_percentage": 100,
            "notes": "Trust is sole member of holding LLC",
            "created_at": now.isoformat()
        },
        {
            "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "parent_entity_id": holding_llc_id,
            "child_entity_id": real_estate_llc_id,
            "relationship_type": "owns",
            "ownership_percentage": 100,
            "notes": "Holding LLC is sole member of real estate entity",
            "created_at": now.isoformat()
        },
        {
            "relationship_id": f"rel_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "parent_entity_id": holding_llc_id,
            "child_entity_id": investment_corp_id,
            "relationship_type": "owns",
            "ownership_percentage": 100,
            "notes": "Holding LLC is sole shareholder of investment corp",
            "created_at": now.isoformat()
        }
    ])
    
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
    
    # ==================== SCHEDULE A ASSETS (Including DISPOSED examples) ====================
    
    # Create a minutes ID for the property acceptance
    property_acceptance_minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    
    # Create a minutes ID for the disposed vehicle
    vehicle_disposition_minutes_id = f"minutes_{uuid.uuid4().hex[:12]}"
    
    await db.schedule_a_items.insert_many([
        # Active Assets - Trust 1
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "real_property", 
            "description": "Primary Family Residence - 123 Oak Street",
            "identifier": "Deed #2020-12345", 
            "location": "Wilmington, Delaware",
            "approximate_value": 650000, 
            "date_conveyed": "2020-01-15",
            "notes": "Original trust corpus - 4BR/3BA Colonial", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "real_property", 
            "description": "Vacation Property - Beach Condo Unit 4B",
            "identifier": "Deed #2021-67890", 
            "location": "Rehoboth Beach, Delaware",
            "approximate_value": 425000, 
            "date_conveyed": "2021-06-01",
            "notes": "Added via property acceptance minutes - 2BR oceanfront", 
            "status": "active",
            "minutes_ref": property_acceptance_minutes_id,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "financial_accounts", 
            "description": "Schwab Brokerage Account - Growth Portfolio",
            "identifier": "Acct #****7890", 
            "location": "Charles Schwab",
            "approximate_value": 1250000, 
            "date_conveyed": "2020-01-15",
            "notes": "Primary investment account - diversified equity/bond mix", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "financial_accounts", 
            "description": "First National Bank - Operating Account",
            "identifier": "Acct #****1234", 
            "location": "First National Bank, DE",
            "approximate_value": 85000, 
            "date_conveyed": "2020-02-01",
            "notes": "Trust checking account for distributions", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "business_interests", 
            "description": "Smith Holdings LLC - 100% Membership Interest",
            "identifier": "Member Certificate #001", 
            "location": "Delaware",
            "approximate_value": 500000, 
            "date_conveyed": "2020-03-01",
            "notes": "Wholly-owned holding company", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        # DISPOSED Asset - Vehicle sold
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "personal_property", 
            "description": "2019 BMW X5 SUV",
            "identifier": "VIN: 5UXCR6C53KLL******", 
            "location": "Delaware",
            "approximate_value": 45000, 
            "date_conveyed": "2020-01-15",
            "notes": "Trust vehicle - sold to fund distribution", 
            "status": "disposed",
            "minutes_ref": None,
            "disposition_minutes_ref": vehicle_disposition_minutes_id,
            "disposition_date": (now - timedelta(days=120)).isoformat()[:10],
            "disposition_notes": "Reason: sale. Buyer: CarMax Delaware. Value: $38,500. Proceeds deposited to trust operating account.",
            "created_at": (now - timedelta(days=365)).isoformat()
        },
        # Active personal property
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "personal_property", 
            "description": "2023 Mercedes-Benz S-Class",
            "identifier": "VIN: WDDUG8FB2NA******", 
            "location": "Wilmington, Delaware",
            "approximate_value": 95000, 
            "date_conveyed": "2023-04-15",
            "notes": "Replacement trust vehicle", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "other_property", 
            "description": "Fine Art Collection - Various Works",
            "identifier": "Appraised Inventory #2023-001", 
            "location": "Family Residence",
            "approximate_value": 175000, 
            "date_conveyed": "2020-01-15",
            "notes": "12 paintings and 3 sculptures", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust1_id, 
            "user_id": user["user_id"],
            "category": "digital_assets", 
            "description": "Bitcoin Holdings",
            "identifier": "Wallet: bc1q****", 
            "location": "Cold Storage (Ledger)",
            "approximate_value": 125000, 
            "date_conveyed": "2021-11-01",
            "notes": "2.5 BTC acquired at $50,000 avg cost basis", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        # Trust 2 Assets
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust2_id, 
            "user_id": user["user_id"],
            "category": "financial_accounts", 
            "description": "529 Education Savings Account",
            "identifier": "Acct #****5678", 
            "location": "Fidelity Investments",
            "approximate_value": 250000, 
            "date_conveyed": "2023-01-15",
            "notes": "College savings - aggressive growth allocation", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        },
        {
            "item_id": f"asset_{uuid.uuid4().hex[:12]}", 
            "trust_id": trust2_id, 
            "user_id": user["user_id"],
            "category": "financial_accounts", 
            "description": "Trust Operating Account",
            "identifier": "Acct #****9999", 
            "location": "Wells Fargo",
            "approximate_value": 15000, 
            "date_conveyed": "2023-01-15",
            "notes": "Operating account for expenses", 
            "status": "active",
            "minutes_ref": None,
            "disposition_minutes_ref": None,
            "disposition_date": None,
            "disposition_notes": None,
            "created_at": now.isoformat()
        }
    ])
    
    # ==================== GOVERNANCE TASKS (Various statuses) ====================
    await db.governance_tasks.insert_many([
        # Trust 1 Tasks
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
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "tax_filing", "due_date": (now + timedelta(days=90)).isoformat(),
         "completed_at": None, "description": "File trust income tax returns", "created_at": now.isoformat()},
        # Trust 2 Tasks
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=120)).isoformat(),
         "completed_at": None, "description": "Annual education trust review", "created_at": now.isoformat()},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "beneficiary_review", "due_date": (now + timedelta(days=45)).isoformat(),
         "completed_at": None, "description": "Review beneficiary eligibility for fall semester", "created_at": now.isoformat()}
    ])
    
    # ==================== MINUTES RECORDS (Various types including disposition) ====================
    await db.minutes_records.insert_many([
        # Trust 1 Minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "quarterly", "meeting_date": (now - timedelta(days=15)).isoformat(),
         "participants_text": "John Smith (Trustee), Jane Smith (Trustee), Robert Attorney (Advisor)",
         "decisions_text": "Reviewed Q4 2025 performance. Approved education distribution for Emily. Confirmed investment strategy remains aligned with trust objectives.",
         "created_at": (now - timedelta(days=15)).isoformat()},
        # Property Acceptance Minutes
        {"minutes_id": property_acceptance_minutes_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=60)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Accept Beach Condo Unit 4B into trust corpus. Value: $425,000. Schedule A amended.",
         "generated_from_template": "acceptance_of_property",
         "template_data": {"property_description": "Beach Condo Unit 4B", "estimated_value": 425000},
         "created_at": (now - timedelta(days=60)).isoformat()},
        # Vehicle Disposition Minutes
        {"minutes_id": vehicle_disposition_minutes_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=120)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Approve the sale of the 2019 BMW X5 SUV (VIN: 5UXCR6C53KLL******) to CarMax Delaware for $38,500. Proceeds to be deposited into trust operating account. Schedule A amended to reflect removal.",
         "generated_from_template": "disposition_of_asset",
         "template_data": {
             "disposition_asset_description": "2019 BMW X5 SUV",
             "disposition_reason": "sale",
             "disposition_value": 38500,
             "disposition_recipient": "CarMax Delaware",
             "update_schedule_a": True
         },
         "created_at": (now - timedelta(days=120)).isoformat()},
        # Benevolence approval minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=45)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Approve $25,000 benevolent grant to Grace Community Church for youth ministry programs.",
         "generated_from_template": "benevolence_approval",
         "template_data": {"beneficiary_name": "Grace Community Church", "amount": 25000},
         "created_at": (now - timedelta(days=45)).isoformat()},
        # Distribution minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "distribution", "meeting_date": (now - timedelta(days=30)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "Approved $15,000 distribution to Emily Smith for spring semester tuition. Solvency confirmed.",
         "created_at": (now - timedelta(days=30)).isoformat()},
        # General meeting with multiple resolutions
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=180)).isoformat(),
         "participants_text": "John Smith, Jane Smith, Attorney Bob Wilson",
         "decisions_text": "Annual review completed. 1) Reviewed all distributions for the year. 2) Confirmed Schedule A accuracy. 3) Approved trustee compensation continuation. 4) Reaffirmed investment policy statement.",
         "created_at": (now - timedelta(days=180)).isoformat()},
        # Trust 2 Minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=90)).isoformat(),
         "participants_text": "John Smith",
         "decisions_text": "Annual review of education trust. 529 account performing well. Reviewed beneficiary designations.",
         "created_at": (now - timedelta(days=90)).isoformat()}
    ])
    
    # ==================== DISTRIBUTIONS (Approved and Pending) ====================
    await db.distribution_records.insert_many([
        # Trust 1 Distributions
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 15000, "date": (now - timedelta(days=10)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(a)",
         "notes": "Spring 2026 semester tuition - State University", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=10)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=10)).isoformat()},
        # PENDING distribution (not yet approved)
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
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "James Smith Jr.", "amount": 5000, "date": (now - timedelta(days=75)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(c)",
         "notes": "First car purchase assistance", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=74)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=75)).isoformat()},
        # Trust 2 Distribution
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "beneficiary_name": "Sarah Johnson", "amount": 12000, "date": (now - timedelta(days=20)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article III",
         "notes": "College tuition - freshman year", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=20)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=20)).isoformat()}
    ])
    
    # ==================== BENEVOLENCE RECORDS (Trust 1 only) ====================
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
         "minutes_id": None, "notes": "New job starting next month", "created_at": (now - timedelta(days=7)).isoformat()},
        # PENDING benevolence request
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Hope Academy", "beneficiary_type": "organization", "purpose": "education",
         "purpose_description": "Scholarship fund for underprivileged students",
         "amount": 10000, "date": (now - timedelta(days=2)).isoformat(),
         "approved_by": [], "approval_method": "pending", "status": "pending",
         "minutes_id": None, "notes": "PENDING APPROVAL - Requested by school principal", "created_at": (now - timedelta(days=2)).isoformat()}
    ])
    
    # ==================== COMPENSATION PLANS AND PAYMENTS ====================
    await db.compensation_plans.insert_many([
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()},
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat()}
    ])
    
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
    
    # ==================== TRUST UNIT CERTIFICATES (Trust 1) ====================
    await db.trust_unit_settings.insert_one({
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "total_authorized_units": 1000,
        "unit_label": "Certificate Unit",
        "allow_fractional": False,
        "created_at": now.isoformat()
    })
    
    await db.trust_unit_certificates.insert_many([
        {"certificate_id": f"cert_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-001", "holder_name": "Emily Smith", "holder_identifier": "Beneficiary - Daughter",
         "units": 400, "issue_date": "2020-01-15", "status": "active",
         "notes": "Primary beneficiary - 40% interest", "created_at": now.isoformat()},
        {"certificate_id": f"cert_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-002", "holder_name": "Michael Smith", "holder_identifier": "Beneficiary - Son",
         "units": 400, "issue_date": "2020-01-15", "status": "active",
         "notes": "Primary beneficiary - 40% interest", "created_at": now.isoformat()},
        {"certificate_id": f"cert_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-003", "holder_name": "James Smith Jr.", "holder_identifier": "Beneficiary - Grandson",
         "units": 200, "issue_date": "2022-06-01", "status": "active",
         "notes": "Contingent beneficiary - 20% interest", "created_at": now.isoformat()}
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
    
    return {
        "message": "Demo data created with 2 trusts showcasing all features",
        "seeded": True,
        "trust_ids": [trust1_id, trust2_id],
        "features_demonstrated": [
            "Multiple trusts with different configurations",
            "Entity hierarchy (Trust -> Holding LLC -> Operating LLCs)",
            "Schedule A with active and disposed assets",
            "Various minutes types (quarterly, annual, special, distribution)",
            "Disposition minutes with Schedule A update",
            "Property acceptance minutes",
            "Distributions (approved and pending)",
            "Benevolence records with multiple purposes",
            "Compensation plans and payment history",
            "Trust unit certificates",
            "Governance tasks (upcoming, overdue, completed)"
        ]
    }


@router.delete("/data")
async def delete_demo_data(user: dict = Depends(require_write_access)):
    """
    Delete all user data (trusts and related records).
    This allows users to start fresh or clean up demo data.
    CAUTION: This action is irreversible!
    """
    user_id = user["user_id"]
    
    # Track what was deleted
    deleted_counts = {}
    
    # Delete in order (children first, then parents)
    collections_to_clean = [
        ("trust_unit_certificates", "trust_unit_certificates"),
        ("trust_unit_transfers", "trust_unit_transfers"),
        ("trust_unit_settings", "trust_unit_settings"),
        ("compensation_payments", "compensation_payments"),
        ("compensation_plans", "compensation_plans"),
        ("benevolence_records", "benevolence_records"),
        ("distribution_records", "distribution_records"),
        ("schedule_a_items", "schedule_a_items"),
        ("minutes_records", "minutes_records"),
        ("governance_tasks", "governance_tasks"),
        ("entity_relationships", "entity_relationships"),
        ("entities", "entities"),
        ("health_score_snapshots", "health_score_snapshots"),
        ("trusts", "trusts"),
    ]
    
    for collection_name, display_name in collections_to_clean:
        collection = db[collection_name]
        result = await collection.delete_many({"user_id": user_id})
        if result.deleted_count > 0:
            deleted_counts[display_name] = result.deleted_count
    
    # Keep notification preferences and subscription - just reset preferences
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": {
            "minutes_created": True,
            "distribution_created": True,
            "distribution_approved": True,
            "task_reminders": True,
            "task_overdue": True,
            "subscription_updates": True,
            "weekly_digest": True
        }},
        upsert=True
    )
    
    total_deleted = sum(deleted_counts.values())
    
    return {
        "message": f"Successfully deleted {total_deleted} records",
        "deleted_counts": deleted_counts,
        "notes": "Subscription and notification preferences were preserved. You can now seed new demo data with POST /api/demo/seed"
    }


@router.get("/status")
async def get_demo_status(user: dict = Depends(get_current_user)):
    """
    Check if user has demo data and get counts of all records.
    Useful for determining if demo data should be seeded or deleted.
    """
    user_id = user["user_id"]
    
    counts = {
        "trusts": await db.trusts.count_documents({"user_id": user_id}),
        "entities": await db.entities.count_documents({"user_id": user_id}),
        "schedule_a_items": await db.schedule_a_items.count_documents({"user_id": user_id}),
        "minutes_records": await db.minutes_records.count_documents({"user_id": user_id}),
        "distribution_records": await db.distribution_records.count_documents({"user_id": user_id}),
        "benevolence_records": await db.benevolence_records.count_documents({"user_id": user_id}),
        "governance_tasks": await db.governance_tasks.count_documents({"user_id": user_id}),
        "compensation_plans": await db.compensation_plans.count_documents({"user_id": user_id}),
        "compensation_payments": await db.compensation_payments.count_documents({"user_id": user_id}),
        "trust_unit_certificates": await db.trust_unit_certificates.count_documents({"user_id": user_id}),
    }
    
    total = sum(counts.values())
    has_data = total > 0
    
    return {
        "has_data": has_data,
        "total_records": total,
        "counts": counts,
        "can_seed": not has_data,
        "can_delete": has_data
    }
