"""Offline regressions: no GitHub calls or user repository mutations."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('publisher', Path(__file__).with_name('release.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
SHA = 'a' * 40


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.files = {'source.tar.gz': b'committed source', 'SHA256SUMS': b'checksums'}
        for name, data in self.files.items():
            (self.root / name).write_bytes(data)
        self.target = None
        self.release = None
        self.writes = []

    def api(self, endpoint, method='GET', payload=None, missing=False):
        if method != 'GET':
            self.writes.append((endpoint, method, payload))
        if '/git/ref/tags/' in endpoint:
            return {'object': {'type': 'commit', 'sha': self.target}} if self.target else None
        if endpoint.endswith('/git/refs'):
            self.target = payload['sha']
            return {}
        if method == 'POST':
            self.release = dict(payload, id=7, assets=[], html_url='https://example.invalid/release', immutable=False)
        if method == 'PATCH':
            self.release.update(payload)
        return copy.deepcopy(self.release)

    def command(self, *args, **kwargs):
        self.assertEqual(args[:3], ('gh', 'release', 'upload'))
        self.assertNotIn('--clobber', args)
        path = Path(args[4])
        self.writes.append(('upload', path.name))
        self.release['assets'].append({'name': path.name, 'id': len(self.release['assets']),
                                      'state': 'uploaded', 'digest': 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()})
        return b''

    def publish(self, **kwargs):
        with patch.object(publisher, 'api', side_effect=self.api), patch.object(publisher, 'command', side_effect=self.command), contextlib.redirect_stdout(io.StringIO()):
            return publisher.publish('example/tool', SHA, self.root, **kwargs)

    def test_rerun_is_read_only_and_reports_server_immutability_honestly(self):
        result = self.publish()
        self.assertFalse(result['github_immutable'])
        self.assertFalse(self.release['draft'])
        self.assertEqual(self.target, SHA)
        self.writes.clear()
        self.assertEqual(self.publish(), result)
        self.assertEqual(self.writes, [])

    def test_wrong_tag_fails_before_any_write(self):
        self.target = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'another commit'):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_changed_asset_fails_without_replacement(self):
        self.publish()
        self.writes.clear()
        (self.root / 'source.tar.gz').write_bytes(b'different')
        with self.assertRaisesRegex(ValueError, 'refusing replacement'):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_partial_draft_recovers_only_missing_assets(self):
        self.publish()
        self.release['draft'] = True
        self.release['assets'] = self.release['assets'][:1]
        self.writes.clear()
        self.publish()
        self.assertEqual(sum(item[0] == 'upload' for item in self.writes), 1)
        self.assertFalse(self.release['draft'])

    def test_published_release_missing_asset_is_never_modified(self):
        self.publish()
        self.release['assets'] = self.release['assets'][:1]
        self.writes.clear()
        with self.assertRaisesRegex(ValueError, 'refusing to modify'):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_unexpected_asset_is_not_removed_or_ignored(self):
        self.publish()
        self.release['assets'].append({'name': 'unexpected.zip'})
        self.writes.clear()
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            self.publish()
        self.assertEqual(self.writes, [])

    def test_changed_tag_before_publication_leaves_draft_unpublished(self):
        normal_command = self.command
        def change_target(*args, **kwargs):
            result = normal_command(*args, **kwargs)
            self.target = 'b' * 40
            return result
        with patch.object(publisher, 'api', side_effect=self.api), patch.object(publisher, 'command', side_effect=change_target):
            with self.assertRaisesRegex(ValueError, 'changed during preparation'):
                publisher.publish('example/tool', SHA, self.root)
        self.assertTrue(self.release['draft'])
        self.assertFalse(any(len(item) > 1 and item[1] == 'PATCH' for item in self.writes))

    def test_semantic_release_requires_existing_tag(self):
        with self.assertRaisesRegex(ValueError, 'existing tag'):
            self.publish(tag='v42')
        self.assertEqual(self.writes, [])
        self.target = SHA
        self.assertEqual(self.publish(tag='v42')['tag'], 'v42')

    def test_annotated_tag_resolves_to_commit(self):
        with patch.object(publisher, 'api', side_effect=[{'object': {'type': 'tag', 'sha': 'c' * 40}}, {'object': {'type': 'commit', 'sha': SHA}}]):
            self.assertEqual(publisher.tag_commit('example/tool', 'v42'), SHA)


class ArtifactTests(unittest.TestCase):
    def test_artifacts_are_reproducible_and_ignore_working_tree_and_untracked_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.github').mkdir()
            (root / '.github/release.json').write_text(json.dumps({'name': 'fixture', 'extensions': [{'directory': '.', 'files': ['metadata.json', 'extension.js', 'buildInfo.js']}]}))
            (root / 'metadata.json').write_text('{"uuid":"fixture@example.invalid"}')
            (root / 'extension.js').write_text('// committed source')
            (root / 'buildInfo.js').write_text("export const BUILD_REVISION = 'development';")
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL)
            git('init', '-q')
            git('add', '.')
            # Synthetic identity is confined to an ephemeral test repository.
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            sha = git('rev-parse', 'HEAD').decode().strip()
            (root / 'secret.log').write_text('not for publication')
            (root / 'extension.js').write_text('// dirty replacement')
            real_command = publisher.command
            def local_command(*args, **kwargs):
                return real_command(args[0], '-C', str(root), *args[1:], **kwargs)
            with patch.object(publisher, 'command', side_effect=local_command):
                publisher.prepare(sha, root / 'first')
                publisher.prepare(sha, root / 'second')
            self.assertEqual({p.name: p.read_bytes() for p in (root / 'first').iterdir()},
                             {p.name: p.read_bytes() for p in (root / 'second').iterdir()})
            with tarfile.open(next((root / 'first').glob('*.tar.gz'))) as archive:
                self.assertFalse(any(name.endswith('secret.log') for name in archive.getnames()))
                self.assertEqual(archive.extractfile(f'fixture-{sha}/extension.js').read(), b'// committed source')
            with zipfile.ZipFile(next((root / 'first').glob('*.zip'))) as archive:
                self.assertEqual(archive.read('extension.js'), b'// committed source')
                self.assertIn(sha.encode(), archive.read('buildInfo.js'))


if __name__ == '__main__':
    unittest.main()
