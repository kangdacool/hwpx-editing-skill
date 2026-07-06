# Install guide — for humans (사람용 설치 가이드)

**[English](#for-humans-english)** · **[한국어](#사람용-한국어)**

---

<a name="for-humans-english"></a>
## For humans (English)

Two things live here:
- **[Publishing to GitHub](#publishing-to-github-first-time)** — if you made this repo and want it online (first time ever? start here).
- **[Installing the skill](#installing-the-skill)** — putting it into Claude Code, Codex, Cursor, etc.

### Publishing to GitHub (first time)

You have the folder `hwpx-editing-skill/` on your computer. Goal: get it onto GitHub so others can find and ⭐ it.

**Prerequisites**
- A free GitHub account (you have one).
- Git installed. Check in a terminal: `git --version`. If missing, install from <https://git-scm.com/downloads>.

#### Option A — the easy way (GitHub website, no command line)

1. Go to <https://github.com/new>.
2. **Repository name**: `hwpx-editing-skill`. Add a short description. Choose **Public** (needed for stars). **Do not** check "Add a README" (you already have one).
3. Click **Create repository**. GitHub now shows a page with commands under *"…or push an existing repository from the command line."*
4. Open a terminal, `cd` into your folder, and run (replace `<your-username>`):
   ```bash
   cd path/to/hwpx-editing-skill
   git init
   git add .
   git commit -m "Initial commit: HWPX editing skill"
   git branch -M main
   git remote add origin https://github.com/<your-username>/hwpx-editing-skill.git
   git push -u origin main
   ```
5. If it asks you to log in, use a **Personal Access Token** as the password (GitHub no longer accepts your account password over HTTPS). Create one at **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token**, tick the `repo` scope, copy it, and paste it when prompted. Treat it like a password.
6. Refresh your repo page — your files are live. 🎉

> ⚠️ Never paste your token into a chat, a file, or this repo. If you accidentally do, revoke it in GitHub settings and make a new one.

#### Option B — with the GitHub CLI (`gh`), fewer steps

1. Install `gh`: <https://cli.github.com/>. Then `gh auth login` and follow the prompts (this handles the token for you).
2. From the folder:
   ```bash
   cd path/to/hwpx-editing-skill
   git init && git add . && git commit -m "Initial commit: HWPX editing skill"
   gh repo create hwpx-editing-skill --public --source=. --remote=origin --push
   ```
That's it — `gh` creates the repo and pushes in one step.

#### After publishing — a few things that earn stars

- **Add "topics"** on the repo page (gear icon next to *About*): `hwpx`, `hangul`, `한글`, `agent-skills`, `claude-code`, `codex`, `llm`, `korean`. Topics make it discoverable.
- **Fill the *About*** blurb and add the tagline.
- Update the two `<your-username>` placeholders in `README.md` so the clone command works, then commit again:
  ```bash
  git add README.md && git commit -m "docs: set repo URL" && git push
  ```
- Optionally share it where Korean devs gather (a relevant subreddit, dev community, or an "awesome" list PR).

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

여기엔 두 가지가 있습니다.
- **[깃허브에 올리기](#깃허브에-올리기-처음-한-번)** — 이 레포를 온라인에 올리고 싶다면 (처음이라면 여기부터).
- **[스킬 설치하기](#스킬-설치하기)** — Claude Code, Codex, Cursor 등에 넣기.

### 깃허브에 올리기 (처음 한 번)

지금 컴퓨터에 `hwpx-editing-skill/` 폴더가 있습니다. 목표는 이걸 깃허브에 올려서 남들이 찾고 ⭐ 누를 수 있게 하는 것.

**준비물**
- 무료 깃허브 계정 (이미 있음).
- Git 설치. 터미널에서 `git --version` 확인. 없으면 <https://git-scm.com/downloads> 에서 설치.

#### 방법 A — 쉬운 길 (깃허브 웹사이트, 명령어 최소)

1. <https://github.com/new> 접속.
2. **Repository name**: `hwpx-editing-skill`. 짧은 설명 입력. **Public** 선택(스타 받으려면 공개여야 함). "Add a README"는 **체크하지 마세요**(이미 있음).
3. **Create repository** 클릭. 그러면 *"…or push an existing repository from the command line"* 아래 명령어가 나옵니다.
4. 터미널을 열고 폴더로 이동한 뒤 실행(`<your-username>` 교체):
   ```bash
   cd 경로/hwpx-editing-skill
   git init
   git add .
   git commit -m "Initial commit: HWPX editing skill"
   git branch -M main
   git remote add origin https://github.com/<your-username>/hwpx-editing-skill.git
   git push -u origin main
   ```
5. 로그인을 요구하면 비밀번호 자리에 **Personal Access Token(PAT)**을 넣습니다(깃허브는 HTTPS에서 계정 비밀번호를 더 이상 안 받습니다). **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token**에서 `repo` 권한을 체크하고 생성해 복사한 뒤, 물어볼 때 붙여넣습니다. 비밀번호처럼 취급하세요.
6. 레포 페이지를 새로고침하면 파일이 올라와 있습니다. 🎉

> ⚠️ 토큰을 채팅·파일·이 레포에 절대 붙여넣지 마세요. 실수했다면 깃허브 설정에서 폐기(revoke)하고 새로 만드세요.

#### 방법 B — 깃허브 CLI(`gh`)로 더 간단히

1. `gh` 설치: <https://cli.github.com/>. 그다음 `gh auth login` 하고 안내대로 진행(토큰을 알아서 처리해 줌).
2. 폴더에서:
   ```bash
   cd 경로/hwpx-editing-skill
   git init && git add . && git commit -m "Initial commit: HWPX editing skill"
   gh repo create hwpx-editing-skill --public --source=. --remote=origin --push
   ```
`gh`가 레포 생성 + 푸시를 한 번에 처리합니다.

#### 올린 뒤 — 스타를 부르는 마무리

- 레포 페이지 *About* 옆 톱니바퀴에서 **topics** 추가: `hwpx`, `hangul`, `한글`, `agent-skills`, `claude-code`, `codex`, `llm`, `korean`. 검색 노출에 큰 도움.
- *About* 설명과 태그라인 채우기.
- `README.md`의 `<your-username>` 두 군데를 실제 아이디로 바꾸고 다시 커밋:
  ```bash
  git add README.md && git commit -m "docs: set repo URL" && git push
  ```
- 한국 개발자들이 모이는 곳(관련 커뮤니티, "awesome" 리스트 PR 등)에 공유하면 초기 유입에 좋습니다.

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
