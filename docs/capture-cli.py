#!/usr/bin/env python3
"""Capture real CLI output with an isolated headless browser; no live UI changes."""
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, timeout=15, **kwargs).strip()


def render(title, subtitle, content, destination):
    chrome = shutil.which('google-chrome') or shutil.which('chromium')
    if not chrome:
        raise SystemExit('Install Chrome or Chromium to render the documentation capture.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='documentation-browser-') as temporary:
        root = Path(temporary)
        page = root / 'capture.html'
        height = max(440, 220 + 24 * len(content.splitlines()))
        page.write_text('<!doctype html><meta charset="utf-8"><style>'
            'body{margin:0;background:#0c1420;color:#e2eaf2;font-family:monospace;padding:40px}'
            'h1{font:600 30px sans-serif;color:#69e0cf;margin:0 0 12px}'
            'p{font:16px sans-serif;color:#a8b6ca;margin-bottom:28px}'
            'pre{font:17px/24px monospace;white-space:pre-wrap;overflow-wrap:anywhere;'
            'padding:24px;background:#132234;border:1px solid #294157;border-radius:12px}'
            '</style><h1>' + html.escape(title) + '</h1><p>' + html.escape(subtitle)
            + '</p><pre>' + html.escape(content) + '</pre>')
        subprocess.run([chrome, '--headless', '--disable-gpu', '--disable-background-networking',
            '--no-first-run', '--no-default-browser-check', '--hide-scrollbars',
            '--user-data-dir=' + str(root / 'profile'), '--screenshot=' + str(destination),
            '--window-size=1200,' + str(height), '--timeout=10000', page.as_uri()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    print(destination)


if __name__ == '__main__':
    import argparse
    import ast
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-json', type=Path, help='Read captured GetState JSON instead of querying this session')
    args = parser.parse_args()
    command = ['gdbus', 'call', '--session', '--dest', 'org.gnome.Shell',
        '--object-path', '/org/sagecat/HideSuspend', '--method', 'org.sagecat.HideSuspend.GetState']
    data = json.loads(args.from_json.read_text()) if args.from_json else json.loads(ast.literal_eval(run(command))[0])
    # Exclude input layouts, actor names, past recovery details and any unknown field.
    data = {key: data[key] for key in ('version', 'enabled', 'modalCount', 'isLocked', 'recoveryCounts', 'build') if key in data}
    if 'build' in data:
        data['build'] = {key: data['build'][key] for key in ('uuid', 'version', 'revision', 'sourceIdentityKnown') if key in data['build']}
    render('Hide Suspend · extension health',
        'Selected read-only GetState fields · GNOME Shell 46',
        '$ gdbus call ... --method org.sagecat.HideSuspend.GetState\n' + json.dumps(data, indent=2),
        ROOT / 'docs/screenshots/diagnostics.png')
