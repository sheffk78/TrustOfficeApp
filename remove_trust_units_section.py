# Script to remove trust units section from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find start line (# ==================== TRUST UNITS ENDPOINTS ====================)
start_line = None
end_line = None

for i, line in enumerate(lines):
    if '# ==================== TRUST UNITS ENDPOINTS ====================' in line:
        start_line = i
    elif start_line is not None and '# ==================== GOVERNANCE TASK ENDPOINTS ====================' in line:
        end_line = i
        break

if start_line and end_line:
    # Create new content
    new_lines = lines[:start_line]
    new_lines.append("# ==================== TRUST UNITS ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/trust_units.py\n")
    new_lines.append("# Endpoints: GET /trust-units/summary, PATCH /trust-units/settings,\n")
    new_lines.append("#            POST/PATCH/GET /trust-units/certificates, GET /trust-units/certificates/{id}/pdf,\n")
    new_lines.append("#            POST/GET /trust-units/transfers, POST /trust-units/create-from-minutes/{id},\n")
    new_lines.append("#            POST /trust-units/bootstrap-from-minutes/{id}\n")
    new_lines.append("\n")
    new_lines.extend(lines[end_line:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed lines {start_line+1} to {end_line} ({end_line - start_line} lines)")
else:
    print(f"Could not find section boundaries. start={start_line}, end={end_line}")
