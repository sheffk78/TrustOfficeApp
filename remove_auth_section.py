# Script to remove auth section from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find section boundaries
start_line = None
end_line = None

for i, line in enumerate(lines):
    if '# ==================== AUTH ENDPOINTS ====================' in line:
        start_line = i
    elif start_line is not None and '# ==================== NOTIFICATION PREFERENCES ====================' in line:
        end_line = i
        break

if start_line and end_line:
    # Create new content
    new_lines = lines[:start_line]
    new_lines.append("# ==================== AUTH ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/auth.py\n")
    new_lines.append("# Endpoints: POST /auth/register, POST /auth/login, POST /auth/forgot-password,\n")
    new_lines.append("#            POST /auth/reset-password, GET /auth/verify-reset-token, POST /auth/session,\n")
    new_lines.append("#            GET /auth/me, PUT /auth/profile, POST /auth/logout\n")
    new_lines.append("\n")
    new_lines.extend(lines[end_line:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed lines {start_line+1} to {end_line} ({end_line - start_line} lines)")
else:
    print(f"Could not find section boundaries. start={start_line}, end={end_line}")
