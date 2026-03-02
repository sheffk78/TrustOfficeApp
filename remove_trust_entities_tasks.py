# Script to remove trusts, entities, and tasks sections from server.py

with open('/app/backend/server.py', 'r') as f:
    lines = f.readlines()

# Find section boundaries
trusts_start = None
tasks_end = None

for i, line in enumerate(lines):
    if '# ==================== TRUST ENDPOINTS ====================' in line:
        trusts_start = i
    elif trusts_start is not None and '# ==================== TRUST UNITS ENDPOINTS ====================' in line:
        tasks_end = i
        break

if trusts_start and tasks_end:
    # Create new content
    new_lines = lines[:trusts_start]
    new_lines.append("# ==================== TRUST ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/trusts.py\n")
    new_lines.append("# Endpoints: POST/GET/PUT/DELETE /trusts\n")
    new_lines.append("\n")
    new_lines.append("# ==================== ENTITY ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/entities.py\n")
    new_lines.append("# Endpoints: POST/GET/PATCH/DELETE /entities, POST/GET/DELETE /entity-relationships\n")
    new_lines.append("\n")
    new_lines.append("# ==================== GOVERNANCE TASK ENDPOINTS ====================\n")
    new_lines.append("# MIGRATED TO: /app/backend/routers/tasks.py\n")
    new_lines.append("# Endpoints: POST/GET /tasks, PATCH /tasks/{id}/complete, PATCH /tasks/{id}/uncomplete, DELETE /tasks/{id}\n")
    new_lines.append("\n")
    new_lines.extend(lines[tasks_end:])
    
    with open('/app/backend/server.py', 'w') as f:
        f.writelines(new_lines)
    
    print(f"Removed lines {trusts_start+1} to {tasks_end} ({tasks_end - trusts_start} lines)")
else:
    print(f"Could not find section boundaries. trusts_start={trusts_start}, tasks_end={tasks_end}")
