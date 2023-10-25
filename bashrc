#################################################################
# .bashrc
# @Autor : Bilel AFFES <bilelaffes@hotmail.com>
# @Version 1.0
#################################################################

### .bashrc : begin

#auto-completion command git
source ~/.git-completion.bash
source ~/.git-prompt.sh

#auto-completion command makefile
complete -W "\`grep -oE '^[a-zA-Z0-9_.-]+:([^=]|$)' ?akefile | sed 's/[^a-zA-Z0-9_.-]*$//'\`" make

# when scp, don't pollute my STDIN
if [ -z "$PS1" ]; then
    return;
fi

#-----------------------------------------------------------------
# Env Vars :
#-----------------------------------------------------------------

### OS Type :
export OS_TYPE=`uname`

### LS colors :
export LSCOLORS=ExGxBxFxCxDxDxabagacad

### Editor par defaut
export EDITOR='code --wait'

##
# Your previous /Users/bilel/.bash_profile file was backed up as /Users/bilel/.bash_profile.macports-saved_2019-04-28_at_15:54:12
##

# MacPorts Installer addition on 2019-04-28_at_15:54:12: adding an appropriate PATH variable for use with MacPorts.
export PATH="/opt/local/bin:/opt/local/sbin:/usr/local/go/bin:$PATH"
# Finished adapting your PATH environment variable for use with MacPorts.

#-----------------------------------------------------------------
# Symlinks :
#-----------------------------------------------------------------

if [[ ! -f "/usr/local/bin/code" ]]; then
	ln -s "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code" /usr/local/bin/code
fi

#-----------------------------------------------------------------
# Configs :
#-----------------------------------------------------------------

### Default creating modes
umask 022 #644 for files #755 for repositories

#-----------------------------------------------------------------
# Colors definitions ( taken from Color Bash Prompt HowTo )
#-----------------------------------------------------------------

# Reset Couleur 
Reset_Color='\e[0m'       # Text Reset

# Regular Colors
Black='\e[0;30m'        # Black
Red='\e[0;31m'          # Red
Green='\e[0;32m'        # Green
Yellow='\e[0;33m'       # Yellow
Blue='\e[0;34m'         # Blue
Purple='\e[0;35m'       # Purple
Cyan='\e[0;36m'         # Cyan
White='\e[0;37m'        # White

# Bold
BBlack='\e[1;30m'       # Black
BRed='\e[1;31m'         # Red
BGreen='\e[1;32m'       # Green
BYellow='\e[1;33m'      # Yellow
BBlue='\e[1;34m'        # Blue
BPurple='\e[1;35m'      # Purple
BCyan='\e[1;36m'        # Cyan
BWhite='\e[1;37m'       # White

# Underline
UBlack='\e[4;30m'       # Black
URed='\e[4;31m'         # Red
UGreen='\e[4;32m'       # Green
UYellow='\e[4;33m'      # Yellow
UBlue='\e[4;34m'        # Blue
UPurple='\e[4;35m'      # Purple
UCyan='\e[4;36m'        # Cyan
UWhite='\e[4;37m'       # White

# Background
On_Black='\e[40m'       # Black
On_Red='\e[41m'         # Red
On_Green='\e[42m'       # Green
On_Yellow='\e[43m'      # Yellow
On_Blue='\e[44m'        # Blue
On_Purple='\e[45m'      # Purple
On_Cyan='\e[46m'        # Cyan
On_White='\e[47m'       # White

# High Intensity
IBlack='\e[0;90m'       # Black
IRed='\e[0;91m'         # Red
IGreen='\e[0;92m'       # Green
IYellow='\e[0;93m'      # Yellow
IBlue='\e[0;94m'        # Blue
IPurple='\e[0;95m'      # Purple
ICyan='\e[0;96m'        # Cyan
IWhite='\e[0;97m'       # White

