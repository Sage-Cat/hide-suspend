"""Privacy checks in isolated repositories; fixtures contain no real credentials."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('privacy', Path(__file__).with_name('privacy.py'))
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)

    def commit(self, paths, message='Add fixture'):
        for name, data in paths.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data.encode() if isinstance(data, str) else data)
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', message)

    def scan(self, **kwargs):
        with patch.object(privacy, 'git', side_effect=self.git):
            return privacy.scan(**kwargs)

    def test_private_paths_and_runtime_data_are_rejected(self):
        paths = ['AGENTS.md', 'docs/AGENTS.local.md', 'CLAUDE.md', 'GEMINI.md', 'CODEX.md',
                 '.codex/settings.toml', '.claude/x', '.agents/x', '.cursor/x',
                 '.github/copilot-instructions.md', 'logs/run.txt', 'runtime/state.json',
                 'transcripts/session.txt', 'checkpoints/current.json', 'snapshots/current.json',
                 '.env', '.env.production', 'credentials.json', 'id_ed25519', 'key.pem', 'state.sqlite']
        self.commit(dict.fromkeys(paths, 'private fixture'))
        findings = self.scan()
        self.assertEqual({location for _, location in findings}, set(paths))

    def test_forced_tracked_host_data_directories_are_rejected_at_any_depth(self):
        paths = ['private/profile.toml', 'local/host.json',
                 'nested/state/current.json', 'nested/backups/profile.toml']
        self.commit(dict.fromkeys(paths, 'host data fixture'))
        self.assertEqual({location for _, location in self.scan()}, set(paths))

    def test_functional_code_identifiers_and_schema_only_fixtures_are_allowed(self):
        schema = [['table', 'threads', 'threads', 'CREATE TABLE threads (id TEXT PRIMARY KEY)']]
        self.commit({'src/codex_resume.py': 'UUID = "input-source-popup-guard@sagecat.local"\n# codex resume adapter\n',
                     'tests/test_checkpoint.py': '# checkpoint recovery tests',
                     'tests/fixtures/state_5.sqlite.schema.json': json.dumps(schema)})
        self.assertEqual(self.scan(), [])

    def test_schema_named_data_and_disguised_database_are_rejected(self):
        self.commit({'tests/fixtures/state.sqlite.schema.json': json.dumps({'rows': ['private']}),
                     'tests/fixtures/data.bin': b'SQLite format 3\0sensitive data'})
        self.assertEqual(len(self.scan()), 2)

    def test_schema_wrapper_cannot_smuggle_row_insert_statements(self):
        schema = [['table', 'threads', 'threads', "CREATE TABLE threads (id TEXT); INSERT INTO threads VALUES ('private')"]]
        self.commit({'tests/fixtures/state.sqlite.schema.json': json.dumps(schema)})
        self.assertEqual(self.scan()[0][0], 'database fixture is not schema-only')

    def test_key_and_token_signatures_do_not_echo_their_contents(self):
        token = 'gh' + 'p_' + 'a' * 36
        key = '-----BEGIN ' + 'PRIVATE KEY-----\nfixture\n'
        self.commit({'src/innocent.py': token, 'docs/key.txt': key})
        findings = self.scan()
        self.assertEqual(len(findings), 2)
        self.assertNotIn(token, repr(findings))
        self.assertNotIn(key, repr(findings))

    def test_ai_commit_attribution_is_rejected_but_functional_subject_is_allowed(self):
        self.commit({'adapter.py': '# functional code'}, 'Fix Codex resume parsing')
        self.assertEqual(self.scan(), [])
        self.commit({'adapter.py': '# corrected'}, 'Fix parser\n\nCo-authored-by: ' + 'Codex <bot@example.invalid>')
        self.assertEqual(self.scan()[0][0], 'AI commit attribution')
        self.commit({'adapter.py': '# tested'}, 'Test parser')
        self.assertEqual(self.scan(), [])
        self.assertEqual(self.scan(history=True)[0][0], 'AI commit attribution')

    def test_initial_index_can_be_inspected_without_head(self):
        (self.root / 'AGENTS.md').write_text('private instructions')
        self.git('add', 'AGENTS.md')
        self.assertEqual(self.scan(index=True)[0][1], 'AGENTS.md')

    def test_index_gate_detects_staged_private_file_before_commit(self):
        self.commit({'public.py': '# allowed'})
        (self.root / 'AGENTS.md').write_text('private instructions')
        self.git('add', 'AGENTS.md')
        self.assertEqual(self.scan(), [])
        self.assertEqual(self.scan(index=True)[0][1], 'AGENTS.md')


if __name__ == '__main__':
    unittest.main()
