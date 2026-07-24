#!/usr/bin/env python3
import re
import os
import json

PAGES_DIR = '/tmp/TrustOfficeApp/frontend/src/pages'
EXCLUDE_DIRS = {'_archived', '_old', '__pycache__'}

# Known handler patterns that act as save/submit
SAVE_HANDLERS = re.compile(
    r'(handle(Save|Update|Submit|Edit|Add|Create|Upload|Change|Toggle|Delete|Remove|Cancel))|'
    r'(onClick\{handle|type=["\']submit["\'])',
    re.IGNORECASE
)

SAVE_BUTTON_TEXT = re.compile(
    r'(Save|Submit|Update|Create|Add|Upload|Generate|Send|Post|Edit|Apply|Confirm)',
    re.IGNORECASE
)

INPUT_FIELD = re.compile(r'<(Input|Select|Textarea|Switch|Checkbox|RadioGroup|DatePicker)')

def get_file_lines(path):
    with open(path, 'r', errors='replace') as f:
        return f.readlines()

def find_state_vars(lines):
    """Find useState declarations and track if they're used in UI."""
    state_vars = {}  # var_name -> dict with declaration info
    for i, line in enumerate(lines):
        m = re.search(r'\[(\w+),', line)
        if m and 'useState' in line:
            var_name = m.group(1)
            state_vars[var_name] = {
                'name': var_name,
                'line': i + 1,
                'used_in_ui': False,
                'is_loading_or_saving': 'loading' in var_name.lower() or 'saving' in var_name.lower(),
            }
    return state_vars

def check_state_ui_correlation(lines, state_vars):
    """Check if state variables are referenced in UI elements."""
    orphaned = []
    for var_name, info in state_vars.items():
        if info['is_loading_or_saving']:
            continue  # loading/saving states are typically fine
        # Check if the state variable is used somewhere beyond its declaration
        used = False
        for i, line in enumerate(lines):
            if i + 1 == info['line']:
                continue  # skip declaration line
            # Check for value= or checked= or selected= or defaultChecked= or placeholder=
            if re.search(r'(value|checked|selected|defaultChecked|placeholder|onChange|content)={' + re.escape(var_name) + r'\b', line):
                used = True
                break
            # Check for setVarName calls
            if f'set{var_name[0].upper()}{var_name[1:]}' in line:
                used = True
                break
            # Check in conditional rendering / display
            if re.search(r'{' + re.escape(var_name) + r'\s', line):
                used = True
                break
        if not used:
            orphaned.append((var_name, info['line']))
    return orphaned

def audit_forms_in_file(filepath, filename):
    lines = get_file_lines(filepath)
    results = []
    
    # Track field groups (forms) and their proximity to save buttons
    field_groups = []  # list of {line: int, fields: list}
    current_fields = []
    
    for i, line in enumerate(lines):
        # Track input fields
        if INPUT_FIELD.search(line):
            current_fields.append((i + 1, line.strip()))
        else:
            # When we see a non-field line after collecting fields, close the group
            if current_fields:
                # Check if next lines contain save button
                save_found = False
                save_at = None
                for j in range(i, min(i + 51, len(lines))):
                    next_line = lines[j]
                    if '<Button' in next_line or '<button' in next_line:
                        if SAVE_BUTTON_TEXT.search(next_line) or SAVE_HANDLERS.search(next_line):
                            save_found = True
                            save_at = j + 1
                            break
                    elif INPUT_FIELD.search(next_line):
                        # Another field starts, this group continues
                        break
                
                field_groups.append({
                    'start': current_fields[0][0],
                    'end': current_fields[-1][0],
                    'fields': list(current_fields),
                    'save_found': save_found,
                    'save_at_line': save_at
                })
                current_fields = []
    
    # Also handle trailing fields at end of file
    if current_fields:
        field_groups.append({
            'start': current_fields[0][0],
            'end': current_fields[-1][0],
            'fields': list(current_fields),
            'save_found': False,
            'save_at_line': None
        })
    
    # Merge adjacent field groups that share a save button
    merged_groups = []
    for g in field_groups:
        if merged_groups and g['save_found'] == merged_groups[-1]['save_found'] and \
           abs(g['start'] - merged_groups[-1]['end']) < 5:
            merged_groups[-1]['fields'].extend(g['fields'])
            merged_groups[-1]['end'] = g['end']
            if g['save_found']:
                merged_groups[-1]['save_at_line'] = g['save_at_line']
        else:
            merged_groups.append(dict(g))
    
    # Find all save/submit buttons that aren't near any fields (orphan buttons)
    all_save_buttons = []
    for i, line in enumerate(lines):
        if '<Button' in line or '<button' in line:
            if SAVE_BUTTON_TEXT.search(line) or SAVE_HANDLERS.search(line):
                all_save_buttons.append(i + 1)
    
    # Flag issues with entire forms (field groups without save buttons)
    for group in merged_groups:
        if not group['save_found']:
            results.append({
                'file': filepath,
                'filename': filename,
                'kind': 'missing_save_button',
                'start_line': group['start'],
                'end_line': group['end'],
                'field_count': len(group['fields']),
                'fields': group['fields'],
                'message': f'Form with {len(group["fields"])} field(s) missing save/submit button within 50 lines'
            })
    
    return results, merged_groups

