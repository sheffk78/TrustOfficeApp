# Script to remove subscription section from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find start line (# ==================== SUBSCRIPTION ENDPOINTS ====================)
start_line = None
end_line = None

for i, line in enumerate(lines):
    if '# ==================== SUBSCRIPTION ENDPOINTS ====================' in line:
        start_line = i
    elif start_line is not None and '# ==================== EMAIL ENDPOINTS ====================' in line:
        end_line = i
        break

if start_line and end_line:
    # Create new content
    new_lines = lines[:start_line]
    new_lines.append("# ==================== SUBSCRIPTION ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/subscriptions.py\n")
    new_lines.append("# Endpoints: GET /subscription, GET /subscription/state, GET /subscription/features,\n")
    new_lines.append("#            POST /subscription/create-checkout, GET /subscription/verify-payment,\n")
    new_lines.append("#            POST /subscription/create-portal, POST /subscription/cancel,\n")
    new_lines.append("#            POST /subscription/reactivate, POST /subscription/upgrade, POST /stripe/webhook\n")
    new_lines.append("\n")
    new_lines.extend(lines[end_line:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed lines {start_line+1} to {end_line} ({end_line - start_line} lines)")
else:
    print(f"Could not find section boundaries. start={start_line}, end={end_line}")
