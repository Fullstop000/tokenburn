#!/usr/bin/env python3
import sys
from pathlib import Path

def recover_from_diff(diff_content: str, target_file: str):
    original_lines = []
    for line in diff_content.splitlines():
        # Skip diff header lines
        if line.startswith('diff --git') or line.startswith('index') or line.startswith('---') or line.startswith('+++'):
            continue
        # Extract original lines marked as deleted in diff
        if line.startswith('-') and not line.startswith('---'):
            original_line = line[1:].rstrip('\n')
            original_lines.append(original_line)
    # Write reconstructed content to target file
    Path(target_file).write_text('\n'.join(original_lines) + '\n')

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <diff_file> <target_file>")
        sys.exit(1)
    diff_file = sys.argv[1]
    target_file = sys.argv[2]
    diff_content = Path(diff_file).read_text()
    recover_from_diff(diff_content, target_file)