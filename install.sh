#!/usr/bin/env bash
# Install the hwpx-editing skill into an AI agent's skills directory.
#
# Usage:
#   ./install.sh <agent> [<agent> ...]   copy the skill into each agent's dir
#   ./install.sh all                      install into every known agent
#   ./install.sh --link <agent>           symlink instead of copy (stays in sync)
#
# Agents: claude  codex  cursor  gemini  openclaw
set -euo pipefail

SKILL_NAME="hwpx-editing"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/skills/$SKILL_NAME"

LINK=0
AGENTS=()
for arg in "$@"; do
  case "$arg" in
    --link) LINK=1 ;;
    all) AGENTS=(claude codex cursor gemini openclaw) ;;
    claude|codex|cursor|gemini|openclaw) AGENTS+=("$arg") ;;
    -h|--help|"")
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown agent: $arg (try: claude codex cursor gemini openclaw all)"; exit 1 ;;
  esac
done

if [ ${#AGENTS[@]} -eq 0 ]; then
  echo "Nothing to do. Example:  ./install.sh claude"; exit 1
fi

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "ERROR: $SRC/SKILL.md not found — run this from the repo root."; exit 1
fi

dest_dir_for() {
  case "$1" in
    claude)   echo "$HOME/.claude/skills" ;;
    codex)    echo "$HOME/.codex/skills" ;;
    cursor)   echo "$PWD/.cursor/skills" ;;       # project-scoped
    gemini)   echo "$HOME/.gemini/skills" ;;
    openclaw) echo "$HOME/.openclaw/skills" ;;
  esac
}

for agent in "${AGENTS[@]}"; do
  base="$(dest_dir_for "$agent")"
  dest="$base/$SKILL_NAME"
  mkdir -p "$base"
  rm -rf "$dest"
  if [ "$LINK" -eq 1 ]; then
    ln -s "$SRC" "$dest"
    echo "linked  $agent  →  $dest  ->  $SRC"
  else
    cp -r "$SRC" "$dest"
    echo "copied  $agent  →  $dest"
  fi
done

echo
echo "Done. Restart your agent (or start a new session)."
echo "Claude Code: type /skills and look for '$SKILL_NAME'."
echo "Python dep:  pip install lxml"
echo "Sanity check: python \"$SRC/scripts/selftest.py\""
