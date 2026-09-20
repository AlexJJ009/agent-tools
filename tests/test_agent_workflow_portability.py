"""Real subprocess install from tracked sources into an isolated child-process home."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.workflow_support import context, repository

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux/WSL installer')
class PortabilityTests(unittest.TestCase):
    def test_tracked_export_survives_source_relocation(self):
        evidence = os.environ.get('WORKFLOW_PORTABILITY_EVIDENCE')
        if evidence:
            base = Path(evidence).resolve()
            base.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(prefix='workflow-portability-')
            self.addCleanup(temporary.cleanup)
            base = Path(temporary.name)
        source = base / 'export with spaces'
        source.mkdir()
        paths = subprocess.check_output(['git', 'ls-files', '-z', '--', 'agent_workflow',
            'skills/intent-to-contract', 'skills/infra-verification', 'skills/cleaner',
            'skills/acceptance-gate', 'skills/reviewer-brief', 'docs/AGENT_WORKFLOW.md',
            'scripts/install_agent_workflow.py', 'scripts/codex_target_guard.py'], cwd=ROOT).decode().split('\0')
        manifest = {}
        for relative in filter(None, paths):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
            manifest[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
        (base / 'source-manifest.json').write_text(json.dumps(manifest, indent=2))
        # HOME is isolated only in child environments, never in the running agent.
        isolated_home = base / 'isolated user'
        isolated_home.mkdir()
        env = {'HOME': str(isolated_home), 'PATH': os.defpath, 'LANG': 'C.UTF-8',
               'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        trace = []

        def run(argv, expected=0):
            result = subprocess.run([str(a) for a in argv], cwd=base, env=env,
                                    capture_output=True, text=True)
            trace.append({'argv': [str(a) for a in argv], 'cwd': str(base),
                          'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
            (base / 'trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
            return result.stdout

        run([sys.executable, source / 'scripts/codex_target_guard.py', '--platform', 'auto',
             '--path-only', '--allow-missing-config', '--allow-missing-cc-switch',
             '--skip-cc-switch-read-check', '--json'])
        installer = source / 'scripts/install_agent_workflow.py'
        run([sys.executable, installer])
        run([sys.executable, installer, '--check'])
        run([sys.executable, installer])  # Existing managed installation upgrade path.
        run([sys.executable, installer, '--check'])
        source.rename(base / 'source moved away')
        launcher = isolated_home / '.local/bin/agent-workflow'
        run([launcher, '--help'])
        project = repository(base / 'fixture project')
        oracle, ctx = context('algorithm')
        query = base / 'query.txt'
        query.write_text(oracle['query'])
        context_file = base / 'context.json'
        context_file.write_text(json.dumps(ctx))
        record = json.loads(run([launcher, 'init', '--repo', project, '--query', query,
            '--context', context_file, '--scenario', 'algorithm', '--mode', 'simulation']))['record']
        run([launcher, 'check', '--record', record, '--phase', 'agent'])
        run([launcher, 'gate', '--record', record, '--action', 'formal-run'], expected=1)
        self.assertFalse((isolated_home / '.codex').exists())
        self.assertFalse((isolated_home / '.cc-switch').exists())
