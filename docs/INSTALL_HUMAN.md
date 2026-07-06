# Install guide — for humans (사람용 설치 가이드)

**[English](#for-humans-english)** · **[한국어](#사람용-한국어)**

---

<a name="for-humans-english"></a>
## For humans (English)

This guide covers **[installing the skill](#installing-the-skill)** into Claude Code, Codex, Cursor, etc.

### Installing the skill

Every method just puts the `skills/hwpx-editing/` folder where your agent looks for skills. The included installer does this for you.

#### With the installer (recommended)

```bash
# macOS / Linux
./install.sh claude     # → ~/.claude/skills/hwpx-editing/   (Claude Code + Desktop)
./install.sh codex      # → ~/.codex/skills/hwpx-editing/
./install.sh cursor     # → ./.cursor/skills/hwpx-editing/   (current project)
./install.sh gemini     # → ~/.gemini/skills/hwpx-editing/
./install.sh openclaw   # → ~/.openclaw/skills/hwpx-editing/
./install.sh all        # every agent above
./install.sh --link claude   # symlink instead of copy (stays in sync with the repo)
```

```powershell
# Windows PowerShell
./install.ps1 claude
./install.ps1 all
```

Then **restart your agent** (or start a new session) and confirm. In Claude Code, type `/skills` and look for **hwpx-editing**.

#### By hand (any agent)

Copy the one folder into the right place:

| Agent | Destination |
|---|---|
| Claude Code / Desktop (personal) | `~/.claude/skills/hwpx-editing/` |
| Claude Code (this project only) | `.claude/skills/hwpx-editing/` |
| OpenAI Codex | `~/.codex/skills/hwpx-editing/` |
| Cursor (this project) | `.cursor/skills/hwpx-editing/` |
| Gemini CLI | `~/.gemini/skills/hwpx-editing/` |
| OpenClaw | `~/.openclaw/skills/hwpx-editing/` |

```bash
mkdir -p ~/.claude/skills
cp -r skills/hwpx-editing ~/.claude/skills/
```

The destination folder must contain `SKILL.md` **directly** (i.e. `.../skills/hwpx-editing/SKILL.md`), not nested an extra level deep.

#### Claude.ai (web)

Zip the skill folder and upload it under **Settings → Features → Skills** (needs a Pro/Max/Team/Enterprise plan with code execution). Make the zip so `SKILL.md` is at the top level:
```bash
cd skills && zip -r hwpx-editing.zip hwpx-editing && cd ..
```

#### Install the Python dependency

The scripts use `lxml`:
```bash
pip install lxml       # or: pip3 install lxml
```

#### Verify it works (no HWPX needed)

```bash
python skills/hwpx-editing/scripts/selftest.py
```
You should see six `PASS` lines and `RESULT: ALL PASS`.

---

<a name="사람용-한국어"></a>
## 사람용 (한국어)

이 문서는 **[스킬 설치하기](#스킬-설치하기)** — Claude Code, Codex, Cursor 등에 넣는 방법을 다룹니다.

### 스킬 설치하기

모든 방법은 결국 `skills/hwpx-editing/` 폴더를 에이전트가 스킬을 찾는 위치에 두는 것뿐입니다. 포함된 설치 스크립트가 대신 해줍니다.

#### 설치 스크립트 사용 (권장)

```bash
# macOS / Linux
./install.sh claude     # → ~/.claude/skills/hwpx-editing/   (Claude Code + Desktop)
./install.sh codex      # → ~/.codex/skills/hwpx-editing/
./install.sh cursor     # → ./.cursor/skills/hwpx-editing/   (현재 프로젝트)
./install.sh gemini     # → ~/.gemini/skills/hwpx-editing/
./install.sh openclaw   # → ~/.openclaw/skills/hwpx-editing/
./install.sh all        # 위 전부
./install.sh --link claude   # 복사 대신 심볼릭 링크(레포와 계속 동기화)
```

```powershell
# Windows PowerShell
./install.ps1 claude
./install.ps1 all
```

그다음 **에이전트를 재시작**(또는 새 세션 시작)하고 확인하세요. Claude Code에서는 `/skills`를 입력해 **hwpx-editing**이 보이는지 봅니다.

#### 직접 복사 (모든 에이전트)

폴더 하나를 알맞은 위치에 복사하면 끝:

| 에이전트 | 대상 경로 |
|---|---|
| Claude Code / Desktop (개인) | `~/.claude/skills/hwpx-editing/` |
| Claude Code (이 프로젝트만) | `.claude/skills/hwpx-editing/` |
| OpenAI Codex | `~/.codex/skills/hwpx-editing/` |
| Cursor (이 프로젝트) | `.cursor/skills/hwpx-editing/` |
| Gemini CLI | `~/.gemini/skills/hwpx-editing/` |
| OpenClaw | `~/.openclaw/skills/hwpx-editing/` |

```bash
mkdir -p ~/.claude/skills
cp -r skills/hwpx-editing ~/.claude/skills/
```

대상 폴더 안에 `SKILL.md`가 **바로** 있어야 합니다(`.../skills/hwpx-editing/SKILL.md`). 한 단계 더 깊이 들어가면 안 됩니다.

#### Claude.ai (웹)

스킬 폴더를 zip으로 묶어 **설정 → Features → Skills**에서 업로드합니다(코드 실행이 켜진 Pro/Max/Team/Enterprise 필요). `SKILL.md`가 zip 최상위에 오도록:
```bash
cd skills && zip -r hwpx-editing.zip hwpx-editing && cd ..
```

#### 파이썬 의존성 설치

스크립트는 `lxml`을 씁니다:
```bash
pip install lxml       # 또는: pip3 install lxml
```

#### 동작 확인 (HWPX 없이)

```bash
python skills/hwpx-editing/scripts/selftest.py
```
`PASS` 6줄과 `RESULT: ALL PASS`가 보이면 정상입니다.
