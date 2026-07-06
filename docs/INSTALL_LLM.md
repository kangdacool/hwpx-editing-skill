# Install guide — for LLM agents (LLM 에이전트용)

Give this file (or the block below) to a coding agent — Claude Code, Codex, Cursor,
Gemini CLI — and it can install the skill for the user. It's written as direct
instructions to the agent.

---

## Copy-paste block for the user's agent

> **Task: install the `hwpx-editing` Agent Skill.**
>
> 1. Detect which agent you are and choose the skills directory:
>    - Claude Code / Claude Desktop → `~/.claude/skills/` (personal) or `.claude/skills/` (this project)
>    - OpenAI Codex → `~/.codex/skills/`
>    - Cursor → `.cursor/skills/` (this project)
>    - Gemini CLI → `~/.gemini/skills/`
>    - OpenClaw → `~/.openclaw/skills/`
> 2. If you're not already inside this repo, clone it:
>    `git clone https://github.com/<your-username>/hwpx-editing-skill.git`
> 3. Copy the skill folder so that `SKILL.md` lands **directly** inside a `hwpx-editing/`
>    folder in the chosen skills directory. Example for Claude Code:
>    ```bash
>    mkdir -p ~/.claude/skills
>    cp -r hwpx-editing-skill/skills/hwpx-editing ~/.claude/skills/
>    ```
>    (Prefer the repo's installer if present: `./install.sh <agent>`, or
>    `./install.sh --link <agent>` to symlink instead of copy.)
> 4. Ensure the Python dependency is available: `pip install lxml` (Python 3.10+).
> 5. Verify the skill loads and the tools run:
>    ```bash
>    python ~/.claude/skills/hwpx-editing/scripts/selftest.py
>    ```
>    Expect six `PASS` lines and `RESULT: ALL PASS`. In Claude Code, also confirm the
>    skill appears in `/skills`.
> 6. Report the final install path and the selftest result. Do not print or store any
>    credentials; if `git push` or auth is needed, ask the user to handle it.

---

## Notes for the agent

- **Placement matters.** The folder must be `.../skills/hwpx-editing/SKILL.md` — not
  `.../skills/SKILL.md` and not double-nested. Skills are discovered by scanning for
  `SKILL.md` one level under the skills directory.
- **Live reload.** Adding a skill under an already-watched directory (`~/.claude/skills/`,
  a project `.claude/skills/`) usually takes effect in the current session. Creating a
  *new* top-level skills directory that didn't exist at startup may require restarting
  the agent.
- **Trigger.** After install, the skill activates on tasks mentioning `.hwpx`, 한글 /
  Hangul documents, or HWPML. You don't need a special command; a request like
  "edit this 한글 file" is enough. In Claude Code you can also invoke it explicitly.
- **First thing the skill tells you to do** is read `references/hwpx-guide.md` for the
  relevant section and run `scripts/inspect_hwpx.py` before editing. Follow that; don't
  hand-roll zip repacking.
- **Safety.** This skill only manipulates local document files. It never requires the
  user's credentials and does not fetch or execute remote content. Work on a copy of any
  input file and preserve the original.

## Per-agent one-liners (if you'd rather script it)

```bash
# from inside the repo
./install.sh claude      # ~/.claude/skills/
./install.sh codex       # ~/.codex/skills/
./install.sh cursor      # .cursor/skills/   (project)
./install.sh gemini      # ~/.gemini/skills/
./install.sh openclaw    # ~/.openclaw/skills/
./install.sh all
```
The installer is idempotent (re-running overwrites the installed copy) and prints where
it placed the skill.
