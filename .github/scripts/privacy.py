#!/usr/bin/env python3
"""Reject private publication inputs without printing matched contents."""
import argparse
import json
from pathlib import PurePosixPath
import re
import sqlite3
import subprocess
import sys


PRIVATE_DIRECTORIES = {'.codex', '.claude', '.agents', '.cursor', 'logs', 'runtime',
                       'transcripts', 'checkpoints', 'snapshots', '.secrets',
                       'local', 'private', 'state', 'backups'}
PRIVATE_NAMES = {'claude.md', 'gemini.md', 'codex.md', 'credentials', 'credentials.json',
                 'credentials.toml', 'credentials.yaml', 'credentials.yml', 'secrets.json',
                 'secrets.toml', 'secrets.yaml', 'secrets.yml', 'id_rsa', 'id_ed25519',
                 'id_ecdsa', 'id_dsa', '.netrc', '.npmrc', '.pypirc'}
PRIVATE_SUFFIXES = {'.log', '.jsonl', '.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx'}
CREDENTIALS = [
    re.compile(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),
    re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'\bsk-(?:proj-|ant-api\d{2}-)[A-Za-z0-9_-]{32,}\b'),
    re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
]
AI_NAMES = r'(?:codex|claude|chatgpt|copilot|gemini|openai|anthropic|cursor|aider|devin|\bAI\b)'
ATTRIBUTION = re.compile(
    r'(?im)^\s*(?:co-authored-by|signed-off-by):[^\n]*' + AI_NAMES
    + r'|(?:generated|written|authored|co-authored|assisted|created)\s+(?:by|with|using)\s+[^\n]{0,40}' + AI_NAMES
    + r'|\bAI[- ](?:generated|authored|assisted)\b')


def git(*args):
    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)


def single_schema_statement(sql):
    if not re.match(r'^\s*CREATE\s+', sql, re.IGNORECASE):
        return False
    statement = ''
    count = 0
    for character in sql.rstrip().rstrip(';') + ';':
        statement += character
        if character == ';' and sqlite3.complete_statement(statement):
            count += 1
            statement = ''
    return count == 1 and not statement.strip()


def schema_only(data):
    try:
        entries = json.loads(data)
        return isinstance(entries, list) and all(
            isinstance(entry, list) and len(entry) == 4 and all(isinstance(value, str) for value in entry)
            and entry[0] in {'table', 'index', 'view', 'trigger'}
            and single_schema_statement(entry[3])
            for entry in entries)
    except (ValueError, UnicodeDecodeError):
        return False


def path_problem(path, data):
    parts = PurePosixPath(path.lower()).parts
    name = parts[-1]
    if (any(part in PRIVATE_DIRECTORIES for part in parts)
            or re.fullmatch(r'agents[^/]*\.md', name) or name in PRIVATE_NAMES
            or (len(parts) > 1 and parts[0] == '.github' and name.startswith('copilot-instructions'))):
        return 'private instruction, runtime, or credential path'
    if name == '.env' or name.startswith('.env.') or PurePosixPath(name).suffix in PRIVATE_SUFFIXES:
        return 'private data or key file'
    if name.endswith('.sqlite.schema.json'):
        if not (len(parts) == 3 and parts[:2] == ('tests', 'fixtures') and schema_only(data)):
            return 'database fixture is not schema-only'
    return None


def scan(*, index=False, history=False):
    if index:
        records = git('ls-files', '--stage', '-z').split(b'\0')
    else:
        records = git('ls-tree', '-r', '-z', 'HEAD').split(b'\0')
    findings = []
    for record in records:
        if not record:
            continue
        metadata, raw_path = record.split(b'\t', 1)
        fields = metadata.split()
        if index:
            mode, oid, stage = fields
            if stage != b'0':
                findings.append(('unmerged index entry', raw_path.decode(errors='replace')))
                continue
        else:
            mode, kind, oid = fields
            if kind != b'blob':
                findings.append(('uninspected submodule', raw_path.decode(errors='replace')))
                continue
        path = raw_path.decode(errors='replace')
        data = git('cat-file', 'blob', oid.decode())
        problem = path_problem(path, data)
        if problem:
            findings.append((problem, path))
        if any(pattern.search(data) for pattern in CREDENTIALS):
            findings.append(('credential/private-key signature', path))
        if data.startswith(b'SQLite format 3\0'):
            findings.append(('database content', path))
    try:
        git('rev-parse', '--verify', 'HEAD')
    except subprocess.CalledProcessError:
        if index and not history:
            return findings  # Initial candidate index has no commit message yet.
        raise
    commits = git('rev-list', *(['HEAD'] if history else ['--max-count=1', 'HEAD'])).decode().splitlines()
    for commit in commits:
        message = git('show', '-s', '--format=%B', commit).decode(errors='replace')
        if ATTRIBUTION.search(message):
            findings.append(('AI commit attribution', commit))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', action='store_true', help='inspect staged files instead of HEAD')
    parser.add_argument('--history', action='store_true', help='check attribution in all reachable HEAD history')
    args = parser.parse_args()
    try:
        findings = scan(index=args.index, history=args.history)
    except subprocess.CalledProcessError:
        print('privacy gate: cannot inspect Git state; require a committed HEAD or use --index before the first commit', file=sys.stderr)
        return 1
    for reason, location in findings:
        print(f'privacy gate: {reason}: {json.dumps(location)}', file=sys.stderr)
    if findings:
        print('privacy gate: refused publication; matched contents are never printed', file=sys.stderr)
        return 1
    print('privacy gate: tracked paths, credential signatures, and commit attribution passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
