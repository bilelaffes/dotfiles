# Shared by login and interactive shells. Re-sourcing must not duplicate PATH.
_personal_path_prepend() {
    [[ -d $1 ]] || return 0
    case ":${PATH-}:" in
        *":$1:"*) ;;
        *) PATH="$1${PATH:+:$PATH}" ;;
    esac
}

_personal_brew=$(type -P brew)
if [[ -z $_personal_brew ]]; then
    for _personal_candidate in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
        if [[ -x $_personal_candidate ]]; then
            _personal_brew=$_personal_candidate
            break
        fi
    done
fi
_personal_brew_prefix=
if [[ -n $_personal_brew ]]; then
    _personal_brew_prefix=$("$_personal_brew" --prefix 2>/dev/null)
    if [[ -n $_personal_brew_prefix ]]; then
        if [[ ${HOMEBREW_PREFIX-} != "$_personal_brew_prefix" ]]; then
            eval "$("$_personal_brew" shellenv)"
        fi
        _personal_path_prepend "$_personal_brew_prefix/sbin"
        _personal_path_prepend "$_personal_brew_prefix/bin"
        _personal_path_prepend "$_personal_brew_prefix/opt/helm@3/bin"
    fi
fi

# Respect an existing Rust installation. The bootstrap may install Rust privately.
if [[ -r "$HOME/.cargo/env" ]]; then
    source "$HOME/.cargo/env"
elif [[ -r "$HOME/.local/share/dotfiles/rust/cargo/env" ]]; then
    export CARGO_HOME="$HOME/.local/share/dotfiles/rust/cargo"
    export RUSTUP_HOME="$HOME/.local/share/dotfiles/rust/rustup"
    source "$CARGO_HOME/env"
fi
_personal_path_prepend "${CARGO_HOME:-$HOME/.cargo}/bin"
_personal_path_prepend "$HOME/.docker/bin"
_personal_path_prepend "$HOME/go/bin"
_personal_path_prepend "$HOME/.local/bin"
export PATH

if [[ -z ${EDITOR-} ]]; then
    if command -v code >/dev/null 2>&1; then
        export EDITOR='code --wait'
    else
        export EDITOR=vim
    fi
fi
unset _personal_brew _personal_candidate
unset -f _personal_path_prepend
