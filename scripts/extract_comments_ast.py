#!/usr/bin/env python3
import tokenize
import os
from pathlib import Path

def extract_comments_from_file(file_path):
    comments = []
    try:
        with open(file_path, 'rb') as f:
            tokens = tokenize.tokenize(f.readline)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    comment_text = token.string.strip()[1:].strip()
                    line_num = token.start[0]
                    for comment_type in ['BUG', 'FIXME', 'TODO', 'HACK']:
                        if comment_text.upper().startswith(comment_type + ':') or comment_type in comment_text.upper():
                            if comment_text.startswith(comment_type + ':'):
                                message = comment_text[len(comment_type)+1:].strip()
                            else:
                                message = comment_text
                            comments.append((comment_type, message, line_num, file_path))
                            break
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return comments

def collect_all_comments(root_dir):
    exclude_dirs = {'tests', '.git', 'reports', 'scripts', 'tasks'}
    all_comments = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                all_comments.extend(extract_comments_from_file(file_path))
    return all_comments

def generate_backlog(comments):
    priority_order = {'BUG': 0, 'FIXME': 1, 'TODO': 2, 'HACK': 3}
    sorted_comments = sorted(comments, key=lambda x: priority_order[x[0]])
    
    backlog = "# Priority Task Backlog\n\n"
    current_section = None
    section_titles = {
        'BUG': "## P0: Critical Bugs",
        'FIXME': "\n## P1: Defects to Fix",
        'TODO': "\n## P2: Feature & Improvement Tasks",
        'HACK': "\n## P3: Temporary Workarounds to Refactor"
    }
    
    for comment in sorted_comments:
        comment_type, message, line_num, file_path = comment
        if current_section != comment_type:
            current_section = comment_type
            backlog += section_titles[current_section] + '\n'
        backlog += f"- [{comment_type}] {Path(file_path).relative_to('.')}:{line_num} - {message}\n"
    
    return backlog

if __name__ == '__main__':
    root_dir = Path(__file__).parent.parent
    comments = collect_all_comments(root_dir)
    print(generate_backlog(comments))
