#!/usr/bin/env python3
"""Build committed artifacts and publish append-only releases using repository GH_TOKEN."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile


def command(*args, data=None):
    return subprocess.run(args, input=data, capture_output=True, check=True).stdout


def api(endpoint, method='GET', payload=None, missing=False):
    args = ['gh', 'api', endpoint, '--method', method]
    if payload is not None:
        args += ['--input', '-']
    try:
        raw = command(*args, data=json.dumps(payload).encode() if payload is not None else None)
    except subprocess.CalledProcessError as error:
        if missing and b'(HTTP 404)' in error.stderr:
            return None
        raise
    return json.loads(raw) if raw else None


def checked_sha(value):
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise ValueError('expected full lowercase commit SHA')
    return value


def prepare(sha, output):
    checked_sha(sha)
    if command('git', 'rev-parse', 'HEAD').decode().strip() != sha:
        raise ValueError('artifact commit must equal checked-out HEAD')
    config = json.loads(command('git', 'show', f'{sha}:.github/release.json'))
    name = config['name']
    if not re.fullmatch(r'[a-z0-9-]+', name):
        raise ValueError('invalid package name')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('artifact directory must be empty')
    source = command('git', 'archive', '--format=tar', f'--prefix={name}-{sha}/', sha)
    buffer = io.BytesIO()
    # Stored DEFLATE avoids dependence on zlib compression-version output.
    with gzip.GzipFile(filename='', fileobj=buffer, mode='wb', compresslevel=0, mtime=0) as archive:
        archive.write(source)
    (output / f'{name}-{sha}.tar.gz').write_bytes(buffer.getvalue())
    for extension in config.get('extensions', []):
        prefix = extension['directory'].rstrip('/')
        prefix = prefix + '/' if prefix and prefix != '.' else ''
        files = extension['files']
        if not {'metadata.json', 'extension.js'} <= set(files):
            raise ValueError('extension requires metadata.json and extension.js')
        contents = {}
        for file in files:
            if Path(file).is_absolute() or '..' in Path(file).parts:
                raise ValueError('invalid extension file')
            contents[file] = command('git', 'show', f'{sha}:{prefix}{file}')
        uuid = json.loads(contents['metadata.json'])['uuid']
        if not re.fullmatch(r'[a-zA-Z0-9@._-]+', uuid):
            raise ValueError('invalid extension UUID')
        if 'buildInfo.js' in contents:
            contents['buildInfo.js'] = f"// Release artifact from this exact source commit.\nexport const BUILD_REVISION = '{sha}';\n".encode()
        with zipfile.ZipFile(output / f'{uuid}.shell-extension.zip', 'w', compression=zipfile.ZIP_STORED) as archive:
            for file, content in sorted(contents.items()):
                info = zipfile.ZipInfo(file, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
    sums = ''.join(f'{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n'
                   for file in sorted(output.iterdir()))
    (output / 'SHA256SUMS').write_text(sums)


def tag_commit(repo, tag):
    ref = api(f'repos/{repo}/git/ref/tags/{tag}', missing=True)
    if ref is None:
        return None
    obj = ref['object']
    for _ in range(8):
        if obj['type'] == 'commit':
            return obj['sha']
        if obj['type'] != 'tag':
            break
        obj = api(f'repos/{repo}/git/tags/{obj["sha"]}')['object']
    raise ValueError('release tag does not resolve to a commit')


def verify_assets(repo, release, files):
    existing = {asset['name']: asset for asset in release['assets']}
    if len(existing) != len(release['assets']) or set(existing) - set(files):
        raise ValueError('release contains unexpected or duplicate assets')
    for name, asset in existing.items():
        expected = 'sha256:' + hashlib.sha256(files[name].read_bytes()).hexdigest()
        digest = asset.get('digest')
        if not digest:
            raw = command('gh', 'api', f'repos/{repo}/releases/assets/{asset["id"]}',
                          '-H', 'Accept: application/octet-stream')
            digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
        if asset.get('state') != 'uploaded' or digest != expected:
            raise ValueError(f'existing asset differs: {name}; refusing replacement')
    return sorted(set(files) - set(existing))


def publish(repo, sha, output, tag=None):
    checked_sha(sha)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo):
        raise ValueError('invalid GitHub repository')
    tag = tag or f'build-{sha}'
    if tag != f'build-{sha}' and not re.fullmatch(r'v[0-9][A-Za-z0-9._-]*', tag):
        raise ValueError('expected commit-addressed or semantic version tag')
    files = {file.name: file for file in Path(output).iterdir() if file.is_file()}
    if 'SHA256SUMS' not in files or len(files) < 2:
        raise ValueError('release artifacts are missing')
    target = tag_commit(repo, tag)
    if target is None:
        if not tag.startswith('build-'):
            raise ValueError('semantic release requires an existing tag')
        api(f'repos/{repo}/git/refs', 'POST', {'ref': f'refs/tags/{tag}', 'sha': sha})
    elif target != sha:
        raise ValueError('existing release tag targets another commit; refusing to move it')
    endpoint = f'repos/{repo}/releases/tags/{tag}'
    release = api(endpoint, missing=True)
    if release is None:
        release = api(f'repos/{repo}/releases', 'POST', {
            'tag_name': tag, 'target_commitish': sha, 'name': f'{repo.split("/")[1]} {tag}',
            'body': f'Checked source commit: `{sha}`.\n\nArtifacts and SHA256SUMS are append-only; reruns verify existing bytes.',
            'draft': True, 'prerelease': False, 'make_latest': 'false' if tag.startswith('build-') else 'true'})
    missing = verify_assets(repo, release, files)
    if missing and not release['draft']:
        raise ValueError('published release lacks expected assets; refusing to modify it')
    for name in missing:
        # No --clobber: concurrent uploads fail safely and can be retried.
        command('gh', 'release', 'upload', tag, str(files[name]), '--repo', repo)
    release = api(f'repos/{repo}/releases/{release["id"]}')
    if verify_assets(repo, release, files) or tag_commit(repo, tag) != sha:
        raise ValueError('release changed during preparation')
    if release['draft']:
        release = api(f'repos/{repo}/releases/{release["id"]}', 'PATCH', {'draft': False, 'make_latest': 'false' if tag.startswith('build-') else 'true'})
    result = {'tag': tag, 'commit': sha, 'url': release['html_url'],
              'append_only_verified': True, 'github_immutable': bool(release.get('immutable', False))}
    print(json.dumps(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'publish'])
    parser.add_argument('--sha', default=os.environ.get('GITHUB_SHA'))
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--output', default='release-dist')
    parser.add_argument('--tag')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.sha, args.output)
    else:
        publish(args.repo, args.sha, args.output, args.tag)


if __name__ == '__main__':
    main()
