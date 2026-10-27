import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import types
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('manage', Path(__file__).parents[1] / 'scripts/manage.py')
manage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manage)


class FakeTools:
    def __init__(self):
        self.formulae = set()
        self.prefix = '/fake/homebrew'
        self.casks = set()
        self.extensions = set()
        self.calls = []
        self.fail_install = False
        self.fail_inventory_after_install = False
        self.inventory_broken = False
        self.fail_remove = False

    def __call__(self, command, **kwargs):
        command = [str(value) for value in command]
        self.calls.append((command, kwargs))
        name = Path(command[0]).name
        if name == 'brew':
            if command[1:] == ['--prefix']:
                return subprocess.CompletedProcess(command, 0, self.prefix + '\n', '')
            category = self.casks if '--cask' in command else self.formulae
            if command[1] == 'list':
                if self.inventory_broken:
                    raise subprocess.CalledProcessError(1, command, stderr='inventory unavailable')
                return subprocess.CompletedProcess(command, 0, '\n'.join(sorted(category)), '')
            token = command[-1].rsplit('/', 1)[-1]
            if command[1] == 'install':
                category.add(token)
                if self.fail_inventory_after_install:
                    self.inventory_broken = True
                if self.fail_install:
                    raise subprocess.CalledProcessError(1, command, stderr='post-install failed')
            if command[1] == 'uninstall':
                if self.fail_remove:
                    raise subprocess.CalledProcessError(1, command, stderr='required by another package')
                category.discard(token)
        elif name == 'code':
            if command[1] == '--list-extensions':
                return subprocess.CompletedProcess(command, 0, '\n'.join(sorted(self.extensions)), '')
            if command[1] == '--install-extension':
                self.extensions.add(command[2])
            elif command[1] == '--uninstall-extension':
                self.extensions.discard(command[2])
        else:
            raise AssertionError('Unexpected command: ' + repr(command))
        return subprocess.CompletedProcess(command, 0, '', '')


class BaseFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / 'repo'
        self.home = self.root / 'home'
        self.home.mkdir()
        for source, _ in manage.FILE_MAP:
            source = self.repo / source
            source.parent.mkdir(parents=True, exist_ok=True)
            if source.name == 'config' and source.parent.name == 'shell':
                source.mkdir()
                (source / 'test.bash').write_text('true\n')
            else:
                source.write_text('# portable config\n')
        (self.repo / 'vscode').mkdir()
        (self.repo / 'vscode/settings.json').write_text('{}\n')
        self.stdout = contextlib.redirect_stdout(io.StringIO())
        self.stderr = contextlib.redirect_stderr(io.StringIO())
        self.stdout.__enter__()
        self.stderr.__enter__()
        self.addCleanup(self.stdout.__exit__, None, None, None)
        self.addCleanup(self.stderr.__exit__, None, None, None)

    def manager(self, **kwargs):
        return manage.Manager(self.repo, self.home, **kwargs)


