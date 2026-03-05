#!/usr/bin/env python3
import sys
from pathlib import Path

def recover_file_from_diff(diff_content: str, target_path: str):
    original_lines = []
    in_original = False
    for line in diff_content.splitlines():
        if line.startswith('--- a/'):
            in_original = True
            continue
        if line.startswith('+++ b/') or line.startswith('@@'):
            continue
        if in_original:
            if line.startswith('-'):
                original_lines.append(line[1:])
            elif line.startswith(' '):
                original_lines.append(line[1:])
            elif line.startswith('\ No newline at end of file'):
                continue
            else:
                break
    
    Path(target_path).write_text('\n'.join(original_lines) + '\n', encoding='utf-8')
    print(f"Successfully recovered {target_path} with {len(original_lines)} lines")

if __name__ == '__main__':
    diff_content = sys.stdin.read()
    recover_file_from_diff(diff_content, 'src/llm247/autonomous.py')