# Bold High Intensity
BIBlack='\e[1;90m'      # Black
BIRed='\e[1;91m'        # Red
BIGreen='\e[1;92m'      # Green
BIYellow='\e[1;93m'     # Yellow
BIBlue='\e[1;94m'       # Blue
BIPurple='\e[1;95m'     # Purple
BICyan='\e[1;96m'       # Cyan
BIWhite='\e[1;97m'      # White

# High Intensity backgrounds
On_IBlack='\e[0;100m'   # Black
On_IRed='\e[0;101m'     # Red
On_IGreen='\e[0;102m'   # Green
On_IYellow='\e[0;103m'  # Yellow
On_IBlue='\e[0;104m'    # Blue
On_IPurple='\e[0;105m'  # Purple
On_ICyan='\e[0;106m'    # Cyan
On_IWhite='\e[0;107m'   # White

#-----------------------------------------------------------------
# Welcome message 
#-----------------------------------------------------------------

Welcome_Date=`date`
echo "********************************************************************************"
echo "********    BashByWaye - $Welcome_Date - السلام عليكم    *******"
echo "********************************************************************************"

#-----------------------------------------------------------------
# Prompt Configuration 
#-----------------------------------------------------------------

# Sometimes I need to return to default prompt
#export PS1='\h:\w\$ '

# Generate PS1 after each command
export PROMPT_COMMAND=__prompt_command

# function to generate PS1 after each command
# prompt is formed from 3 lines :
# 1- last return line : return code + symbol
# 2- default line : current hour + user name + workspace
# 3- scan line
function __prompt_command() {

    # Last command return
    local Last_Return="$?"

    # Return Symbol initialization
    if [[ $Last_Return == 0 ]]; then
	Last_Proc_Return_Symbol="\[$BGreen\]\342\234\223"; #Green check
    else
	Last_Proc_Return_Symbol="\[$BRed\]\342\234\227"; #Red cross
    fi

    # Return line initialization
    Prompt_Last_Proc_Return_Line="\[$Reset_Color\]$Last_Return : $Last_Proc_Return_Symbol"

    # default line initialization
    Prompt_Default_Line="\[$BCyan\][\A] \u:\[$BYellow\]\w \[$BRed\]$(__git_ps1 "(%s)")\[$Reset_Color\]"

    # scan line initialization
    Prompt_Scan_Line="→ "

    # go combine it !
    PS1="$Prompt_Last_Proc_Return_Line
$Prompt_Default_Line
$Prompt_Scan_Line"
}

#-----------------------------------------------------------------
# Alias definition
#-----------------------------------------------------------------

# Shorcuts
if [[ $OS_TYPE == "Linux" ]]; then
    alias ls="ls -G --color=auto"
else
    alias ls="ls -G"
fi

alias ll='ls -l'
alias la='ls -A'
alias l='ls -CF'
alias g='grep -i'  #Faire un grep non sensible à la casse
alias f='find . -iname' # Faire une recherche non caseSensitive dans .

# Graphical emacs for MAC OS

if [[ $OS_TYPE == 'Darwin' ]]; then
    alias emacs='open -a emacs'
fi

# garder un oeil sur les erreurs php et apache :
if [ -f ${PHP_ERROR_FILE} ]; then
    alias phperror="tail -f ${PHP_ERROR_FILE}"
fi

if [ -f ${APACHE_LOG_FILE} ]; then
    alias apachelogs="tail -f ${APACHE_LOG_FILE}"
fi


export HISTCONTROL=ignoredups # Ignores dupes in the history
shopt -s checkwinsize # After each command, checks the windows size and changes lines and columns

# bash completion settings (actually, these are readline settings)
bind "set completion-ignore-case on" # note: bind is used instead of setting these in .inputrc.  This ignores case in bash completion
bind "set bell-style none" # No bell, because it's damn annoying
bind "set show-all-if-ambiguous On" # this allows you to automatically show completion without double tab-ing

### .bashrc : end

