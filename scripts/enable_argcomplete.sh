#!/usr/bin/env bash
# Enable argcomplete tab-completion for os-node / os-cli on bash, zsh, and fish.
# Usage:
#   bash  : source scripts/enable_argcomplete.sh
#   zsh   : source scripts/enable_argcomplete.sh
#   fish  : (run with --fish flag) bash scripts/enable_argcomplete.sh --fish
#   auto-apply to current shell profile (bash/zsh): bash scripts/enable_argcomplete.sh --install
#
# Requires: pip install argcomplete

set -euo pipefail

COMMAND="${1:-os-node}"
INSTALL_MODE=0
FISH_MODE=0

for arg in "$@"; do
    case "$arg" in
        --install) INSTALL_MODE=1 ;;
        --fish)    FISH_MODE=1 ;;
        --help|-h)
            echo "Usage: $0 [<command-name>] [--install] [--fish]"
            echo "  <command-name>  CLI entry point (default: os-node)"
            echo "  --install       Append activation line to shell profile (~/.bashrc or ~/.zshrc)"
            echo "  --fish          Output fish shell config and install to ~/.config/fish/completions/"
            exit 0 ;;
    esac
done

# ── Verify argcomplete is installed ──────────────────────────────────────────
if ! command -v register-python-argcomplete &>/dev/null; then
    echo "ERROR: register-python-argcomplete not found." >&2
    echo "Install with: pip install argcomplete" >&2
    exit 1
fi

# ── Fish shell ────────────────────────────────────────────────────────────────
if [[ "$FISH_MODE" -eq 1 ]]; then
    FISH_DIR="${HOME}/.config/fish/completions"
    mkdir -p "$FISH_DIR"
    register-python-argcomplete --shell fish "$COMMAND" > "$FISH_DIR/${COMMAND}.fish"
    echo "Fish completion installed: $FISH_DIR/${COMMAND}.fish"
    echo "Restart fish or run: source $FISH_DIR/${COMMAND}.fish"
    exit 0
fi

# ── Bash / Zsh ────────────────────────────────────────────────────────────────
ACTIVATION_LINE='eval "$(register-python-argcomplete '"$COMMAND"')"'

if [[ "${SHELL:-}" == *zsh* || -n "${ZSH_VERSION:-}" ]]; then
    SHELL_NAME="zsh"
    PROFILE="${ZDOTDIR:-$HOME}/.zshrc"
    # zsh needs bashcompinit for argcomplete
    ACTIVATION_LINE='autoload -U bashcompinit && bashcompinit && eval "$(register-python-argcomplete '"$COMMAND"')"'
else
    SHELL_NAME="bash"
    PROFILE="${HOME}/.bashrc"
fi

if [[ "$INSTALL_MODE" -eq 1 ]]; then
    if grep -qF "register-python-argcomplete $COMMAND" "$PROFILE" 2>/dev/null; then
        echo "Argcomplete activation line already present in $PROFILE"
    else
        printf '\n# OpenSynaptic CLI tab-completion\n%s\n' "$ACTIVATION_LINE" >> "$PROFILE"
        echo "Argcomplete enabled for '$COMMAND' in $PROFILE ($SHELL_NAME)"
        echo "Run 'source $PROFILE' or restart your shell to apply."
    fi
else
    # Print the line so the user can evaluate it manually or via source
    echo "# Run the following to enable completion in this shell session:"
    echo "$ACTIVATION_LINE"
    echo ""
    echo "# To persist across sessions, run:"
    echo "  $0 $COMMAND --install"
fi
