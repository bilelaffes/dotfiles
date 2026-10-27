#!/bin/bash
# Install prerequisites, then the personal environment. Supports macOS and Linux.
set -euo pipefail
DOTFILES_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

# Preview and isolated/config-only operations must never bootstrap the machine.
for argument in "$@"; do
    case "$argument" in
        --help|-h|--dry-run|--configs-only|--target-home|--target-home=*)
            exec "$DOTFILES_REPO/install.sh" "$@"
            ;;
    esac
done

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) printf '%s\n' 'This environment supports macOS and Linux.' >&2; exit 1 ;;
esac

find_brew() {
    command -v brew 2>/dev/null && return 0
    local candidate
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew "$HOME/.linuxbrew/bin/brew"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

if ! DOTFILES_BREW=$(find_brew); then
    command -v curl >/dev/null || {
        printf '%s\n' 'Install curl and the OS build tools first (see README.md).' >&2
        exit 1
    }
    printf '%s\n' 'Installing Homebrew from its official installer. It may request administrator access.'
    DOTFILES_INSTALLER=$(mktemp "${TMPDIR:-/tmp}/dotfiles-homebrew.XXXXXX")
    trap 'rm -f -- "$DOTFILES_INSTALLER"' EXIT
    curl --fail --show-error --silent --location --proto '=https' --tlsv1.2 \
        https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh \
        -o "$DOTFILES_INSTALLER"
    /bin/bash "$DOTFILES_INSTALLER"
    rm -f -- "$DOTFILES_INSTALLER"
    trap - EXIT
    DOTFILES_BREW=$(find_brew)
fi

eval "$("$DOTFILES_BREW" shellenv)"
if ! command -v python3 >/dev/null 2>&1 ||
   ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
    HOMEBREW_NO_INSTALL_CLEANUP=1 "$DOTFILES_BREW" install python
fi

# Homebrew and Python are prerequisites, kept during environment removal.
exec "$DOTFILES_REPO/install.sh" "$@"
