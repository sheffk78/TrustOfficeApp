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
- Transactions
- Tax calendar entries
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
    Only seeds if no demo data exists (allows seeding alongside user's own trusts).
    """
    # Check if demo data already exists (not all trusts, just demo trusts)
    existing_demo = await db.trusts.count_documents({"user_id": user["user_id"], "is_demo": True})
    if existing_demo > 0:
        return {"message": "Demo data already exists", "seeded": False}
    
    now = datetime.now(timezone.utc)
    
    # ==================== TRUST 1: Smith Family Trust (Full featured with Benevolence) ====================
    trust1_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "name": "Smith Family Trust",
        "trust_type": "family",
        "jurisdiction": "Delaware",
        "state_code": "DE",
        "ein": "12-3456789",
        "start_date": "2020-01-15",
        "tax_year_end_month": 12,
        "tax_year_end_day": 31,
        "is_fiscal_year": False,
        "benevolence_enabled": True,
        "tax_status": "501c3",
        "description": "Irrevocable family trust for asset protection and generational wealth transfer.",
        "review_cadence": "quarterly",
        "role": "Trustee",
        "created_at": now.isoformat(),
        "is_demo": True
    })
    
    # ==================== TRUST 2: Johnson Education Trust ====================
    trust2_id = f"trust_{uuid.uuid4().hex[:12]}"
    
    await db.trusts.insert_one({
        "trust_id": trust2_id,
        "user_id": user["user_id"],
        "name": "Johnson Education Trust",
        "trust_type": "family",
        "jurisdiction": "California",
        "state_code": "CA",
        "ein": "98-7654321",
        "start_date": "2023-01-01",
        "tax_year_end_month": 6,
        "tax_year_end_day": 30,
        "is_fiscal_year": True,
        "benevolence_enabled": False,
        "description": "Education trust for grandchildren's college expenses.",
        "review_cadence": "annual",
        "role": "Trustee",
        "created_at": now.isoformat(),
        "is_demo": True
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
        "created_at": now.isoformat(),
        "is_demo": True
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
        "created_at": now.isoformat(),
        "is_demo": True
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
        "created_at": now.isoformat(),
        "is_demo": True
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
        "created_at": now.isoformat(),
        "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
        "created_at": now.isoformat(),
        "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": (now - timedelta(days=365)).isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
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
            "created_at": now.isoformat(),
            "is_demo": True
        }
    ])
    
    # ==================== GOVERNANCE TASKS (Various statuses) ====================
    await db.governance_tasks.insert_many([
        # Trust 1 Tasks
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=60)).isoformat(),
         "completed_at": None, "description": "Annual trust administration review", "created_at": now.isoformat(), "is_demo": True},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "quarterly_review", "due_date": (now + timedelta(days=30)).isoformat(),
         "completed_at": None, "description": "Q1 2026 quarterly review", "created_at": now.isoformat(), "is_demo": True},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "compensation_review", "due_date": (now - timedelta(days=5)).isoformat(),
         "completed_at": None, "description": "Review trustee compensation for 2026 (OVERDUE)", "created_at": (now - timedelta(days=30)).isoformat(), "is_demo": True},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "distribution_review", "due_date": (now + timedelta(days=15)).isoformat(),
         "completed_at": (now - timedelta(days=2)).isoformat(), "description": "Review Q4 distributions - COMPLETED", "created_at": (now - timedelta(days=20)).isoformat(), "is_demo": True},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "task_type": "tax_filing", "due_date": (now + timedelta(days=90)).isoformat(),
         "completed_at": None, "description": "File trust income tax returns", "created_at": now.isoformat(), "is_demo": True},
        # Trust 2 Tasks
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "annual_review", "due_date": (now + timedelta(days=120)).isoformat(),
         "completed_at": None, "description": "Annual education trust review", "created_at": now.isoformat(), "is_demo": True},
        {"task_id": f"task_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "task_type": "beneficiary_review", "due_date": (now + timedelta(days=45)).isoformat(),
         "completed_at": None, "description": "Review beneficiary eligibility for fall semester", "created_at": now.isoformat(), "is_demo": True}
    ])
    
    # ==================== MINUTES RECORDS (Various types including disposition) ====================
    await db.minutes_records.insert_many([
        # Trust 1 Minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "quarterly", "meeting_date": (now - timedelta(days=15)).isoformat(),
         "participants_text": "John Smith (Trustee), Jane Smith (Trustee), Robert Attorney (Advisor)",
         "decisions_text": "Reviewed Q4 2025 performance. Approved education distribution for Emily. Confirmed investment strategy remains aligned with trust objectives.",
         "created_at": (now - timedelta(days=15)).isoformat(), "is_demo": True},
        # Property Acceptance Minutes
        {"minutes_id": property_acceptance_minutes_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=60)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Accept Beach Condo Unit 4B into trust corpus. Value: $425,000. Schedule A amended.",
         "generated_from_template": "acceptance_of_property",
         "template_data": {"property_description": "Beach Condo Unit 4B", "estimated_value": 425000},
         "created_at": (now - timedelta(days=60)).isoformat(), "is_demo": True},
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
         "created_at": (now - timedelta(days=120)).isoformat(), "is_demo": True},
        # Benevolence approval minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=45)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Approve $25,000 benevolent grant to Grace Community Church for youth ministry programs.",
         "generated_from_template": "benevolence_approval",
         "template_data": {"beneficiary_name": "Grace Community Church", "amount": 25000},
         "created_at": (now - timedelta(days=45)).isoformat(), "is_demo": True},
        # Distribution minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "distribution", "meeting_date": (now - timedelta(days=30)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "Approved $15,000 distribution to Emily Smith for spring semester tuition. Solvency confirmed.",
         "created_at": (now - timedelta(days=30)).isoformat(), "is_demo": True},
        # General meeting with multiple resolutions
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=180)).isoformat(),
         "participants_text": "John Smith, Jane Smith, Attorney Bob Wilson",
         "decisions_text": "Annual review completed. 1) Reviewed all distributions for the year. 2) Confirmed Schedule A accuracy. 3) Approved trustee compensation continuation. 4) Reaffirmed investment policy statement.",
         "created_at": (now - timedelta(days=180)).isoformat(),
         "is_demo": True},
        # Bank Account Authorization
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=250)).isoformat(),
         "participants_text": "John Smith, Jane Smith",
         "decisions_text": "RESOLVED: Authorize opening a trust brokerage account at Charles Schwab for investment management purposes.",
         "generated_from_template": "bank_account_authorization",
         "template_data": {"bank_name": "Charles Schwab", "account_type": "Brokerage", "signatories": ["John Smith", "Jane Smith"]},
         "created_at": (now - timedelta(days=250)).isoformat(),
         "is_demo": True},
        # Investment Policy
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=200)).isoformat(),
         "participants_text": "John Smith, Jane Smith, Financial Advisor Mark Thompson",
         "decisions_text": "RESOLVED: Adopt Investment Policy Statement with 60/40 equity-bond allocation, quarterly rebalancing, and ESG screening criteria.",
         "generated_from_template": "investment_policy",
         "template_data": {"allocation": "60/40 equity-bond", "review_frequency": "quarterly"},
         "created_at": (now - timedelta(days=200)).isoformat(),
         "is_demo": True},
        # Trustee Compensation Approval
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "minutes_type": "special", "meeting_date": (now - timedelta(days=365)).isoformat(),
         "participants_text": "John Smith, Jane Smith, Attorney Bob Wilson",
         "decisions_text": "RESOLVED: Approve annual trustee compensation of $24,000 per trustee, payable quarterly. Compensation is reasonable based on trust size and complexity.",
         "generated_from_template": "trustee_compensation",
         "template_data": {"annual_fee": 24000, "payment_frequency": "quarterly"},
         "created_at": (now - timedelta(days=365)).isoformat(),
         "is_demo": True},
        # Trust 2 Minutes
        {"minutes_id": f"minutes_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "minutes_type": "annual", "meeting_date": (now - timedelta(days=90)).isoformat(),
         "participants_text": "John Smith",
         "decisions_text": "Annual review of education trust. 529 account performing well. Reviewed beneficiary designations.",
         "created_at": (now - timedelta(days=90)).isoformat(),
         "is_demo": True}
    ])
    
    # ==================== DISTRIBUTIONS (Approved and Pending) ====================
    await db.distribution_records.insert_many([
        # Trust 1 Distributions
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 15000, "date": (now - timedelta(days=10)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(a)",
         "notes": "Spring 2026 semester tuition - State University", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=10)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=10)).isoformat(), "is_demo": True},
        # PENDING distribution (not yet approved)
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Emily Smith", "amount": 2500, "date": (now - timedelta(days=3)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(b)",
         "notes": "Monthly living allowance - PENDING APPROVAL", "solvency_confirmed": False,
         "recusal_acknowledged": False, "approved_by": None, "approved_at": None,
         "minutes_record_id": None, "created_at": (now - timedelta(days=3)).isoformat(), "is_demo": True},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Michael Smith", "amount": 8000, "date": (now - timedelta(days=45)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.2",
         "notes": "Medical expenses - dental surgery", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=44)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=45)).isoformat(), "is_demo": True},
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "James Smith Jr.", "amount": 5000, "date": (now - timedelta(days=75)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article IV, Section 4.1(c)",
         "notes": "First car purchase assistance", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=74)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=75)).isoformat(), "is_demo": True},
        # Trust 2 Distribution
        {"distribution_id": f"dist_{uuid.uuid4().hex[:12]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "beneficiary_name": "Sarah Johnson", "amount": 12000, "date": (now - timedelta(days=20)).isoformat(),
         "purpose_classification": "distribution", "authority_clause_ref": "Article III",
         "notes": "College tuition - freshman year", "solvency_confirmed": True,
         "recusal_acknowledged": True, "approved_by": user["user_id"], "approved_at": (now - timedelta(days=20)).isoformat(),
         "minutes_record_id": None, "created_at": (now - timedelta(days=20)).isoformat(), "is_demo": True}
    ])
    
    # ==================== BENEVOLENCE RECORDS (Trust 1 only) ====================
    await db.benevolence_records.insert_many([
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Grace Community Church", "beneficiary_type": "organization", "purpose": "spiritual",
         "purpose_description": "Annual ministry support for youth programs and community outreach",
         "amount": 25000, "date": (now - timedelta(days=45)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "5th consecutive year of support", "created_at": (now - timedelta(days=45)).isoformat(), "is_demo": True},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Johnson Family", "beneficiary_type": "family", "purpose": "medical",
         "purpose_description": "Cancer treatment expenses - chemotherapy and hospital bills",
         "amount": 15000, "date": (now - timedelta(days=30)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Referred by Pastor Williams", "created_at": (now - timedelta(days=30)).isoformat(), "is_demo": True},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Maria Rodriguez", "beneficiary_type": "individual", "purpose": "education",
         "purpose_description": "Community college tuition for nursing program",
         "amount": 4500, "date": (now - timedelta(days=20)).isoformat(),
         "approved_by": ["John Smith"], "approval_method": "majority", "status": "approved",
         "minutes_id": None, "notes": "Single mother pursuing RN degree", "created_at": (now - timedelta(days=20)).isoformat(), "is_demo": True},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Local Food Bank", "beneficiary_type": "organization", "purpose": "food_necessities",
         "purpose_description": "Thanksgiving meal packages for 200 families",
         "amount": 5000, "date": (now - timedelta(days=90)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "Annual holiday contribution", "created_at": (now - timedelta(days=90)).isoformat(), "is_demo": True},
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Thomas Williams", "beneficiary_type": "individual", "purpose": "housing",
         "purpose_description": "Emergency rent assistance - 2 months rent after job loss",
         "amount": 3200, "date": (now - timedelta(days=7)).isoformat(),
         "approved_by": ["John Smith", "Jane Smith"], "approval_method": "unanimous", "status": "approved",
         "minutes_id": None, "notes": "New job starting next month", "created_at": (now - timedelta(days=7)).isoformat(), "is_demo": True},
        # PENDING benevolence request
        {"record_id": f"ben_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "beneficiary_name": "Hope Academy", "beneficiary_type": "organization", "purpose": "education",
         "purpose_description": "Scholarship fund for underprivileged students",
         "amount": 10000, "date": (now - timedelta(days=2)).isoformat(),
         "approved_by": [], "approval_method": "pending", "status": "pending",
         "minutes_id": None, "notes": "PENDING APPROVAL - Requested by school principal", "created_at": (now - timedelta(days=2)).isoformat(), "is_demo": True}
    ])
    
    # ==================== COMPENSATION PLANS AND PAYMENTS ====================
    await db.compensation_plans.insert_many([
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat(), "is_demo": True},
        {"plan_id": f"plan_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "annual_fee": 24000, "fee_type": "fixed",
         "effective_date": "2024-01-01", "notes": "Fixed quarterly payments of $6,000", "created_at": now.isoformat(), "is_demo": True}
    ])
    
    await db.compensation_payments.insert_many([
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "date": (now - timedelta(days=90)).isoformat(),
         "classification_text": "Q4 2025 compensation", "exceeds_plan_flag": False,
         "plan_id": None, "minutes_record_id": None,
         "created_at": (now - timedelta(days=90)).isoformat(), "is_demo": True},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "date": (now - timedelta(days=90)).isoformat(),
         "classification_text": "Q4 2025 compensation", "exceeds_plan_flag": False,
         "plan_id": None, "minutes_record_id": None,
         "created_at": (now - timedelta(days=90)).isoformat(), "is_demo": True},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "John Smith", "amount": 6000, "date": (now - timedelta(days=5)).isoformat(),
         "classification_text": "Q1 2026 compensation", "exceeds_plan_flag": False,
         "plan_id": None, "minutes_record_id": None,
         "created_at": (now - timedelta(days=5)).isoformat(), "is_demo": True},
        {"payment_id": f"pay_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "trustee_name": "Jane Smith", "amount": 6000, "date": (now - timedelta(days=5)).isoformat(),
         "classification_text": "Q1 2026 compensation", "exceeds_plan_flag": False,
         "plan_id": None, "minutes_record_id": None,
         "created_at": (now - timedelta(days=5)).isoformat(), "is_demo": True}
    ])
    
    # ==================== TRUST UNIT CERTIFICATES (Trust 1) ====================
    await db.trust_unit_settings.insert_one({
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "total_authorized_units": 100,
        "unit_label": "Certificate Unit",
        "allow_fractional": False,
        "created_at": now.isoformat(),
        "is_demo": True
    })
    
    # Generate certificate IDs for transfer history
    cert1_id = f"cert_{uuid.uuid4().hex[:12]}"
    cert2_id = f"cert_{uuid.uuid4().hex[:12]}"
    cert3_id = f"cert_{uuid.uuid4().hex[:12]}"
    cert4_id = f"cert_{uuid.uuid4().hex[:12]}"
    
    await db.trust_unit_certificates.insert_many([
        {"certificate_id": cert1_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-001", "holder_name": "Emily Smith", "holder_identifier": "Beneficiary - Daughter",
         "units": 25, "issue_date": "2020-01-15", "status": "active",
         "notes": "Primary beneficiary - 25% interest", "created_at": now.isoformat(), "is_demo": True},
        {"certificate_id": cert2_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-002", "holder_name": "Michael Smith", "holder_identifier": "Beneficiary - Son",
         "units": 30, "issue_date": "2020-01-15", "status": "active",
         "notes": "Primary beneficiary - 30% interest", "created_at": now.isoformat(), "is_demo": True},
        {"certificate_id": cert3_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-003", "holder_name": "James Smith Jr.", "holder_identifier": "Beneficiary - Grandson",
         "units": 15, "issue_date": "2022-06-01", "status": "active",
         "notes": "Contingent beneficiary - 15% interest", "created_at": now.isoformat(), "is_demo": True},
        {"certificate_id": cert4_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "certificate_number": "CERT-004", "holder_name": "Sarah Smith", "holder_identifier": "Beneficiary - Spouse",
         "units": 30, "issue_date": "2020-01-15", "status": "active",
         "notes": "Primary beneficiary - 30% interest", "created_at": now.isoformat(), "is_demo": True}
    ])
    
    # ==================== TRUST UNIT TRANSFERS (Transfer History) ====================
    await db.trust_unit_transfers.insert_many([
        {"transfer_id": f"transfer_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "from_holder": "Sarah Smith", "to_holder": "James Smith Jr.",
         "units": 5, "reason": "Gift to grandson for college graduation",
         "transfer_date": (now - timedelta(days=180)).isoformat(),
         "created_at": (now - timedelta(days=180)).isoformat(), "is_demo": True},
        {"transfer_id": f"transfer_{uuid.uuid4().hex[:12]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "from_holder": "Michael Smith", "to_holder": "Emily Smith",
         "units": 5, "reason": "Voluntary reallocation per family agreement",
         "transfer_date": (now - timedelta(days=90)).isoformat(),
         "created_at": (now - timedelta(days=90)).isoformat(), "is_demo": True}
    ])
    
    # ==================== NOTIFICATION PREFERENCES ====================
    await db.notification_preferences.update_one(
        {"user_id": user["user_id"]},
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

    # ==================== TRANSACTIONS (Trust 1 - Money module) ====================
    await db.transactions.insert_many([
        {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "entity_id": trust1_entity_id,
            "user_id": user["user_id"],
            "amount": 15000,
            "date": (now - timedelta(days=10)).isoformat(),
            "direction": "outflow",
            "source_account": "Trust Operating Account",
            "destination_account": "State University Bursar",
            "governance_classification": "Distribution",
            "purpose_memo": "Educational distribution to Emily Smith - Spring tuition",
            "other_note": "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now.isoformat(),
            "updated_at": None,
            "is_demo": True
        },
        {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "entity_id": trust1_entity_id,
            "user_id": user["user_id"],
            "amount": 6000,
            "date": (now - timedelta(days=5)).isoformat(),
            "direction": "outflow",
            "source_account": "Trust Operating Account",
            "destination_account": "John Smith Personal Account",
            "governance_classification": "Compensation",
            "purpose_memo": "Q1 2026 Trustee compensation - John Smith",
            "other_note": "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now.isoformat(),
            "updated_at": None,
            "is_demo": True
        },
        {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "entity_id": trust1_entity_id,
            "user_id": user["user_id"],
            "amount": 38500,
            "date": (now - timedelta(days=120)).isoformat(),
            "direction": "inflow",
            "source_account": "CarMax Delaware",
            "destination_account": "Trust Operating Account",
            "governance_classification": "Capital Contribution",
            "purpose_memo": "Sale of 2019 BMW X5 to CarMax Delaware",
            "other_note": "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now.isoformat(),
            "updated_at": None,
            "is_demo": True
        },
        {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "entity_id": trust1_entity_id,
            "user_id": user["user_id"],
            "amount": 12500,
            "date": (now - timedelta(days=14)).isoformat(),
            "direction": "inflow",
            "source_account": "Schwab Brokerage",
            "destination_account": "Trust Operating Account",
            "governance_classification": "Inter-Entity Transfer",
            "purpose_memo": "Q1 2026 dividend distribution - Schwab Growth Portfolio",
            "other_note": "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now.isoformat(),
            "updated_at": None,
            "is_demo": True
        },
        {
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "entity_id": trust1_entity_id,
            "user_id": user["user_id"],
            "amount": 850,
            "date": (now - timedelta(days=60)).isoformat(),
            "direction": "outflow",
            "source_account": "Trust Operating Account",
            "destination_account": "Delaware Division of Corporations",
            "governance_classification": "Operational Expense",
            "purpose_memo": "Annual trust filing fee - Delaware Division of Corporations",
            "other_note": "",
            "linked_distribution_id": None,
            "linked_compensation_payment_id": None,
            "document_name": None,
            "import_batch_id": None,
            "created_at": now.isoformat(),
            "updated_at": None,
            "is_demo": True
        },
    ])

    # ==================== TAX CALENDAR ENTRIES ====================
    await db.tax_calendar.insert_many([
        {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "tax_year": 2026,
            "deadline_type": "federal_1041",
            "description": "Federal trust income tax return (Form 1041)",
            "due_date": (now + timedelta(days=90)).isoformat(),
            "filing_status": "pending",
            "filed_date": None,
            "notes": "Estimated based on prior year income",
            "accountant_engaged": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_demo": True
        },
        {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "tax_year": 2026,
            "deadline_type": "state_fiduciary",
            "description": "Delaware state trust income tax return",
            "due_date": (now + timedelta(days=90)).isoformat(),
            "filing_status": "not_required",
            "filed_date": None,
            "notes": "Delaware does not tax trusts on accumulated income",
            "accountant_engaged": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_demo": True
        },
        {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "tax_year": 2026,
            "deadline_type": "estimated_q2",
            "description": "Estimated tax payment - Q2 2026",
            "due_date": (now + timedelta(days=45)).isoformat(),
            "filing_status": "pending",
            "filed_date": None,
            "notes": "Quarterly estimated payment",
            "accountant_engaged": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_demo": True
        },
        {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id,
            "user_id": user["user_id"],
            "tax_year": 2025,
            "deadline_type": "federal_1041_extension",
            "description": "Form 1041 extension filed",
            "due_date": (now - timedelta(days=60)).isoformat(),
            "filing_status": "filed",
            "filed_date": (now - timedelta(days=60)).isoformat(),
            "notes": "Extension granted to September 15",
            "accountant_engaged": True,
            "created_at": (now - timedelta(days=60)).isoformat(),
            "updated_at": (now - timedelta(days=60)).isoformat(),
            "is_demo": True
        },
        {
            "entry_id": f"tax_{uuid.uuid4().hex[:12]}",
            "trust_id": trust2_id,
            "user_id": user["user_id"],
            "tax_year": 2026,
            "deadline_type": "state_fiduciary",
            "description": "California state trust tax filing",
            "due_date": (now + timedelta(days=120)).isoformat(),
            "filing_status": "pending",
            "filed_date": None,
            "notes": "Small trust - minimal CA tax exposure",
            "accountant_engaged": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "is_demo": True
        },
    ])

    # ==================== CLASS BENEFICIARIES (Beneficiary Dashboard) ====================
    await db.class_beneficiaries.insert_many([
        {"class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "class_type": "children", "class_type_label": "Children (including after-born)",
         "description": "Primary class — all living children of the grantor",
         "percentage": 60, "notes": "Per stirpes distribution among children",
         "created_at": now.isoformat(), "is_demo": True},
        {"class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}", "trust_id": trust1_id, "user_id": user["user_id"],
         "class_type": "descendants", "class_type_label": "Descendants",
         "description": "Contingent class — lineal descendants per stirpes",
         "percentage": 40, "notes": "Includes grandchildren if primary class predeceases",
         "created_at": now.isoformat(), "is_demo": True},
        {"class_beneficiary_id": f"cb_{uuid.uuid4().hex[:16]}", "trust_id": trust2_id, "user_id": user["user_id"],
         "class_type": "descendants", "class_type_label": "Descendants",
         "description": "Grandchildren eligible for education distributions",
         "percentage": 100, "notes": "All grandchildren of the grantor",
         "created_at": now.isoformat(), "is_demo": True},
    ])

    # ==================== VAULT DOCUMENTS (Reference-only, no binary) ====================
    vault_doc1_id = f"doc_{uuid.uuid4().hex[:12]}"
    vault_doc2_id = f"doc_{uuid.uuid4().hex[:12]}"
    vault_doc3_id = f"doc_{uuid.uuid4().hex[:12]}"
    vault_doc4_id = f"doc_{uuid.uuid4().hex[:12]}"
    vault_doc5_id = f"doc_{uuid.uuid4().hex[:12]}"
    vault_doc6_id = f"doc_{uuid.uuid4().hex[:12]}"

    await db.vault_documents.insert_many([
        {"doc_id": vault_doc1_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "title": "Smith Family Trust Agreement", "category": "trust_instrument",
         "category_label": "Trust Instrument / Governing Document", "date": "2020-01-15",
         "description": "Original irrevocable trust agreement executed January 15, 2020",
         "storage_provider": "google_drive", "storage_url": "https://drive.google.com/file/d/demo_smith_trust",
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["original", "executed"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=400)).isoformat(), "updated_at": (now - timedelta(days=400)).isoformat(),
         "is_demo": True},
        {"doc_id": vault_doc2_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "title": "EIN Confirmation Letter (CP575)", "category": "ein_letter",
         "category_label": "EIN Confirmation Letter (CP575)", "date": "2020-01-20",
         "description": "IRS CP575 confirming EIN 12-3456789 for Smith Family Trust",
         "storage_provider": "local_server", "storage_url": None,
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["IRS", "EIN"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=395)).isoformat(), "updated_at": (now - timedelta(days=395)).isoformat(),
         "is_demo": True},
        {"doc_id": vault_doc3_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "title": "2025 Form 1041 - Federal Trust Tax Return", "category": "tax_return",
         "category_label": "Tax Return (Form 1041)", "date": "2026-03-15",
         "description": "Federal trust income tax return for tax year 2025",
         "storage_provider": "google_drive", "storage_url": "https://drive.google.com/file/d/demo_1041_2025",
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["tax", "2025", "1041"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=100)).isoformat(), "updated_at": (now - timedelta(days=100)).isoformat(),
         "is_demo": True},
        {"doc_id": vault_doc4_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "title": "Beach Condo Property Appraisal", "category": "appraisal",
         "category_label": "Asset Appraisal / Valuation", "date": "2021-06-01",
         "description": "Independent appraisal for Beach Condo Unit 4B - $425,000",
         "storage_provider": "google_drive", "storage_url": "https://drive.google.com/file/d/demo_appraisal",
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["real_estate", "appraisal"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=60)).isoformat(), "updated_at": (now - timedelta(days=60)).isoformat(),
         "is_demo": True},
        {"doc_id": vault_doc5_id, "trust_id": trust1_id, "user_id": user["user_id"],
         "title": "Investment Policy Statement", "category": "other",
         "category_label": "Other", "date": "2025-10-01",
         "description": "60/40 equity-bond allocation with quarterly rebalancing and ESG screening",
         "storage_provider": "google_drive", "storage_url": "https://drive.google.com/file/d/demo_ips",
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["investment", "policy"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=200)).isoformat(), "updated_at": (now - timedelta(days=200)).isoformat(),
         "is_demo": True},
        {"doc_id": vault_doc6_id, "trust_id": trust2_id, "user_id": user["user_id"],
         "title": "Johnson Education Trust Agreement", "category": "trust_instrument",
         "category_label": "Trust Instrument / Governing Document", "date": "2023-01-01",
         "description": "Original education trust agreement for grandchildren",
         "storage_provider": "google_drive", "storage_url": "https://drive.google.com/file/d/demo_johnson_trust",
         "storage_path": None, "file_name": None, "file_size": None, "tags": ["original", "education"],
         "expiration_date": None, "needs_renewal": False,
         "created_at": (now - timedelta(days=300)).isoformat(), "updated_at": (now - timedelta(days=300)).isoformat(),
         "is_demo": True},
    ])

    # ==================== TRUST DOCUMENT ANALYSIS (AI Document Intelligence) ====================
    await db.trust_document_analysis.insert_one({
        "analysis_id": f"tda_{vault_doc1_id[:20]}_{(now - timedelta(days=395)).strftime('%Y%m%d%H%M%S')}",
        "trust_id": trust1_id,
        "user_id": user["user_id"],
        "vault_document_id": vault_doc1_id,
        "is_amendment": False,
        "status": "complete",
        "extracted_fields": {
            "grantor": "John Smith",
            "trustee_names": ["John Smith", "Jane Smith"],
            "trust_type": "Irrevocable Family Trust",
            "beneficiary_names": ["Emily Smith", "Michael Smith", "James Smith Jr.", "Sarah Smith"],
            "distribution_standard": "Health, Education, Maintenance, and Support (HEMS)",
            "trust_formation_date": "January 15, 2020",
            "ein": "12-3456789",
            "governing_law": "Delaware",
            "trustee_powers": "General administrative powers including investment, real property acquisition/sale, and borrowing",
            "termination_rules": "Terminates upon death of last beneficiary or 21 years after rule against perpetuities",
            "compensation_clause": "Article V, Section 5.2 - Reasonable compensation for trustees",
            "amendment_clause": "Article VIII - Amendments require unanimous trustee consent",
        },
        "raw_text_length": 15420,
        "error_message": None,
        "created_at": (now - timedelta(days=395)).isoformat(),
        "updated_at": (now - timedelta(days=390)).isoformat(),
        "is_demo": True
    })

    # ==================== HEALTH SCORE SNAPSHOTS ====================
    await db.health_score_snapshots.insert_many([
        {
            "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id, "user_id": user["user_id"],
            "schema_version": 2,
            "base_score": 75, "risk_penalty": 0, "score_value": 75,
            "color": "yellow",
            "calculated_at": (now - timedelta(days=90)).isoformat(),
            "criteria_breakdown": [
                {"name": "Trust profile complete", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Entities structured", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Minutes documented", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Schedule A current", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Beneficiaries designated", "points": 15, "max_points": 15, "achieved": True},
            ],
            "risk_findings_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "is_demo": True
        },
        {
            "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
            "trust_id": trust1_id, "user_id": user["user_id"],
            "schema_version": 2,
            "base_score": 90, "risk_penalty": 5, "score_value": 85,
            "color": "green",
            "calculated_at": (now - timedelta(days=7)).isoformat(),
            "criteria_breakdown": [
                {"name": "Trust profile complete", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Entities structured", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Minutes documented", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Schedule A current", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Beneficiaries designated", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Trust document uploaded", "points": 15, "max_points": 15, "achieved": True},
            ],
            "risk_findings_count": {"critical": 0, "high": 0, "medium": 1, "low": 0},
            "is_demo": True
        },
        {
            "snapshot_id": f"health_{uuid.uuid4().hex[:12]}",
            "trust_id": trust2_id, "user_id": user["user_id"],
            "schema_version": 2,
            "base_score": 60, "risk_penalty": 0, "score_value": 60,
            "color": "yellow",
            "calculated_at": (now - timedelta(days=30)).isoformat(),
            "criteria_breakdown": [
                {"name": "Trust profile complete", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Entities structured", "points": 0, "max_points": 15, "achieved": False},
                {"name": "Minutes documented", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Schedule A current", "points": 15, "max_points": 15, "achieved": True},
                {"name": "Beneficiaries designated", "points": 15, "max_points": 15, "achieved": True},
            ],
            "risk_findings_count": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "is_demo": True
        },
    ])

    # ==================== TRUST ASSISTANT CHAT HISTORY ====================
    conv1_id = f"conv_{uuid.uuid4().hex[:12]}"
    conv2_id = f"conv_{uuid.uuid4().hex[:12]}"
    conv3_id = f"conv_{uuid.uuid4().hex[:12]}"

    await db.chat_conversations.insert_many([
        {
            "conversation_id": conv1_id,
            "user_id": user["user_id"],
            "trust_id": trust1_id,
            "title": "Distribution rules for Emily's tuition",
            "messages": [
                {"role": "user", "content": "What are the distribution rules for my daughter Emily's college tuition?",
                 "timestamp": (now - timedelta(days=12)).isoformat()},
                {"role": "assistant",
                 "content": "Based on the Smith Family Trust Agreement, the distribution standard is Health, Education, Maintenance, and Support (HEMS). Emily's college tuition qualifies under the Education prong of HEMS. The trust instrument specifically authorizes distributions for tuition, fees, books, and reasonable living expenses while enrolled as a full-time student.\n\nKey details:\n• Distribution authority: Article IV, Section 4.1(a)\n• Beneficiary: Emily Smith (25% interest, CERT-001)\n• Prior distributions: $15,000 for Spring 2026 tuition\n• Solvency check required before approval\n\nYou can create a new distribution through the Money → Distributions page.",
                 "citation_note": "Trust instrument analysis: Article IV, Section 4.1(a) - HEMS distribution standard",
                 "unknown_note": "I cannot verify Emily's current enrollment status — please confirm with the university.",
                 "timestamp": (now - timedelta(days=12)).isoformat()},
                {"role": "user", "content": "Can I also pay for her off-campus housing?",
                 "timestamp": (now - timedelta(days=11)).isoformat()},
                {"role": "assistant",
                 "content": "Yes, reasonable housing expenses qualify under the Maintenance prong of HEMS. The trust document does not impose a specific dollar cap on individual distributions, but all distributions must be: (1) consistent with the beneficiary's standard of living, (2) approved by the trustee(s) via minutes, and (3) supported by a solvency check confirming sufficient trust corpus remains.\n\nRecommended next steps:\n1. Document the housing cost estimate\n2. Create a distribution entry in the Money tab\n3. Generate authorizing minutes from the distribution",
                 "citation_note": "Article IV, Section 4.1(b) - Maintenance and Support standard",
                 "timestamp": (now - timedelta(days=11)).isoformat()},
            ],
            "created_at": (now - timedelta(days=12)).isoformat(),
            "updated_at": (now - timedelta(days=11)).isoformat(),
            "is_demo": True
        },
        {
            "conversation_id": conv2_id,
            "user_id": user["user_id"],
            "trust_id": trust1_id,
            "title": "Trustee compensation review",
            "messages": [
                {"role": "user", "content": "How much compensation can I take as trustee?",
                 "timestamp": (now - timedelta(days=30)).isoformat()},
                {"role": "assistant",
                 "content": "Your trust agreement authorizes reasonable trustee compensation under Article V, Section 5.2. The current approved plan is $24,000 per trustee annually, payable quarterly ($6,000 per quarter).\n\nCurrent compensation:\n• John Smith: $24,000/year (approved)\n• Jane Smith: $24,000/year (approved)\n• Recent payments: Q1 2026 paid on " + (now - timedelta(days=5)).strftime("%B %d, %Y") + "\n\nWhen reviewing compensation, consider: trust size and complexity, time commitment, and comparison to professional fiduciary rates in your jurisdiction. Any changes should be documented via trustee compensation minutes.",
                 "citation_note": "Article V, Section 5.2 - Trustee compensation clause; Minutes dated " + (now - timedelta(days=365)).strftime("%B %d, %Y"),
                 "caveat": "This is informational only. Consult a licensed attorney for specific legal advice on fiduciary compensation.",
                 "timestamp": (now - timedelta(days=30)).isoformat()},
            ],
            "created_at": (now - timedelta(days=30)).isoformat(),
            "updated_at": (now - timedelta(days=30)).isoformat(),
            "is_demo": True
        },
        {
            "conversation_id": conv3_id,
            "user_id": user["user_id"],
            "trust_id": trust1_id,
            "title": "Beneficiary questions about trust assets",
            "messages": [
                {"role": "user", "content": "What assets are currently held in the trust?",
                 "timestamp": (now - timedelta(days=5)).isoformat()},
                {"role": "assistant",
                 "content": "The Smith Family Trust currently holds the following assets per Schedule A:\n\n1. **Primary Residence** - 123 Oak Street, Wilmington, DE ($650,000)\n2. **Beach Condo** - Unit 4B, Rehoboth Beach, DE ($425,000)\n3. **Schwab Brokerage** - Growth Portfolio ($1,250,000)\n4. **Bank Operating Account** - First National Bank ($85,000)\n5. **Smith Holdings LLC** - 100% membership interest ($500,000)\n6. **Fine Art Collection** - 12 paintings + 3 sculptures ($175,000)\n7. **Bitcoin** - 2.5 BTC in cold storage ($125,000)\n8. **2023 Mercedes S-Class** ($95,000)\n\n**Disposed assets:** 2019 BMW X5 sold for $38,500 (proceeds deposited to operating account).\n\nTotal estimated trust corpus: ~$3,255,000",
                 "citation_note": "Schedule A inventory — 8 active assets, 1 disposed",
                 "timestamp": (now - timedelta(days=5)).isoformat()},
                {"role": "user", "content": "Can I sell the beach condo and distribute the proceeds?",
                 "timestamp": (now - timedelta(days=4)).isoformat()},
                {"role": "assistant",
                 "content": "Yes, you have the authority to sell trust real property under the general administrative powers in your trust agreement. The process would be:\n\n1. **Obtain an appraisal** — document current fair market value\n2. **Draft and approve disposition minutes** — document the decision and rationale\n3. **Execute the sale** — proceeds deposited to trust operating account\n4. **Update Schedule A** — mark the condo as disposed with sale details\n5. **Distribute proceeds** — create a distribution entry with solvency check and authorizing minutes\n\nAll steps must be documented in the trust records for audit purposes. I can help you create disposition minutes or a distribution record when you're ready.",
                 "citation_note": "Trust instrument: General administrative powers; Article IV - Distribution authority",
                 "caveat": "Real property sales may have tax implications. Consult a CPA before executing.",
                 "timestamp": (now - timedelta(days=4)).isoformat()},
            ],
            "created_at": (now - timedelta(days=5)).isoformat(),
            "updated_at": (now - timedelta(days=4)).isoformat(),
            "is_demo": True
        },
    ])

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
            "Trust unit certificates and transfers",
            "Class beneficiary designations",
            "Governance tasks (upcoming, overdue, completed)",
            "Transaction records (Money module)",
            "Tax calendar entries",
            "Health score snapshots with historical trend",
            "Vault documents with AI document analysis",
            "Trust Assistant chat history"
        ]
    }


@router.delete("/data")
async def delete_demo_data(user: dict = Depends(require_write_access)):
    """
    Delete only demo data (records with is_demo: True).
    User-created data is preserved.
    """
    user_id = user["user_id"]
    
    # Track what was deleted
    deleted_counts = {}
    
    # Delete in order (children first, then parents)
    # Only delete records that have is_demo: True
    collections_to_clean = [
        ("chat_conversations", "chat_conversations"),
        ("trust_document_analysis", "trust_document_analysis"),
        ("vault_documents", "vault_documents"),
        ("class_beneficiaries", "class_beneficiaries"),
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
        ("transactions", "transactions"),
        ("tax_calendar", "tax_calendar"),
        ("health_score_snapshots", "health_score_snapshots"),
        ("trusts", "trusts"),
    ]
    
    for collection_name, display_name in collections_to_clean:
        collection = db[collection_name]
        # Only delete records marked as demo data
        result = await collection.delete_many({"user_id": user_id, "is_demo": True})
        if result.deleted_count > 0:
            deleted_counts[display_name] = result.deleted_count
    
    total_deleted = sum(deleted_counts.values())
    
    return {
        "message": f"Successfully deleted {total_deleted} demo records",
        "deleted_counts": deleted_counts,
        "notes": "Only demo data was removed. Your custom trusts and data remain intact."
    }


@router.get("/status")
async def get_demo_status(user: dict = Depends(get_current_user)):
    """
    Check if user has demo data and get counts of all records.
    Separates demo data from user-created data.
    """
    user_id = user["user_id"]
    
    # Count all records
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
        "transactions": await db.transactions.count_documents({"user_id": user_id}),
        "tax_calendar": await db.tax_calendar.count_documents({"user_id": user_id}),
        "class_beneficiaries": await db.class_beneficiaries.count_documents({"user_id": user_id}),
        "vault_documents": await db.vault_documents.count_documents({"user_id": user_id}),
        "health_score_snapshots": await db.health_score_snapshots.count_documents({"user_id": user_id}),
        "chat_conversations": await db.chat_conversations.count_documents({"user_id": user_id}),
        "trust_document_analysis": await db.trust_document_analysis.count_documents({"user_id": user_id}),
        "entity_relationships": await db.entity_relationships.count_documents({"user_id": user_id}),
        "trust_unit_settings": await db.trust_unit_settings.count_documents({"user_id": user_id}),
        "trust_unit_transfers": await db.trust_unit_transfers.count_documents({"user_id": user_id}),
    }
    
    # Count demo records only
    demo_counts = {
        "trusts": await db.trusts.count_documents({"user_id": user_id, "is_demo": True}),
        "entities": await db.entities.count_documents({"user_id": user_id, "is_demo": True}),
        "schedule_a_items": await db.schedule_a_items.count_documents({"user_id": user_id, "is_demo": True}),
        "minutes_records": await db.minutes_records.count_documents({"user_id": user_id, "is_demo": True}),
        "distribution_records": await db.distribution_records.count_documents({"user_id": user_id, "is_demo": True}),
        "benevolence_records": await db.benevolence_records.count_documents({"user_id": user_id, "is_demo": True}),
        "governance_tasks": await db.governance_tasks.count_documents({"user_id": user_id, "is_demo": True}),
        "compensation_plans": await db.compensation_plans.count_documents({"user_id": user_id, "is_demo": True}),
        "compensation_payments": await db.compensation_payments.count_documents({"user_id": user_id, "is_demo": True}),
        "trust_unit_certificates": await db.trust_unit_certificates.count_documents({"user_id": user_id, "is_demo": True}),
        "transactions": await db.transactions.count_documents({"user_id": user_id, "is_demo": True}),
        "tax_calendar": await db.tax_calendar.count_documents({"user_id": user_id, "is_demo": True}),
        "class_beneficiaries": await db.class_beneficiaries.count_documents({"user_id": user_id, "is_demo": True}),
        "vault_documents": await db.vault_documents.count_documents({"user_id": user_id, "is_demo": True}),
        "health_score_snapshots": await db.health_score_snapshots.count_documents({"user_id": user_id, "is_demo": True}),
        "chat_conversations": await db.chat_conversations.count_documents({"user_id": user_id, "is_demo": True}),
        "trust_document_analysis": await db.trust_document_analysis.count_documents({"user_id": user_id, "is_demo": True}),
        "entity_relationships": await db.entity_relationships.count_documents({"user_id": user_id, "is_demo": True}),
        "trust_unit_settings": await db.trust_unit_settings.count_documents({"user_id": user_id, "is_demo": True}),
        "trust_unit_transfers": await db.trust_unit_transfers.count_documents({"user_id": user_id, "is_demo": True}),
    }
    
    total = sum(counts.values())
    total_demo = sum(demo_counts.values())
    has_data = total > 0
    has_demo_data = total_demo > 0
    
    return {
        "has_data": has_data,
        "has_demo_data": has_demo_data,
        "total_records": total,
        "total_demo_records": total_demo,
        "counts": counts,
        "demo_counts": demo_counts,
        "can_seed": not has_demo_data,
        "can_delete_demo": has_demo_data
    }