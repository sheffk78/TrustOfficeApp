# Script to remove duplicate helper functions from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find section boundaries
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if '# ==================== HELPER FUNCTIONS ====================' in line:
        start_idx = i
    elif start_idx is not None and '# ==================== AUTH ENDPOINTS ====================' in line:
        end_idx = i
        break

if start_idx is not None and end_idx is not None:
    print(f"Found section to remove: lines {start_idx+1} to {end_idx}")
    
    # Build new content
    new_lines = lines[:start_idx]
    
    # Add a note about where the functions are
    new_lines.append("# ==================== HELPER FUNCTIONS ====================\n")
    new_lines.append("# All helper functions have been moved to dependencies.py:\n")
    new_lines.append("# - hash_password, verify_password, create_jwt_token\n")
    new_lines.append("# - get_current_user, should_show_watermark, check_subscription_active\n")
    new_lines.append("# - get_task_status, get_quarter_start, get_year_start\n")
    new_lines.append("# - calculate_health_score, auto_update_onboarding, create_initial_governance_tasks\n")
    new_lines.append("\n")
    
    # Keep everything from AUTH ENDPOINTS onwards
    new_lines.extend(lines[end_idx:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed {end_idx - start_idx} lines")
else:
    print(f"Could not find section boundaries. start={start_idx}, end={end_idx}")
