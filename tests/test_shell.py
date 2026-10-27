"""Shell syntax and prompt behaviour, without loading the real home configuration."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ShellTests(unittest.TestCase):
    def test_shell_syntax_on_available_bash_versions(self):
        candidates = ['/bin/bash', '/opt/homebrew/bin/bash', '/usr/local/bin/bash',
                      '/home/linuxbrew/.linuxbrew/bin/bash', shutil.which('bash')]
        scripts = [ROOT / name for name in ('bootstrap.sh', 'install.sh', 'uninstall.sh',
                                            'shell/bashrc', 'shell/bash_profile')]
        scripts += list((ROOT / 'shell/config').glob('*.bash'))
        for bash in dict.fromkeys(candidates):
            if bash and Path(bash).is_file():
                for script in scripts:
                    with self.subTest(bash=bash, script=script.name):
                        subprocess.run([bash, '-n', str(script)], check=True, capture_output=True)

    def test_noninteractive_rc_is_silent(self):
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c',
                                 'source "$1"; printf marker', 'test', str(ROOT / 'shell/bashrc')],
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, 'marker')
        self.assertEqual(result.stderr, '')

    def test_legacy_exported_prompt_function_does_not_survive_migration(self):
        script = '''
PROMPT_COMMAND=__prompt_command
export PROMPT_COMMAND
source "$1"
[[ "${PROMPT_COMMAND[*]}" != *"__prompt_command"* ]] || exit 10
[[ "${PROMPT_COMMAND[*]}" == *"__personal_prompt_command"* ]] || exit 11
'''
        for bash in ('/bin/bash', '/opt/homebrew/bin/bash'):
            if Path(bash).is_file():
                subprocess.run([bash, '--noprofile', '--norc', '-c', script,
                                'test', str(ROOT / 'shell/config/prompt.bash')],
                               check=True, capture_output=True, cwd='/tmp')

    def test_prompt_keeps_exit_status_and_valid_existing_hook(self):
        script = '''
_existing_hook() { :; }
PROMPT_COMMAND=_existing_hook
source "$1"
false
__personal_prompt_command
status=$?
[[ $status == 1 && $PS1 == *"1 :"* ]] || exit 10
[[ "${PROMPT_COMMAND[*]}" == *"_existing_hook"* ]] || exit 11
true
__personal_prompt_command
[[ $PS1 == *"0 :"* ]] || exit 12
'''
        subprocess.run(['/bin/bash', '--noprofile', '--norc', '-c', script,
                        'test', str(ROOT / 'shell/config/prompt.bash')], check=True,
                       capture_output=True, cwd='/tmp')


if __name__ == '__main__':
    unittest.main()
