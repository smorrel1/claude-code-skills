#!/usr/bin/env bash
# One-command installer for smorrel1/claude-code-skills
#   All skills:   curl -fsSL https://smorrel1.github.io/claude-code-skills/install.sh | bash
#   Pick skills:  curl -fsSL https://smorrel1.github.io/claude-code-skills/install.sh | bash -s -- interview-transcript humanizer
# Non-destructive: clones to ~/claude-code-skills and symlinks into ~/.claude/skills,
# skipping any skill name that already exists there.
set -euo pipefail
REPO_DIR="$HOME/claude-code-skills"
SKILLS_DIR="$HOME/.claude/skills"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --ff-only
else
  git clone --depth 1 https://github.com/smorrel1/claude-code-skills "$REPO_DIR"
fi
mkdir -p "$SKILLS_DIR"
installed=0; skipped=0
for dir in "$REPO_DIR"/*/; do
  name="$(basename "$dir")"
  [ -f "$dir/SKILL.md" ] || continue
  if [ "$#" -gt 0 ]; then
    case " $* " in *" $name "*) ;; *) continue;; esac
  fi
  if [ -e "$SKILLS_DIR/$name" ]; then
    skipped=$((skipped+1)); continue
  fi
  ln -s "$REPO_DIR/$name" "$SKILLS_DIR/$name"
  echo "installed: $name"
  installed=$((installed+1))
done
echo "Done. $installed installed, $skipped already present. Restart Claude Code to load them."