class LifecycleTests(BaseFixture):
    def test_backup_round_trip_preserves_files_dirs_and_symlinks(self):
        (self.home / '.bashrc').write_text('original shell\n')
        (self.home / '.bash_profile').symlink_to('missing-original-profile')
        directory = self.home / '.config/personal-shell'
        directory.mkdir(parents=True)
        (directory / 'private').write_text('original contents')
        manager = self.manager()
        with manager.locked():
            for source, target in manage.FILE_MAP:
                manager.link(source, target)
            self.assertTrue((self.home / '.bashrc').is_symlink())
            self.assertEqual(len(manager.state['files']), len(manage.FILE_MAP))
            manager.restore_configs()
        self.assertEqual((self.home / '.bashrc').read_text(), 'original shell\n')
        self.assertEqual(os.readlink(self.home / '.bash_profile'), 'missing-original-profile')
        self.assertEqual((directory / 'private').read_text(), 'original contents')
        self.assertFalse(manage.exists(self.home / '.inputrc'))
        self.assertFalse(manager.state['files'])
        self.assertEqual(manager.state_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(manager.directory.stat().st_mode & 0o777, 0o700)

    def test_repeated_install_keeps_first_backup(self):
        target = self.home / '.bashrc'
        target.write_text('original')
        first = self.manager()
        with first.locked():
            first.link('shell/bashrc', '.bashrc')
            backup = first.state['files'][str(target)]['backup']
        second = self.manager()
        with second.locked():
            second.link('shell/bashrc', '.bashrc')
            self.assertEqual(second.state['files'][str(target)]['backup'], backup)
            second.restore_configs()
        self.assertEqual(target.read_text(), 'original')

    def test_preexisting_identical_link_not_adopted(self):
        target = self.home / '.bashrc'
        target.symlink_to(self.repo / 'shell/bashrc')
        manager = self.manager()
        with manager.locked():
            manager.link('shell/bashrc', '.bashrc')
            manager.restore_configs()
        self.assertTrue(target.is_symlink())
        self.assertFalse(manager.state['files'])

    def test_replaced_target_protected_and_backup_retained(self):
        target = self.home / '.bashrc'
        target.write_text('original')
        manager = self.manager()
        with manager.locked():
            manager.link('shell/bashrc', '.bashrc')
            target.rename(self.home / '.bashrc.moved')
            target.write_text('new user configuration')
            manager.link('shell/bashrc', '.bashrc')
            manager.restore_configs()
            self.assertEqual(target.read_text(), 'new user configuration')
            self.assertTrue((self.home / '.bashrc.moved').is_symlink())
            self.assertEqual(Path(manager.state['files'][str(target)]['backup']).read_text(), 'original')
            self.assertEqual(len(manager.problems), 2)

    def test_changed_link_protected(self):
        target = self.home / '.bashrc'
        manager = self.manager()
        with manager.locked():
            manager.link('shell/bashrc', '.bashrc')
            target.unlink()
            target.symlink_to('some-other-file')
            manager.restore_configs()
        self.assertEqual(os.readlink(target), 'some-other-file')
        self.assertIn(str(target), manager.state['files'])

    def test_dry_run_no_files_created_or_changed(self):
        target = self.home / '.bashrc'
        target.write_text('untouched')
        before = sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*'))
        manager = self.manager(dry_run=True)
        with manager.locked():
            manager.link('shell/bashrc', '.bashrc')
            manager.link('shell/inputrc', '.inputrc')
        self.assertEqual(target.read_text(), 'untouched')
        self.assertEqual(before, sorted(str(p.relative_to(self.home)) for p in self.home.rglob('*')))

    def test_interrupted_install_after_backup_can_resume(self):
        target = self.home / '.bashrc'
        target.write_text('original')
        first = self.manager()
        with first.locked(), mock.patch.object(manage.os, 'symlink', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                first.link('shell/bashrc', '.bashrc')
        self.assertFalse(manage.exists(target))
        second = self.manager()
        with second.locked():
            second.link('shell/bashrc', '.bashrc')
            second.restore_configs()
        self.assertEqual(target.read_text(), 'original')

    def test_interrupted_install_before_backup_can_uninstall(self):
        target = self.home / '.bashrc'
        target.write_text('original')
        first = self.manager()
        actual_replace = manage.os.replace
        def interrupted(source, destination):
            if Path(source) == target:
                raise OSError('interrupted')
            return actual_replace(source, destination)
        with first.locked(), mock.patch.object(manage.os, 'replace', side_effect=interrupted):
            with self.assertRaises(OSError):
                first.link('shell/bashrc', '.bashrc')
        second = self.manager()
        with second.locked():
            second.restore_configs()
        self.assertEqual(target.read_text(), 'original')
        self.assertFalse(second.state['files'])

    def test_interrupted_restore_can_resume(self):
        target = self.home / '.bashrc'
        target.write_text('original')
        manager = self.manager()
        actual_replace = manage.os.replace
        def interrupted(source, destination):
            if Path(destination) == target:
                raise OSError('interrupted')
            return actual_replace(source, destination)
        with manager.locked():
            manager.link('shell/bashrc', '.bashrc')
            with mock.patch.object(manage.os, 'replace', side_effect=interrupted):
                with self.assertRaises(OSError):
                    manager.restore_configs()
        again = self.manager()
        with again.locked():
            again.restore_configs()
        self.assertEqual(target.read_text(), 'original')
        self.assertFalse(again.state['files'])

    def test_second_operation_is_locked_out(self):
        with self.manager().locked():
            with self.assertRaises(RuntimeError):
                with self.manager().locked():
                    self.fail('Acquired concurrent lock')

    def test_state_symlink_rejected_without_chmod_or_writes(self):
        other = self.root / 'other'
        other.mkdir(mode=0o755)
        state_parent = self.home / '.local/state'
        state_parent.mkdir(parents=True)
        (state_parent / 'dotfiles').symlink_to(other, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            with self.manager().locked():
                pass
        self.assertEqual(other.stat().st_mode & 0o777, 0o755)
        self.assertFalse(list(other.iterdir()))

    def test_backup_directory_symlink_rejected(self):
        manager = self.manager()
        manager.directory.mkdir(parents=True)
        other = self.root / 'other'
        other.mkdir()
        (manager.directory / 'backups').symlink_to(other)
        with self.assertRaises(RuntimeError):
            with manager.locked():
                pass

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_git_identity_and_later_edits_preserved(self):
        target = self.home / '.gitconfig'
        original = '[user]\n\tname = Local Person\n\temail = local@example.test\n'
        target.write_text(original)
        manager = self.manager()
        with manager.locked():
            manager.git_include()
            manager.git_include()
            target.write_text(target.read_text() + '[alias]\n\tst = status\n')
            manager.remove_git_include()
        self.assertEqual(target.read_text(), original + '[alias]\n\tst = status\n')

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_preexisting_git_include_not_adopted(self):
        target = self.home / '.gitconfig'
        original = '[include]\n\tpath = ~/.config/personal-git/config\n[user]\n\tname = Personal\n'
        target.write_text(original)
        manager = self.manager()
        with manager.locked():
            manager.git_include()
            self.assertNotIn('git_include', manager.state)
            manager.remove_git_include()
        self.assertEqual(target.read_text(), original)

    @unittest.skipUnless(shutil.which('git'), 'Git required')
    def test_interrupted_git_write_can_resume(self):
        target = self.home / '.gitconfig'
        target.write_text('[user]\n\tname = Original\n')
        manager = self.manager()
        with manager.locked(), mock.patch.object(manager, 'write_git_config', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                manager.git_include()
        again = self.manager()
        with again.locked():
            again.git_include()
            self.assertIn('# BEGIN personal-dotfiles', target.read_text())
            again.remove_git_include()
        self.assertEqual(target.read_text(), '[user]\n\tname = Original\n')

    def test_linux_vscode_settings_use_config_directory(self):
        manager = self.manager()
        with manager.locked(), mock.patch.object(manage.platform, 'system', return_value='Linux'):
            manager.configs()
            self.assertTrue((self.home / '.config/Code/User/settings.json').is_symlink())
            self.assertFalse((self.home / 'Library').exists())
            manager.restore_configs()

    def test_wrappers_preserve_homebrew_already_in_path(self):
        binaries = self.root / 'bin'
        binaries.mkdir()
        brew = binaries / 'brew'
        brew.write_text('#!/bin/sh\nexit 0\n')
        brew.chmod(0o700)
        python = binaries / 'python3'
        python.write_text('#!/bin/sh\ncommand -v brew\n')
        python.chmod(0o700)
        for wrapper in ('install.sh', 'uninstall.sh'):
            with self.subTest(wrapper=wrapper):
                result = subprocess.run(
                    ['/bin/bash', str(Path(__file__).parents[1] / wrapper), '--help'],
                    env={**os.environ, 'PATH': str(binaries) + ':/usr/bin:/bin'},
                    text=True, capture_output=True, check=True)
                self.assertEqual(result.stdout.strip(), str(brew))

    def test_alternate_home_rejects_tool_actions(self):
        with self.assertRaises(SystemExit) as result:
            manage.main(['install', '--target-home', str(self.home)])
        self.assertEqual(result.exception.code, 2)
        with self.assertRaises(SystemExit) as result:
            manage.main(['uninstall', '--target-home', str(self.home), '--purge-tools'])
        self.assertEqual(result.exception.code, 2)


class OwnershipTests(BaseFixture):
    def setUp(self):
        super().setUp()
        self.fake = FakeTools()
        self.manager_instance = self.manager(runner=self.fake)
        self.manager_instance.brew = '/fake/brew'
        self.manager_instance.code = '/fake/code'

    def test_linux_without_code_skips_casks_and_warns_about_extensions(self):
        manifest = {'formulae': [], 'casks': ['visual-studio-code'],
                    'vscode_extensions': ['new.extension']}
        (self.repo / 'packages.json').write_text(json.dumps(manifest))
        manager = self.manager_instance
        manager.code = None
        rust = types.SimpleNamespace(setup=lambda *args, **kwargs: 'Rust test stub')
        with manager.locked(), mock.patch.object(manage.platform, 'system', return_value='Linux'), \
                mock.patch.object(manage.shutil, 'which', return_value=None), \
                mock.patch.dict('sys.modules', {'rust_setup': rust}):
            manager.install_tools()
        self.assertTrue(all(call[0][1:] == ['--prefix'] for call in self.fake.calls))
        self.assertFalse(manager.state['tools']['casks'])
        self.assertEqual(len(manager.problems), 1)
        self.assertIn('extensions are skipped', manager.problems[0])

    def test_linux_with_code_installs_extensions_but_no_casks(self):
        manifest = {'formulae': [], 'casks': ['visual-studio-code'],
                    'vscode_extensions': ['new.extension']}
        (self.repo / 'packages.json').write_text(json.dumps(manifest))
        manager = self.manager_instance
        rust = types.SimpleNamespace(setup=lambda *args, **kwargs: 'Rust test stub')
        with manager.locked(), mock.patch.object(manage.platform, 'system', return_value='Linux'), \
                mock.patch.object(manage.shutil, 'which', return_value='/fake/code'), \
                mock.patch.dict('sys.modules', {'rust_setup': rust}):
            manager.install_tools()
        self.assertFalse(self.fake.casks)
        self.assertEqual(self.fake.extensions, {'new.extension'})
        self.assertEqual(manager.state['tools']['extensions'], ['new.extension'])
        self.assertFalse(manager.problems)

    def test_changed_brew_provider_refuses_purge_and_preserves_other_installation(self):
        manager = self.manager_instance
        self.fake.prefix = '/fake/brew-a'
        target = self.home / '.bashrc'
        target.write_text('original shell')
        with manager.locked():
            manager.add_tools('formulae', ['fzf'])
            manager.link('shell/bashrc', '.bashrc')
        other = FakeTools()
        other.prefix = '/fake/brew-b'
        other.formulae = {'fzf'}
        again = self.manager(runner=other)
        again.brew = '/different/bin/brew'
        rust = types.SimpleNamespace(purge=mock.Mock(side_effect=AssertionError('Must not purge Rust')))
        with again.locked(), mock.patch.dict('sys.modules', {'rust_setup': rust}):
            again.restore_configs()
            self.assertEqual(target.read_text(), 'original shell')
            with self.assertRaisesRegex(RuntimeError, 'Homebrew installation changed'):
                again.purge_tools()
            self.assertEqual(again.state['tools']['formulae'], ['fzf'])
        self.assertEqual(other.formulae, {'fzf'})
        self.assertTrue(all(call[0][1:] == ['--prefix'] for call in other.calls))
        rust.purge.assert_not_called()

    def test_changed_brew_provider_refuses_install_resume(self):
        manager = self.manager_instance
        self.fake.prefix = '/fake/brew-a'
        with manager.locked():
            manager.add_tools('formulae', ['fzf'])
            self.fake.prefix = '/fake/brew-b'
            self.fake.calls.clear()
            with self.assertRaisesRegex(RuntimeError, 'Homebrew installation changed'):
                manager.add_tools('formulae', ['k9s'])
        self.assertNotIn('k9s', self.fake.formulae)
        self.assertTrue(all(call[0][1:] == ['--prefix'] for call in self.fake.calls))

    def test_equivalent_prefix_accepts_changed_executable_alias(self):
        manager = self.manager_instance
        with manager.locked():
            manager.add_tools('formulae', ['fzf'])
        again = self.manager(runner=self.fake)
        again.brew = '/another/alias/bin/brew'
        with again.locked():
            again.purge_tools()
        self.assertFalse(self.fake.formulae)
        self.assertFalse(again.state['tools']['formulae'])

    def test_unrecorded_provider_never_claims_existing_ownership(self):
        manager = self.manager_instance
        self.fake.formulae = {'fzf'}
        with manager.locked():
            manager.state['tools']['formulae'] = ['fzf']
            with self.assertRaisesRegex(RuntimeError, 'no recorded provider'):
                manager.purge_tools()
        self.assertEqual(self.fake.formulae, {'fzf'})

    def test_only_new_roots_and_extensions_are_owned(self):
        self.fake.formulae = {'git', 'terraform', 'preexisting-dependency'}
        self.fake.extensions = {'existing.extension'}
        manager = self.manager_instance
        with manager.locked():
            manager.add_tools('formulae', ['git', 'hashicorp/tap/terraform', 'fzf'])
            manager.add_tools('extensions', ['existing.extension', 'New.Extension'])
            self.assertEqual(manager.state['tools']['formulae'], ['fzf'])
            self.assertEqual(manager.state['tools']['extensions'], ['new.extension'])
            manager.purge_tools()
        self.assertEqual(self.fake.formulae, {'git', 'terraform', 'preexisting-dependency'})
        self.assertEqual(self.fake.extensions, {'existing.extension'})
        self.assertFalse(manager.state['tools']['formulae'])
        self.assertFalse(manager.state['tools']['extensions'])

    def test_failed_install_retains_successfully_added_root(self):
        self.fake.fail_install = True
        manager = self.manager_instance
        with manager.locked():
            with self.assertRaises(subprocess.CalledProcessError):
                manager.add_tools('formulae', ['hashicorp/tap/terraform'])
            self.assertEqual(manager.state['tools']['formulae'], ['hashicorp/tap/terraform'])
            self.assertEqual(manager.state['tools']['pending'], [])
        stored = json.loads(manager.state_file.read_text())
        self.assertEqual(stored['tools']['formulae'], ['hashicorp/tap/terraform'])

    def test_failed_inventory_retains_pending_journal_and_recovers(self):
        self.fake.fail_inventory_after_install = True
        manager = self.manager_instance
        with manager.locked():
            with self.assertRaises(subprocess.CalledProcessError):
                manager.add_tools('formulae', ['fzf'])
            self.assertEqual(manager.state['tools']['pending'], [{'category': 'formulae', 'name': 'fzf'}])
            self.fake.inventory_broken = False
            manager.reconcile(['formulae'])
            self.assertEqual(manager.state['tools']['formulae'], ['fzf'])
            self.assertEqual(manager.state['tools']['pending'], [])

    def test_dependency_conflict_retains_package_ownership(self):
        manager = self.manager_instance
        with manager.locked():
            manager.add_tools('formulae', ['fzf'])
            self.fake.fail_remove = True
            manager.purge_tools()
            self.assertEqual(manager.state['tools']['formulae'], ['fzf'])
            self.assertIn('fzf', self.fake.formulae)
            self.assertTrue(manager.problems)

    def test_dry_run_never_calls_install_or_uninstall(self):
        manager = self.manager_instance
        manager.dry_run = True
        with manager.locked():
            manager.add_tools('formulae', ['fzf'])
            manager.add_tools('extensions', ['new.extension'])
            manager.state['tools']['formulae'] = ['git']
            self.fake.formulae.add('git')
            manager.purge_tools()
        self.assertTrue(all('install' not in call[0] and 'uninstall' not in call[0]
                            and '--install-extension' not in call[0] for call in self.fake.calls))
        self.assertFalse(manager.directory.exists())

    def test_no_vscode_keeps_owned_cask_and_extension(self):
        manager = self.manager_instance
        manager.no_vscode = True
        self.fake.casks = {'visual-studio-code'}
        self.fake.extensions = {'existing.extension'}
        with manager.locked(), mock.patch.object(manage.platform, 'system', return_value='Darwin'):
            manager.verify_brew_provider(initialize=True)
            manager.state['tools']['casks'] = ['visual-studio-code']
            manager.state['tools']['extensions'] = ['existing.extension']
            manager.purge_tools()
        self.assertEqual(self.fake.casks, {'visual-studio-code'})
        self.assertEqual(self.fake.extensions, {'existing.extension'})

    def test_existing_unmanaged_vscode_app_is_not_adopted(self):
        app = self.home / 'Applications/Visual Studio Code.app'
        app.mkdir(parents=True)
        manager = self.manager_instance
        with manager.locked():
            manager.add_tools('casks', ['visual-studio-code'])
        self.assertFalse(manager.state['tools']['casks'])
        self.assertFalse(self.fake.casks)


if __name__ == '__main__':
    unittest.main()
