# Script to remove benevolence section from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find start line (# ==================== BENEVOLENCE ENDPOINTS ====================)
start_line = None
end_line = None

for i, line in enumerate(lines):
    if '# ==================== BENEVOLENCE ENDPOINTS ====================' in line:
        start_line = i
    elif start_line is not None and '# ==================== DISTRIBUTION ENDPOINTS ====================' in line:
        end_line = i
        break

if start_line and end_line:
    # Create new content
    new_lines = lines[:start_line]
    new_lines.append("# ==================== BENEVOLENCE ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/benevolence.py\n")
    new_lines.append("# Endpoints: POST/GET/PUT/DELETE /benevolence, GET /benevolence/summary/{trust_id},\n")
    new_lines.append("#            GET /benevolence/export/{trust_id}/pdf\n")
    new_lines.append("\n")
    new_lines.extend(lines[end_line:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed lines {start_line+1} to {end_line} ({end_line - start_line} lines)")
else:
    print(f"Could not find section boundaries. start={start_line}, end={end_line}")
