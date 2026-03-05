#!/usr/bin/env python3
import os
import re

def is_comment_outside_string(line):
    """Determine if the line's # comment is outside string literals."""
    in_single_quote = False
    in_double_quote = False
    escaped = False
    for idx, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
        elif char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        # Check if we've reached a comment outside any quotes
        if char == '#' and not in_single_quote and not in_double_quote:
            return idx, True
    return -1, False

def extract_priority_comments(file_path):
    """Extract valid TODO/FIXME/BUG/HACK comments from Python file."""
    comments = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                comment_pos, is_valid = is_comment_outside_string(line)
                if is_valid:
                    comment_part = line[comment_pos:].strip()
                    match = re.match(r'#\s*(TODO|FIXME|BUG|HACK):?\s*(.+)', comment_part, re.IGNORECASE)
                    if match:
                        comment_type = match.group(1).upper()
                        comment_text = match.group(2).strip()
                        comments.append(f"{file_path}:{line_num}: [{comment_type}] {comment_text}")
    except Exception as e:
        pass
    return comments

def main():
    # Scan src directory excluding tests
    for root, dirs, files in os.walk('src'):
        if 'tests' in dirs:
            dirs.remove('tests')
        for file in files:
            if file.endswith('.py'):
                full_path = os.path.join(root, file)
                for comment in extract_priority_comments(full_path):
                    print(comment)

if __name__ == '__main__':
    main()