def main():
    all_issues = []
    all_field_groups = {}
    
    for filename in sorted(os.listdir(PAGES_DIR)):
        if filename in EXCLUDE_DIRS or not filename.endswith('.js'):
            continue
            
        filepath = os.path.join(PAGES_DIR, filename)
        if os.path.isdir(filepath):
            continue
        
        lines = get_file_lines(filepath)
        
        # Find state variables
        state_vars = find_state_vars(lines)
        
        # Find form issues
        form_results, field_groups = audit_forms_in_file(filepath, filename)
        all_issues.extend(form_results)
        all_field_groups[filename] = field_groups
        
        # Find orphaned state vars
        orphaned = check_state_ui_correlation(lines, state_vars)
        for var_name, line in orphaned:
            all_issues.append({
                'file': filepath,
                'filename': filename,
                'kind': 'orphaned_state',
                'start_line': line,
                'end_line': line,
                'message': f'Orphaned state variable "{var_name}" at line {line} - no corresponding UI found'
            })
    
    # Print report
    print('=' * 80)
    print('                    TRUSTOFFICE FORM & STATE AUDIT REPORT')
    print('=' * 80)
    
    # Group by file
    files_with_issues = {}
    for issue in all_issues:
        fn = issue['filename']
        if fn not in files_with_issues:
            files_with_issues[fn] = []
        files_with_issues[fn].append(issue)
    
    total_missing = sum(1 for i in all_issues if i['kind'] == 'missing_save_button')
    total_orphaned = sum(1 for i in all_issues if i['kind'] == 'orphaned_state')
    
    print(f'\nTotal files checked: {len([f for f in os.listdir(PAGES_DIR) if f.endswith(".js") and f not in EXCLUDE_DIRS])}')
    print(f'Files with issues: {len(files_with_issues)}')
    print(f'Forms missing save buttons: {total_missing}')
    print(f'Orphaned state variables: {total_orphaned}')
    print()
    
    for filename in sorted(files_with_issues.keys()):
        issues = files_with_issues[filename]
        missing = [i for i in issues if i['kind'] == 'missing_save_button']
        orphaned = [i for i in issues if i['kind'] == 'orphaned_state']
        
        print(f'\n{"â" * 76}')
        print(f'  FILE: {filename}')
        print(f'{"â" * 76}')
        
        if missing:
            print(f'\n  [!!] FORMS MISSING SAVE BUTTONS ({len(missing)}):')
            for m in missing:
                print(f'\n       ââ Lines {m["start_line"]}-{m["end_line"]} ({m["field_count"]} fields)')
                for f_num, (ln, field_line) in enumerate(m['fields'], 1):
                    field_line_clean = field_line.strip()
                    if len(field_line_clean) > 100:
                        field_line_clean = field_line_clean[:97] + '...'
                    print(f'          Field {f_num} @ line {ln}: {field_line_clean}')
        
        if orphaned:
            print(f'\n  [!] ORPHANED STATE VARIABLES ({len(orphaned)}):')
            for o in orphaned:
                print(f'       ââ Line {o["start_line"]}: "{o["message"].split(chr(34))[1] if chr(34) in o["message"] else o["message"]}"')
        
        # Only show OK files
        if not missing and not orphaned:
            print(f'\n  [OK] No issues found.')
    
    print(f'\n{"=" * 80}')
    print(f'SUMMARY: {total_missing} forms without save buttons, {total_orphaned} orphaned state variables')
    print(f'{"=" * 80}')
    
    # Summary table
    print(f'\n{"File":<40} {"Forms OK":<10} {"Missing Btn":<12} {"Orphaned":<10}')
    print(f'{"â"*40} {"â"*10} {"â"*12} {"â"*10}')
    for filename in sorted(os.listdir(PAGES_DIR)):
        if filename in EXCLUDE_DIRS or not filename.endswith('.js'):
            continue
        filepath = os.path.join(PAGES_DIR, filename)
        if os.path.isdir(filepath):
            continue
        missing_count = sum(1 for i in all_issues if i['filename'] == filename and i['kind'] == 'missing_save_button')
        orphaned_count = sum(1 for i in all_issues if i['filename'] == filename and i['kind'] == 'orphaned_state')
        lines_in_file = len(get_file_lines(filepath))
        fg_count = len([g for fn2, groups in [all_field_groups.get(filename, [])] for g in [groups] if isinstance(g, dict)])
        ok_forms = fg_count - missing_count
        print(f'{filename:<40} {ok_forms:<10} {missing_count:<12} {orphaned_count:<10}')
    
    # Print machine-readable JSON for verification
    print(f'\n{"=" * 80}')
    print('MACHINE-READABLE RESULTS (issues.json):')
    print(f'{"=" * 80}')
    output = {
        'total_files_checked': len([f for f in os.listdir(PAGES_DIR) if f.endswith('.js') and f not in EXCLUDE_DIRS]),
        'total_missing_save_buttons': total_missing,
        'total_orphaned_state_vars': total_orphaned,
        'issues': all_issues
    }
    print(json.dumps(output, indent=2, default=str))

if __name__ == '__main__':
    main()