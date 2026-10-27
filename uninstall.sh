#!/usr/bin/env bash
set -eu
if ! command -v brew >/dev/null 2>&1; then
  for DOTFILES_BREW_PREFIX in /opt/homebrew /home/linuxbrew/.linuxbrew "$HOME/.linuxbrew" /usr/local; do
    if [ -x "$DOTFILES_BREW_PREFIX/bin/brew" ]; then
      export PATH="$DOTFILES_BREW_PREFIX/bin:$DOTFILES_BREW_PREFIX/sbin:$PATH"
      break
    fi
  done
fi
DOTFILES_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3 is required to restore the saved configuration.' >&2
  exit 1
fi
exec python3 "$DOTFILES_ROOT/scripts/manage.py" uninstall "$@"
