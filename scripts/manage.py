#!/usr/bin/env python3
"""Install personal dotfiles, retaining reversible ownership in private local state."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

VERSION = 1
FILE_MAP = (
    ('shell/bashrc', '.bashrc'),
    ('shell/bash_profile', '.bash_profile'),
    ('shell/inputrc', '.inputrc'),
    ('shell/config', '.config/personal-shell'),
    ('git/config', '.config/personal-git/config'),
    ('git/ignore', '.config/personal-git/ignore'),
)


def exists(path):
    return os.path.lexists(str(path))


def fingerprint(path):
    stat = path.lstat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
            os.readlink(path) if path.is_symlink() else None]


def installed_name(name, installed):
    return name in installed or name.rsplit('/', 1)[-1] in installed


def run(command, **kwargs):
    kwargs.setdefault('text', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('check', True)
    return subprocess.run([str(part) for part in command], **kwargs)


class Manager:
    def __init__(self, repo, home, dry_run=False, no_vscode=False, runner=run):
        self.repo, self.home = Path(repo).resolve(), Path(home).resolve()
        self.dry_run, self.no_vscode, self.run = dry_run, no_vscode, runner
        self.directory = self.home / '.local/state/dotfiles'
        self.state_file = self.directory / 'state.json'
        self.state = {'version': VERSION, 'home': str(self.home), 'files': {},
                      'tools': {'formulae': [], 'casks': [], 'extensions': [], 'pending': []}}
        self.problems = []
        self.brew = shutil.which('brew')
        self.code = shutil.which('code')
        if not self.code and platform.system() == 'Darwin':
            candidate = Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code')
            if candidate.is_file():
                self.code = str(candidate)

    def say(self, message):
        print(('DRY RUN: ' if self.dry_run else '') + message)

    def problem(self, message):
        self.problems.append(message)
        print('WARNING: ' + message, file=sys.stderr)

    def check_state_paths(self):
        paths = [self.home / '.local', self.home / '.local/state', self.directory,
                 self.directory / 'lock', self.state_file, self.directory / 'backups']
        for path in paths:
            if path.is_symlink():
                raise RuntimeError('State path must not be a symlink: ' + str(path))

    def load(self):
        self.check_state_paths()
        if self.state_file.exists():
            self.state = json.loads(self.state_file.read_text())
            if self.state.get('version') != VERSION or self.state.get('home') != str(self.home):
                raise RuntimeError('State version or home does not match; refusing to modify it.')
            for target, entry in self.state.get('files', {}).items():
                if not Path(target).is_absolute() or self.home not in Path(target).parents:
                    raise RuntimeError('Unsafe target in state: ' + target)
                if entry.get('backup') and Path(entry['backup']).parent != self.directory / 'backups':
                    raise RuntimeError('Unsafe backup path in state.')
            for key in ('formulae', 'casks', 'extensions', 'pending'):
                self.state.setdefault('tools', {}).setdefault(key, [])

    def save(self):
        self.check_state_paths()
        if self.dry_run:
            return
        descriptor, temporary = tempfile.mkstemp(prefix='state-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'w') as output:
                json.dump(self.state, output, indent=2, sort_keys=True)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.state_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @contextlib.contextmanager
    def locked(self, create=True):
        self.check_state_paths()
        if self.dry_run or (not create and not self.directory.exists()):
            self.load()
            yield
            return
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        descriptor = os.open(self.directory / 'lock',
                             os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(descriptor, 'a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another dotfiles operation is running.')
            self.load()
            yield

    def owned_link(self, target, entry):
        return target.is_symlink() and os.readlink(target) in {
            entry['source'], entry.get('previous_source', entry['source'])}

    def link(self, relative_source, relative_target):
        source, target = self.repo / relative_source, self.home / relative_target
        if not source.exists():
            raise RuntimeError('Missing repository source: ' + str(source))
        key = str(target)
        entry = self.state['files'].get(key)
        if entry is None and target.is_symlink() and os.readlink(target) == str(source):
            self.say('Keep pre-existing link: ' + str(target))
            return
        if self.dry_run:
            if entry and exists(target) and not self.owned_link(target, entry):
                self.problem('Changed target will be kept: ' + str(target))
            else:
                self.say('Link ' + str(target) + ' -> ' + str(source) +
                         (' (back up existing target)' if exists(target) and not entry else ''))
            return
        if entry is None:
            backup = None
            original = None
            if exists(target):
                original = fingerprint(target)
                name = hashlib.sha256(key.encode()).hexdigest()[:24]
                backup = str(self.directory / 'backups' / name)
                if exists(Path(backup)):
                    raise RuntimeError('Unexpected existing backup: ' + backup)
            entry = {'source': str(source), 'backup': backup, 'original': original,
                     'phase': 'planned'}
            self.state['files'][key] = entry
            self.save()  # Journal intent before moving any original file.
        if entry['phase'] == 'restoring':
            self.problem('Uninstall incomplete for ' + key + '; finish uninstall before installing.')
            return
        if self.owned_link(target, entry):
            if os.readlink(target) == str(source):
                entry['phase'] = 'installed'
                entry.pop('previous_source', None)
                self.save()
                self.say('Already linked: ' + key)
                return
            entry['previous_source'] = os.readlink(target)
            entry['source'] = str(source)
            entry['phase'] = 'planned'
            self.save()
            target.unlink()
        elif exists(target):
            backup = Path(entry['backup']) if entry['backup'] else None
            if (entry['phase'] == 'planned' and backup and not exists(backup)
                    and fingerprint(target) == entry['original']):
                backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                os.replace(target, backup)
            else:
                self.problem('Target changed by you; keeping it and its backup: ' + key)
                return
        elif entry['backup'] and not exists(Path(entry['backup'])):
            self.problem('Original and backup are both missing; refusing to continue: ' + key)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(source), target)
        entry['source'], entry['phase'] = str(source), 'installed'
        entry.pop('previous_source', None)
        self.save()
        self.say('Linked: ' + key)

    def write_git_config(self, target, content):
        descriptor, temporary = tempfile.mkstemp(prefix='.dotfiles-git-', dir=target.parent)
        try:
            with os.fdopen(descriptor, 'w') as output:
                if target.exists():
                    os.fchmod(output.fileno(), target.stat().st_mode & 0o777)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def git_include(self):
        """Append only an owned include block; preserve all existing Git settings."""
        target = self.home / '.gitconfig'
        path = self.home / '.config/personal-git/config'
        start, end = '# BEGIN personal-dotfiles include', '# END personal-dotfiles include'
        text = target.read_text() if target.exists() else ''
        record = self.state.get('git_include')
        if record:
            if record['block'] in text:
                self.say('Git include already present.')
                if not self.dry_run:
                    record['phase'] = 'installed'
                    self.save()
            elif record.get('phase') == 'planned' and (
                    fingerprint(target) if exists(target) else None) == record['original']:
                self.say('Finish pending Git include installation.')
                if not self.dry_run:
                    self.write_git_config(target, text + record['block'])
                    record['phase'] = 'installed'
                    self.save()
            else:
                self.problem('Managed Git include was changed; keeping your .gitconfig.')
            return
        # Consult Git itself to recognize equivalent pre-existing include.path values.
        git = shutil.which('git')
        if not git:
            self.problem('Git unavailable; include was not installed. Re-run after installing Git.')
            return
        query = self.run([git, 'config', '--file', target, '--get-all', 'include.path'], check=False)
        if query.returncode not in (0, 1):
            self.problem('Cannot parse existing .gitconfig; leaving it unchanged.')
            return
        for value in query.stdout.splitlines():
            expanded = value.replace('~/', str(self.home) + '/', 1) if value.startswith('~/') else value
            if Path(expanded) == path:
                self.say('Keep pre-existing Git include.')
                return
        if start in text or end in text:
            self.problem('Untracked personal-dotfiles markers in .gitconfig; leaving it unchanged.')
            return
        if target.is_symlink():
            self.problem('.gitconfig is a symlink; add include.path manually or use a regular file.')
            return
        escaped = str(path).replace('\\', '\\\\').replace('"', '\\"')
        block = ('\n' if text and not text.endswith('\n') else '') + '\n' + start + \
            '\n[include]\n\tpath = "' + escaped + '"\n' + end + '\n'
        self.say('Add personal Git include to ' + str(target))
        if self.dry_run:
            return
        backup = self.directory / 'backups/gitconfig-before-include'
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            shutil.copy2(target, backup)
            os.chmod(backup, 0o600)
        self.state['git_include'] = {'block': block, 'created': not target.exists(),
                                     'original': fingerprint(target) if target.exists() else None,
                                     'phase': 'planned'}
        self.save()
        self.write_git_config(target, text + block)
        self.state['git_include']['phase'] = 'installed'
        self.save()

    def remove_git_include(self):
        record = self.state.get('git_include')
        if not record:
            return
        target = self.home / '.gitconfig'
        if target.is_symlink():
            self.problem('Changed .gitconfig symlink will be kept.')
            return
        text = target.read_text() if target.exists() else ''
        block = record['block']
        if block not in text:
            if '# BEGIN personal-dotfiles include' in text or '# END personal-dotfiles include' in text:
                self.problem('Changed Git include will be kept in .gitconfig.')
                return
            # The user removed the block, or installation stopped before appending it.
            self.say('Managed Git include already absent.')
        else:
            self.say('Remove personal Git include from ' + str(target))
            if self.dry_run:
                return
            remaining = text.replace(block, '', 1)
            if record['created'] and not remaining:
                target.unlink()
            else:
                self.write_git_config(target, remaining)
        if not self.dry_run:
            del self.state['git_include']
            self.save()

    def configs(self):
        for source, target in FILE_MAP:
            self.link(source, target)
        if not self.no_vscode:
            target = ('Library/Application Support/Code/User/settings.json'
                      if platform.system() == 'Darwin' else '.config/Code/User/settings.json')
            self.link('vscode/settings.json', target)
        self.git_include()

    def restore_configs(self):
        self.remove_git_include()
        for key, entry in reversed(list(self.state['files'].items())):
            target = Path(key)
            if self.no_vscode and target.name == 'settings.json':
                continue
            if (entry['phase'] == 'planned' and exists(target)
                    and entry['original'] == fingerprint(target)
                    and entry['backup'] and not exists(Path(entry['backup']))):
                if not self.dry_run:
                    del self.state['files'][key]
                    self.save()
                continue
            if exists(target) and not self.owned_link(target, entry):
                # Recover a completed restore interrupted just before its final state save.
                if entry['phase'] == 'restoring' and entry['original'] == fingerprint(target):
                    if not self.dry_run:
                        del self.state['files'][key]
                        self.save()
                    continue
                self.problem('Target changed by you; keeping it and its backup: ' + key)
                continue
            backup = Path(entry['backup']) if entry['backup'] else None
            if backup and not exists(backup):
                if entry['phase'] == 'planned' and not exists(target):
                    self.problem('Cannot find original or backup for ' + key)
                else:
                    self.problem('Backup is missing; keeping target: ' + key)
                continue
            self.say('Restore ' + key if backup else 'Remove owned link: ' + key)
            if self.dry_run:
                continue
            entry['phase'] = 'restoring'
            self.save()
            if exists(target):
                target.unlink()
            if backup:
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, target)
            del self.state['files'][key]
            self.save()

    def has_brew_ownership(self):
        tools = self.state['tools']
        return bool(tools['formulae'] or tools['casks'] or
                    any(item['category'] in ('formulae', 'casks') for item in tools['pending']) or
                    self.state.get('rust', {}).get('owner'))

    def verify_brew_provider(self, initialize=False):
        if not self.brew:
            raise RuntimeError('Homebrew is unavailable; managed tools are kept.')
        prefix = self.run([self.brew, '--prefix']).stdout.strip()
        if not prefix or not Path(prefix).is_absolute():
            raise RuntimeError('Homebrew returned an invalid installation prefix.')
        current = {'prefix': str(Path(prefix).resolve()),
                   'executable': str(Path(self.brew).resolve())}
        providers = self.state.setdefault('providers', {})
        recorded = providers.get('brew')
        if recorded:
            if recorded.get('prefix') != current['prefix']:
                raise RuntimeError('Homebrew installation changed from ' + recorded.get('prefix', '?') +
                                   ' to ' + current['prefix'] + '. Managed tools are kept; use the original Homebrew.')
        elif not initialize or self.has_brew_ownership():
            raise RuntimeError('Homebrew ownership has no recorded provider; managed tools are kept.')
        else:
            providers['brew'] = current
            self.save()

    def inventory(self, category):
        if category == 'extensions':
            if not self.code:
                raise RuntimeError('VS Code CLI unavailable; cannot inspect extensions.')
            return set(self.run([self.code, '--list-extensions']).stdout.lower().splitlines())
        if not self.brew:
            raise RuntimeError('Homebrew unavailable; cannot inspect managed packages.')
        flag = '--formula' if category == 'formulae' else '--cask'
        return set(self.run([self.brew, 'list', flag, '-1']).stdout.splitlines())

    def reconcile(self, categories):
        for category in categories:
            pending = [p for p in self.state['tools']['pending'] if p['category'] == category]
            if not pending:
                continue
            installed = self.inventory(category)
            for item in pending:
                if installed_name(item['name'], installed) and item['name'] not in self.state['tools'][category]:
                    self.state['tools'][category].append(item['name'])
                self.state['tools']['pending'].remove(item)
            self.save()

    def add_tools(self, category, requested):
        if not requested:
            return
        if category != 'extensions':
            self.verify_brew_provider(initialize=True)
        self.reconcile([category])
        installed = self.inventory(category)
        for name in requested:
            name = name.lower() if category == 'extensions' else name
            if installed_name(name, installed):
                self.say('Already installed: ' + name)
                continue
            if (category == 'casks' and name == 'visual-studio-code'
                    and any(candidate.exists() for candidate in (
                        Path('/Applications/Visual Studio Code.app'),
                        self.home / 'Applications/Visual Studio Code.app'))):
                self.say('Keep existing VS Code application (not managed by this installer).')
                continue
            self.say('Install ' + category + ': ' + name)
            if self.dry_run:
                continue
            pending = {'category': category, 'name': name}
            self.state['tools']['pending'].append(pending)
            self.save()
            try:
                if category == 'extensions':
                    self.run([self.code, '--install-extension', name])
                else:
                    flag = '--formula' if category == 'formulae' else '--cask'
                    self.run([self.brew, 'install', flag, name], env={
                        **os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1',
                        'HOMEBREW_NO_INSTALL_CLEANUP': '1'})
            finally:
                # Some installers return nonzero after successfully installing a package.
                # Keep the pending journal if inventory itself fails; a rerun recovers it.
                after = self.inventory(category)
                if installed_name(name, after) and name not in self.state['tools'][category]:
                    self.state['tools'][category].append(name)
                self.state['tools']['pending'].remove(pending)
                self.save()
                installed = after

    def install_tools(self):
        if platform.system() not in ('Darwin', 'Linux') or not self.brew:
            raise RuntimeError('Full install requires macOS/Linux with Homebrew. Use bootstrap or --configs-only.')
        self.verify_brew_provider(initialize=True)
        manifest = json.loads((self.repo / 'packages.json').read_text())
        self.add_tools('formulae', manifest.get('formulae', []))
        if platform.system() == 'Darwin':
            casks = manifest.get('casks', [])
            if self.no_vscode:
                casks = [name for name in casks if name != 'visual-studio-code']
            self.add_tools('casks', casks)
        elif manifest.get('casks'):
            self.say('Linux: macOS applications (casks) are skipped.')
        self.code = shutil.which('code') or self.code
        if not self.code and platform.system() == 'Darwin':
            candidate = Path('/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code')
            if candidate.is_file():
                self.code = str(candidate)
        try:
            import rust_setup
        except ImportError:
            rust_setup = None
        if rust_setup:
            self.say(rust_setup.setup(self.repo, self.home, self.state, self.save, self.run, dry_run=self.dry_run))
        if not self.no_vscode:
            if self.code:
                self.add_tools('extensions', manifest.get('vscode_extensions', []))
            else:
                self.problem('VS Code CLI is unavailable: settings can be linked, but extensions are skipped.')

    def purge_tools(self):
        # Check before Rust removal too: its executables come from the same Brew.
        if self.has_brew_ownership():
            self.verify_brew_provider()
        try:
            import rust_setup
        except ImportError:
            rust_setup = None
        if rust_setup:
            self.say(rust_setup.purge(self.home, self.state, self.save, self.run, dry_run=self.dry_run))
        for category in ('extensions', 'casks', 'formulae'):
            if self.no_vscode and category == 'extensions':
                continue
            if category == 'casks' and platform.system() != 'Darwin':
                continue
            if not self.state['tools'][category] and not any(
                    p['category'] == category for p in self.state['tools']['pending']):
                continue
            try:
                self.reconcile([category])
                installed = self.inventory(category)
            except (RuntimeError, subprocess.CalledProcessError) as error:
                self.problem(str(error))
                continue
            # Reverse order removes dependent roots before their prerequisites where possible.
            for name in list(reversed(self.state['tools'][category])):
                if self.no_vscode and category == 'casks' and name == 'visual-studio-code':
                    continue
                if not installed_name(name, installed):
                    if not self.dry_run:
                        self.state['tools'][category].remove(name)
                        self.save()
                    continue
                self.say('Uninstall owned ' + category + ': ' + name)
                if self.dry_run:
                    continue
                try:
                    if category == 'extensions':
                        self.run([self.code, '--uninstall-extension', name])
                    else:
                        flag = '--formula' if category == 'formulae' else '--cask'
                        self.run([self.brew, 'uninstall', flag, name], env={
                            **os.environ, 'HOMEBREW_NO_INSTALL_CLEANUP': '1',
                            'HOMEBREW_NO_AUTOREMOVE': '1'})
                except subprocess.CalledProcessError as error:
                    self.problem('Could not remove ' + name + '; ownership retained. ' +
                                 (error.stderr or '').strip())
                finally:
                    try:
                        after = self.inventory(category)
                    except (RuntimeError, subprocess.CalledProcessError) as error:
                        self.problem('Cannot verify removal of ' + name + ': ' + str(error))
                    else:
                        if not installed_name(name, after):
                            self.state['tools'][category].remove(name)
                            self.save()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall'])
    parser.add_argument('--dry-run', action='store_true', help='Show changes without writing files or installing tools')
    parser.add_argument('--configs-only', action='store_true', help='Only link configuration; no package/tool actions')
    parser.add_argument('--no-vscode', action='store_true', help='Skip VS Code settings, extensions and application')
    parser.add_argument('--purge-tools', action='store_true', help='Uninstall only tools recorded as added by this installer')
    parser.add_argument('--target-home', type=Path, default=Path.home(), help='Isolated home for config-only testing')
    args = parser.parse_args(argv)
    if args.action == 'install' and args.purge_tools:
        parser.error('--purge-tools is only available for uninstall')
    if args.action == 'uninstall' and args.configs_only:
        parser.error('--configs-only is only available for install; uninstall keeps tools by default')
    if args.target_home.resolve() != Path.home().resolve():
        if args.action == 'install' and not args.configs_only:
            parser.error('--target-home requires --configs-only for install')
        if args.purge_tools:
            parser.error('--purge-tools is forbidden with an alternative --target-home')
    manager = Manager(Path(__file__).resolve().parent.parent, args.target_home,
                      args.dry_run, args.no_vscode)
    try:
        with manager.locked(create=args.action == 'install'):
            if args.action == 'install':
                if not args.configs_only:
                    manager.install_tools()
                manager.configs()
            else:
                manager.restore_configs()
                if args.purge_tools:
                    manager.purge_tools()
        if manager.problems:
            print('Some items were kept or skipped; see warnings above. State/backups: ' + str(manager.directory))
            return 1
        print('Done.' + (' No changes made.' if args.dry_run else ''))
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.strip(), file=sys.stderr)
        print('Progress and backups are retained; fix the issue and rerun.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
