command -v kubectl >/dev/null 2>&1 && alias k=kubectl

# Modern bash-completion and generated completions require a recent Bash.
(( BASH_VERSINFO[0] >= 5 )) || return 0

if ! declare -F _init_completion >/dev/null && ! declare -F _comp_initialize >/dev/null; then
    for _personal_completion_file in \
        "${_personal_brew_prefix:+$_personal_brew_prefix/etc/profile.d/bash_completion.sh}" \
        "${_personal_brew_prefix:+$_personal_brew_prefix/opt/bash-completion@2/etc/profile.d/bash_completion.sh}" \
        /usr/share/bash-completion/bash_completion \
        /etc/bash_completion; do
        if [[ -r $_personal_completion_file ]]; then
            source "$_personal_completion_file"
            break
        fi
    done
fi

# Git is sometimes shipped separately from the general completion package.
if command -v git >/dev/null 2>&1 && ! complete -p git >/dev/null 2>&1; then
    for _personal_completion_file in \
        "${_personal_brew_prefix:+$_personal_brew_prefix/etc/bash_completion.d/git-completion.bash}" \
        "${_personal_brew_prefix:+$_personal_brew_prefix/share/bash-completion/completions/git}" \
        "${_personal_brew_prefix:+$_personal_brew_prefix/share/git-core/contrib/completion/git-completion.bash}" \
        /usr/local/share/bash-completion/completions/git \
        /usr/share/bash-completion/completions/git \
        /usr/share/git/completion/git-completion.bash \
        /usr/share/git-core/contrib/completion/git-completion.bash \
        /Library/Developer/CommandLineTools/usr/share/git-core/git-completion.bash; do
        if [[ -r $_personal_completion_file ]]; then
            source "$_personal_completion_file"
            break
        fi
    done
fi

for _personal_cli in kubectl helm helmfile docker k9s; do
    if command -v "$_personal_cli" >/dev/null 2>&1; then
        source <("$_personal_cli" completion bash 2>/dev/null)
    fi
done
if declare -F __start_kubectl >/dev/null; then
    complete -o default -F __start_kubectl k
fi

# These CLIs implement Bash's external completer protocol directly.
for _personal_cli in terraform terragrunt; do
    if command -v "$_personal_cli" >/dev/null 2>&1; then
        complete -o nospace -C "$_personal_cli" "$_personal_cli"
    fi
done
if command -v aws_completer >/dev/null 2>&1; then
    complete -C aws_completer aws
fi

if command -v rustup >/dev/null 2>&1; then
    source <(rustup completions bash 2>/dev/null)
    source <(rustup completions bash cargo 2>/dev/null)
fi

# Go has no native completion generator. Read local help without loading packages.
_personal_go_completion() {
    local cur=${COMP_WORDS[COMP_CWORD]} words
    local -a topic=()
    COMPREPLY=()
    if (( COMP_CWORD == 1 )); then
        :
    elif (( COMP_CWORD == 2 )) &&
         [[ ${COMP_WORDS[1]} == mod || ${COMP_WORDS[1]} == work ]]; then
        topic=("${COMP_WORDS[1]}")
    else
        return 0
    fi
    words=$(
        GOTOOLCHAIN=local GOPROXY=off GOSUMDB=off \
            command go help "${topic[@]}" 2>/dev/null |
            awk '
                /^The commands are:$/ {printing=1; next}
                printing && /^Use / {exit}
                printing && NF {print $1}
            '
    )
    (( COMP_CWORD == 1 )) && words+=$'\nhelp'
    mapfile -t COMPREPLY < <(compgen -W "$words" -- "$cur")
}
if command -v go >/dev/null 2>&1; then
    complete -o bashdefault -o default -F _personal_go_completion go
fi

# Ctrl-R: history, Ctrl-T: files, Alt-C: directories. Support older distro fzf too.
if command -v fzf >/dev/null 2>&1; then
    _personal_fzf_init=$(fzf --bash 2>/dev/null)
    if [[ -n $_personal_fzf_init ]]; then
        eval "$_personal_fzf_init"
    else
        for _personal_fzf_dir in \
            "${_personal_brew_prefix:+$_personal_brew_prefix/opt/fzf/shell}" \
            /usr/share/fzf /usr/share/doc/fzf/examples; do
            if [[ -r $_personal_fzf_dir/key-bindings.bash ]]; then
                [[ -r $_personal_fzf_dir/completion.bash ]] && source "$_personal_fzf_dir/completion.bash"
                source "$_personal_fzf_dir/key-bindings.bash"
                break
            fi
        done
    fi
fi
unset _personal_cli _personal_completion_file _personal_fzf_init _personal_fzf_dir
