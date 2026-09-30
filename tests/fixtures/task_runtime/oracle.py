"""Evaluator-owned observable checks, independent of the task runtime."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

FIXTURES = Path(__file__).resolve().parent


def file_snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in Path(root).rglob('*') if p.is_file()}


class Sandbox:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='task-cases-')
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'project'
        self.other = self.root / 'second-worktree'
        self.data = self.root / 'data'
        self.home = self.root / 'home'
        self.home.mkdir()
        self.data.mkdir()
        self.env = {'PATH': os.environ.get('PATH', os.defpath), 'LANG': 'C.UTF-8'}
        self.env.update(HOME=str(self.home), GIT_CONFIG_NOSYSTEM='1',
                        GIT_CONFIG_GLOBAL=os.devnull, PYTHONPATH='',
                        PYTHONNOUSERSITE='1')
        shutil.copytree(FIXTURES / 'project', self.repo,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        manifest = json.loads((FIXTURES / 'manifest.json').read_text())
        for name, expected in manifest.items():
            assert hashlib.sha256((self.repo / name).read_bytes()).hexdigest() == expected, name
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '-qm', 'Frozen synthetic input')
        self.git('worktree', 'add', '-q', '--detach', str(self.other))
        self.retained = [self.repo / 'docs/unrelated.md', self.repo / 'keep.txt',
                         self.other / 'keep.txt', self.root / 'out-of-scope.txt']
        for path in self.retained[1:]:
            path.write_text('preserve ' + path.name + '\n')
        self.protected = {str(p): p.read_bytes() for p in self.retained}
        return self

    def __exit__(self, *args):
        self.temp.cleanup()

    def scoped(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('fixture path escapes disposable root')
        return path

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], env=self.env,
                              text=True, capture_output=True, check=True, timeout=15)

    def python(self, *args, cwd=None, paths=()):
        cwd = self.scoped(cwd or self.repo)
        if cwd not in {self.repo, self.other}:
            raise ValueError('command workspace is not an owned Git worktree')
        for path in paths:
            self.scoped(path)
        for arg in args:
            if Path(str(arg)).is_absolute():
                self.scoped(arg)
        return subprocess.run([sys.executable, '-I', *map(str, args)], cwd=cwd,
                              env=self.env, capture_output=True, timeout=15)


def h01(output, documentation):
    assert Path(output).read_bytes() == b'Alpha\n\nBeta\n', 'strip/order/blank-line output mismatch'
    assert '--mode strip' in Path(documentation).read_text(), 'usage missing new option'


def h02(observed):
    assert observed['requirements'] == {
        'REQ-MODE': 'default lower', 'REQ-BLANK': 'preserve blank lines',
        'REQ-INPUT': 'do not modify input'}, 'lost or replaced requirement'
    assert observed['ordinals'] == ['REQ-INPUT', 'REQ-MODE', 'REQ-BLANK'], 'unstable requirement identity'
    assert observed['stale_write_rejected'] is True, 'concurrent old revision accepted'
    assert observed['result_validity'] == {
        'REQ-MODE': False, 'REQ-BLANK': True, 'REQ-INPUT': False}, 'wrong result validity'


def h03(observed):
    assert set(observed['candidates']) == {'task-transform', 'task-preview'}, 'missing ambiguity'
    assert observed['selected'] is None, 'ambiguous selection guessed'
    assert observed['pending'] == ['finish lower-mode output'], 'resume work omitted'
    assert observed['prohibitions'] == ['do not edit source input', 'do not publish'], 'lost restriction'


def h04(before_state, after_state, before_files, after_files, current_requirement):
    assert after_state == before_state, 'queries/retries changed logical state'
    assert after_files == before_files, 'queries/retries grew or rewrote managed files'
    assert after_state['current_requirement'] == current_requirement, 'stale current state'


def protected_unchanged(expected):
    for name, content in expected.items():
        path = Path(name)
        assert path.is_file() and path.read_bytes() == content, 'protected path changed: ' + name


def h05(sandbox, protected, disposable):
    protected_unchanged(protected)
    assert not Path(disposable).exists(), 'normal owned disposable target was not cleaned'
    fixture = sandbox.repo / 'tests/fixtures/input.json'
    assert fixture.read_bytes() == (FIXTURES / 'project/records/input.json').read_bytes(), 'fixture migration lost bytes'
    assert not (sandbox.repo / 'records/input.json').exists(), 'obsolete record dependency retained'
    result = sandbox.python('-m', 'unittest', 'discover', '-s', 'tests', '-q')
    assert result.returncode == 0, result.stderr.decode()
