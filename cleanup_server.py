# Script to remove duplicate enums/models from server.py

with open('/app/backend/server.py', 'r') as f:
    content = f.read()
    lines = content.split('\n')

# Find the section to remove (from ENUMS to HELPER FUNCTIONS)
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if '# ==================== ENUMS ====================' in line:
        start_idx = i
    elif start_idx is not None and '# ==================== HELPER FUNCTIONS ====================' in line:
        end_idx = i
        break

if start_idx is not None and end_idx is not None:
    print(f"Found section to remove: lines {start_idx+1} to {end_idx}")
    
    # Build new content
    # Keep everything before ENUMS section
    new_lines = lines[:start_idx]
    
    # Add imports from models.py
    imports_to_add = """
# Import models and enums from centralized models.py
from models import (
    # Enums
    TrustType, EntityType, RelationshipType, TaskType, MinutesType,
    PurposeClassification, HealthColor, PlanType, SubscriptionStatus,
    AssetCategory, MinutesTemplateType, AssetStatus, BenevolencePurpose,
    CertificateStatus,
    # Models
    UserCreate, UserLogin, UserResponse, ProfileUpdate,
    NotificationPreferences, NotificationPreferencesUpdate,
    UserPreferences, UserPreferencesUpdate,
    PasswordResetRequest, PasswordResetConfirm,
    TrustCreate, TrustUpdate, TrustResponse,
    EntityCreate, EntityResponse,
    EntityRelationshipCreate, EntityRelationshipResponse,
    GovernanceTaskCreate, GovernanceTaskResponse,
    TrustUnitsSettingsCreate, TrustUnitsSettingsUpdate, TrustUnitsSettingsResponse,
    TrustUnitCertificateCreate, TrustUnitCertificateUpdate, TrustUnitCertificateResponse,
    TrustUnitTransferCreate, TrustUnitTransferResponse, TrustUnitsSummaryResponse,
    MinutesRecordCreate, MinutesResponse, MinutesTemplateCreate, MinutesTemplateResponse,
    DistributionRecordCreate, DistributionRecordUpdate, DistributionRecordResponse,
    ScheduleAItemCreate, ScheduleAItemUpdate, ScheduleAItemResponse,
    BenevolenceRecordCreate, BenevolenceRecordUpdate, BenevolenceRecordResponse,
    CompensationPlanCreate, CompensationPlanResponse,
    CompensationPaymentCreate, CompensationPaymentResponse,
    SubscriptionResponse, CheckoutRequest, PortalRequest,
    HealthScoreResponse, HealthScoreCriterion,
    BeneficiaryDashboardResponse, BeneficiaryHolding
)

"""
    
    # Add the imports
    new_lines.append(imports_to_add)
    
    # Add everything from HELPER FUNCTIONS onwards
    new_lines.extend(lines[end_idx:])
    
    # Write the new content
    with open('/app/backend/server.py', 'w') as f:
        f.write('\n'.join(new_lines))
    
    print(f"Removed {end_idx - start_idx} lines")
    print("Added imports from models.py")
else:
    print(f"Could not find section boundaries. start={start_idx}, end={end_idx}")
