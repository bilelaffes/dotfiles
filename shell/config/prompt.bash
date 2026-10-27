# Use the Git prompt shipped with Git when available.
if ! declare -F __git_ps1 >/dev/null; then
    for _personal_git_prompt in \
        "${_personal_brew_prefix:+$_personal_brew_prefix/etc/bash_completion.d/git-prompt.sh}" \
        "${_personal_brew_prefix:+$_personal_brew_prefix/share/git-core/contrib/completion/git-prompt.sh}" \
        /usr/local/share/git-core/contrib/completion/git-prompt.sh \
        /usr/share/git-core/contrib/completion/git-prompt.sh \
        /usr/share/git/completion/git-prompt.sh \
        /usr/lib/git-core/git-sh-prompt \
        /etc/bash_completion.d/git-prompt \
        /Library/Developer/CommandLineTools/usr/share/git-core/git-prompt.sh; do
        if [[ -r $_personal_git_prompt ]]; then
            source "$_personal_git_prompt"
            break
        fi
    done
fi
unset _personal_git_prompt

__personal_prompt_command() {
    local last_status=$? symbol color branch
    if (( last_status == 0 )); then
        symbol='✓'
        color='\[\e[1;32m\]'
    else
        symbol='✗'
        color='\[\e[1;31m\]'
    fi

    __personal_git_branch=
    if declare -F __git_ps1 >/dev/null; then
        __personal_git_branch=$(__git_ps1 ' (%s)')
    elif command -v git >/dev/null 2>&1; then
        branch=$(GIT_OPTIONAL_LOCKS=0 command git symbolic-ref --quiet --short HEAD 2>/dev/null) ||
            branch=$(GIT_OPTIONAL_LOCKS=0 command git rev-parse --short HEAD 2>/dev/null)
        [[ -n $branch ]] && __personal_git_branch=" ($branch)"
    fi

    # Expand the branch variable at prompt rendering, never as shell source.
    PS1='\[\e[0m\]'"$last_status : $color$symbol"'\[\e[0m\]\n'
    PS1+='\[\e[1;36m\][\A] \u:\[\e[1;33m\]\w\[\e[1;31m\]${__personal_git_branch}\[\e[0m\]\n→ '
    return "$last_status"
}

# Older personal configs exported this hook without exporting its function.
# Discard that specific stale hook when a new shell inherits only its name.
if ! command -v __prompt_command >/dev/null 2>&1; then
    if (( BASH_VERSINFO[0] >= 5 )); then
        _personal_prompt_hooks=()
        for _personal_prompt_hook in "${PROMPT_COMMAND[@]}"; do
            [[ $_personal_prompt_hook == __prompt_command ]] ||
                _personal_prompt_hooks+=("$_personal_prompt_hook")
        done
        PROMPT_COMMAND=("${_personal_prompt_hooks[@]}")
        unset _personal_prompt_hooks _personal_prompt_hook
    elif [[ ${PROMPT_COMMAND-} == __prompt_command ]]; then
        unset PROMPT_COMMAND
    fi
fi

# Preserve terminal integrations and keep our status capture first.
if (( BASH_VERSINFO[0] >= 5 )); then
    _personal_prompt_present=
    for _personal_prompt_hook in "${PROMPT_COMMAND[@]}"; do
        [[ $_personal_prompt_hook == __personal_prompt_command ]] && _personal_prompt_present=1
    done
    if [[ -z $_personal_prompt_present ]]; then
        PROMPT_COMMAND=(__personal_prompt_command "${PROMPT_COMMAND[@]}")
    fi
    unset _personal_prompt_present _personal_prompt_hook
else
    case ${PROMPT_COMMAND-} in
        __personal_prompt_command|__personal_prompt_command';'*) ;;
        *) PROMPT_COMMAND="__personal_prompt_command${PROMPT_COMMAND:+; $PROMPT_COMMAND}" ;;
    esac
fi
