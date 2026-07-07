<div align="center">

# 🦖 HWPX Editing Skill

**LLM 에이전트가 한글(`.hwpx`) 파일을 안 깨고 편집하게 해주는 Agent Skill.**

검증된 HWPML 편집 규칙과 실제로 돌아가는 Python 도구를 하나로 묶었습니다. Claude Code · Codex · Cursor · Gemini CLI 등에서 그대로 씁니다.

_A portable Agent Skill that teaches AI coding agents to edit HWPX (Hangul `.hwpx`) files without corrupting them._

[![CI](https://github.com/kangdacool/hwpx-editing-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/kangdacool/hwpx-editing-skill/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![Agent Skill](https://img.shields.io/badge/format-SKILL.md-8A2BE2)
![Works with](https://img.shields.io/badge/agents-Claude%20Code%20%C2%B7%20Codex%20%C2%B7%20Cursor%20%C2%B7%20Gemini-orange)

**[한국어](#한국어)** · **[English](#english)**

</div>

---

<a name="easiest"></a>
## 🪄 hwpx가 자꾸 깨지나요? (제일 쉬운 방법)

터미널·설치 필요 없습니다. Claude(claude.ai)나 ChatGPT 같은 대화형 AI로 hwpx를
만들거나 고치는 중이라면:

1. **[이 파일 하나](skills/hwpx-editing/references/hwpx-guide.md)** 를 내려받습니다
   (**Download raw file** 버튼, 또는 우클릭 → 다른 이름으로 저장).
2. hwpx 작업 중인 **그 대화에 방금 받은 파일을 첨부**합니다.
3. *"이 가이드 규칙대로 hwpx를 만들어/고쳐줘. 안 깨지게."* 라고 요청합니다.

그게 전부입니다. AI가 직접 파일을 다룰 수 있을 때 가장 매끄럽게 동작합니다. 잘 안 되면
아래 **[설치 방법](#누가-어떻게-쓰나)**을 참고하세요.

<a name="the-easiest-way"></a>
## 🪄 Keep getting corrupted hwpx files? (the easiest way)

No terminal, no install. If you're creating or fixing hwpx with a chat AI like
Claude (claude.ai) or ChatGPT:

1. Download **[this one file](skills/hwpx-editing/references/hwpx-guide.md)**
   (the **Download raw file** button, or right-click → Save link as).
2. **Attach that file** to the same chat where you're working on the hwpx.
3. Ask: *"Create/fix this hwpx following the rules in this guide, without corrupting it."*

That's it. It works most smoothly when the AI can handle files directly. If it
doesn't work well, see the **[install options](#who-is-this-for)** below.

---

<a name="한국어"></a>
## 한국어

### 왜 만들었나

HWPX(요즘 한글 포맷)는 사실상 **XML을 담은 zip**인데, 깨뜨리는 방법이 하나같이
직관적이지 않습니다. 일반 zip 라이브러리로 다시 압축하면 한글이 파일을 안 엽니다.
캐시된 줄배치 배열(`linesegarray`)을 안 지우면 자간·줄간격이 깨집니다. 표를 복제하면
원본 `id`를 물려받아 중복이 생기고 파일이 불안정해집니다. 관련 도구가 거의 없다 보니,
LLM 에이전트가 알아서 하게 두면 **열리지 않는 파일**을 만들기 십상입니다.

이 스킬은 에이전트에게 (한글 렌더링·바이트 수준으로 **검증된**) **정확한 규칙**과
**실제로 돌아가는 스크립트**를 쥐여줍니다. 그래서 편집이 "그냥 됩니다" — 원본이
한글에서 열리면, 편집본도 열립니다.

### 구성

```
skills/hwpx-editing/
├── SKILL.md                 # 스킬 본체 (에이전트가 읽는 파일)
├── references/
│   └── hwpx-guide.md        # 전체 실전 가이드 — §1 파싱 … §7 검증
└── scripts/
    ├── hwpxlib.py           # 검증된 핵심 함수 (재압축 / 파싱 / 검증)
    ├── inspect_hwpx.py      # 구조 덤프 · 숨은 페이지/단 나눔 탐지
    ├── verify.py            # §7 빌드 체크리스트 실행 (CI 게이트 가능)
    └── selftest.py          # 실제 파일 없이 재압축 무손실성 증명
```

핵심은 `repack_preserve`(**raw-preserving 재압축기**)입니다. 아무것도 안 바꾸고
재압축하면 원본과 **바이트 100% 동일**합니다. `selftest.py`가 합성 파일로 이를
증명하므로, 내 문서를 건드리기 전에 신뢰할 수 있습니다. 여기에 더해, 실제 한글 문서
**3종(본문 4·10·12개 섹션 규모, 모두 이미지·표·수식·미주 포함)**에서 편집 후 한글로
다시 열어 정상 동작을 확인했습니다.

### 누가 어떻게 쓰나

크게 두 부류로 나뉩니다. 자기에게 맞는 쪽만 보면 됩니다.

**① 터미널을 안 쓰는 분 (비개발자)**

- **가장 쉽게, 한 번만** — 파일 하나(가이드)를 대화에 첨부하면 끝입니다. 맨 위
  **[제일 쉬운 방법](#easiest)**을 보세요.
- **자주 쓸 때 — 스킬로 업로드** — claude.ai에 스킬로 등록해 두면 매번 첨부할 필요가
  없습니다. 이 GitHub 레포에서 **Code → Download ZIP** 으로 받아 압축을 풀고, 안의
  `skills/hwpx-editing` 폴더 **하나만** 다시 zip으로 묶은 뒤, claude.ai →
  **설정(Settings) → Features → Skills** 에서 업로드합니다(코드 실행이 켜진
  **Pro/Max/Team/Enterprise** 플랜 필요). 이후 `.hwpx`를 올리고 자연어로 시키면 됩니다.

**② 개발자 / 터미널을 쓰는 분 — CLI에 설치**

Claude Code · Codex · Cursor · Gemini CLI 등에 스킬 폴더를 설치해 두면, 이후
`.hwpx`/한글 작업에서 자동으로 발동합니다. 설치는 아래 **[빠른 설치](#빠른-설치-한-줄)**
한 줄이면 됩니다.

### 빠른 설치 (한 줄)

에이전트를 고르세요. 아래 명령을 그대로 실행하면 됩니다.

```bash
# 한 번만 클론
git clone https://github.com/kangdacool/hwpx-editing-skill.git
cd hwpx-editing-skill

# 에이전트에 설치 (macOS / Linux)
./install.sh claude      # Claude Code / Claude Desktop  → ~/.claude/skills/
./install.sh codex       # OpenAI Codex                  → ~/.codex/skills/
./install.sh cursor      # Cursor (프로젝트)              → .cursor/skills/
./install.sh gemini      # Gemini CLI                    → ~/.gemini/skills/
./install.sh openclaw    # OpenClaw                      → ~/.openclaw/skills/
./install.sh all         # 지원하는 모든 에이전트에 설치(openclaw 포함)
```

Windows(PowerShell): `./install.ps1 claude` (하위 명령 동일).

더 자세한 설치 방법은 **[사람용 설치 가이드](docs/INSTALL_HUMAN.md)**, 에이전트에게 대신 설치를
시키려면 **[LLM용 설치 가이드](docs/INSTALL_LLM.md)**를 참고하세요.

> `lxml` 필요: `pip install lxml` (Python 3.10 이상).
>
> **HWPX 전용** — 구형 `.hwp`(OLE 바이너리)는 한글에서 먼저 **다른 이름으로 저장 → HWPX(.hwpx)**로 변환한 뒤 사용하세요.

### 사용법

설치 후에는 그냥 자연스럽게 시키면 됩니다 — `.hwpx`/한글 작업이면 스킬이 자동으로
발동합니다:

- *"`보고서.hwpx` 읽고 표 전부 CSV로 뽑아줘."*
- *"`논문.hwpx`에서 초록 바꾸고 첫 문장 뒤에 미주 하나 달아줘."*
- *"`발표.hwpx`에서 제목이 내용이랑 갈라졌어 — 레이아웃 고쳐줘."*
- *"이 차트 이미지를 2절에 넣고 파일 다시 만들어줘."*

에이전트는 파일을 먼저 진단하고, 가이드를 따라 무손실로 재압축하고, 검증기를 돌린 뒤,
한글에서 라운드트립(직접 열어 확인)해 달라고 요청합니다 — LibreOffice는 HWPX를 렌더할 수
없기 때문입니다.

도구를 직접 돌릴 수도 있습니다:

```bash
python skills/hwpx-editing/scripts/inspect_hwpx.py 내문서.hwpx --breaks
python skills/hwpx-editing/scripts/verify.py 편집본.hwpx --orig 원본.hwpx
python skills/hwpx-editing/scripts/selftest.py     # 파일 없이 동작 점검
```

### 이 스킬이 막아주는 함정

가이드 맨 앞의 "흔한 실패 TOP" 맛보기:

1. 변경 안 한 엔트리를 재deflate → 한글이 거부. *(raw-preserving 재압축 사용)*
2. `linesegarray`를 안 지움 → 자간·줄간격 깨짐. *(편집 후 제거)*
3. 클론이 원본 `id`를 물려받음 → 중복 → 불안정. *(id 재발급)*
4. 숨은 `pageBreak`부터 안 찾고 `keepWithNext`만 만짐. *(숨은 break 먼저)*
5. `content.hpf`를 raw 문자열로 편집 → 백슬래시 오염. *(XML로 파싱)*

…그 외에도 (이미지 순서, `itemCnt`, 2단의 넓은 표, 미주 `ctrl` 래핑 등) 다수.

### 호환성

| 에이전트 | 설치 위치 | 비고 |
|---|---|---|
| Claude Code | `~/.claude/skills/` (개인) 또는 `.claude/skills/` (프로젝트) | `/skills`로 확인 |
| Claude Desktop | `~/.claude/skills/` | Claude Code와 동일 경로 |
| Claude.ai (Pro/Max/Team/Enterprise) | 설정 → Features → 스킬 zip 업로드 | 코드 실행 필요 |
| OpenAI Codex | `~/.codex/skills/` (또는 레포 루트 `AGENTS.md`) | [AGENTS.md](AGENTS.md) 포함 |
| Cursor | `.cursor/skills/` (프로젝트) | |
| Gemini CLI | `~/.gemini/skills/` | |
| OpenClaw | `~/.openclaw/skills/` | 동일한 SKILL.md 포맷 |

`SKILL.md` 포맷은 이들 에이전트가 공유하는 사실상의 표준이라, 폴더 하나면 어디서든
동작합니다. 경로는 바뀔 수 있으니 `/skills`에 안 뜨면 해당 에이전트 최신 문서를 확인하세요.

### 기여 & 라이선스

이슈·PR 환영합니다 — 특히 실제 HWPX 엣지 케이스와 한글에서 검증된 수정이면 좋습니다.
[CONTRIBUTING.md](CONTRIBUTING.md) 참고. [MIT](LICENSE) 라이선스.

**이 스킬이 한글 파일 하나 살렸다면 ⭐ 눌러주세요 — 다른 사람도 찾기 쉬워집니다.**

---

<a name="english"></a>
## English

### Why this exists

HWPX (the modern 한글 format) is a **zip of XML**, and the ways to corrupt it are
non-obvious. Re-zip it with a normal zip writer and 한글 refuses to open it. Forget
to clear a cached line-layout array and spacing breaks. Clone a table and it drags a
duplicate `id` along and destabilizes the file. There's very little tooling for this —
so LLM agents, left to guess, reliably produce files that won't open.

This skill hands the agent **the exact rules** (verified against real 한글 rendering
and at the byte level) plus **working scripts**, so an edit "just works": if the
original opens in 한글, the edited file opens too.

### What's in the box

```
skills/hwpx-editing/
├── SKILL.md                 # the skill (agents read this)
├── references/
│   └── hwpx-guide.md        # the full field guide — §1 parsing … §7 verification
└── scripts/
    ├── hwpxlib.py           # verified primitives (repack / parse / verify)
    ├── inspect_hwpx.py      # dump structure; find hidden page/column breaks
    ├── verify.py            # run the §7 build checklist (CI-gateable)
    └── selftest.py          # prove the repacker is lossless — no real file needed
```

The crown jewel is `repack_preserve`: a **raw-preserving repacker** whose no-op output
is **byte-identical** to the source. `selftest.py` proves it on a synthetic file, so you
can trust it before touching your own documents. Beyond the synthetic self-test, it's
been validated on **3 real 한글 documents** (spanning 4, 10, and 12 sections, each with
images, tables, equations, and endnotes) — edited and re-opened in 한글.

### Who is this for

Two kinds of users — read whichever one fits you.

**① Not a terminal user (non-developer)**

- **Easiest, one-off** — just attach one file (the guide) to your chat. See
  **[the easiest way](#the-easiest-way)** at the top.
- **Using it often — upload as a skill** — register it once on claude.ai so you
  don't attach it every time. Download this repo via **Code → Download ZIP**, unzip,
  re-zip **only** the `skills/hwpx-editing` folder, then upload it under
  **Settings → Features → Skills** (needs a **Pro/Max/Team/Enterprise** plan with
  code execution). Then attach a `.hwpx` and ask in plain language.

**② Developer / terminal user — install into your CLI**

Install the skill folder into Claude Code · Codex · Cursor · Gemini CLI, and it
triggers automatically on `.hwpx` / 한글 work afterward. Installation is the
one-liner in **[Quick install](#quick-install-one-line)** below.

### Quick install (one line)

Pick your agent and run the commands below.

```bash
# Clone once
git clone https://github.com/kangdacool/hwpx-editing-skill.git
cd hwpx-editing-skill

# Then install into your agent (macOS / Linux)
./install.sh claude      # Claude Code / Claude Desktop  → ~/.claude/skills/
./install.sh codex       # OpenAI Codex                  → ~/.codex/skills/
./install.sh cursor      # Cursor                        → .cursor/skills/ (project)
./install.sh gemini      # Gemini CLI                    → ~/.gemini/skills/
./install.sh openclaw    # OpenClaw                      → ~/.openclaw/skills/
./install.sh all         # install into every supported agent (incl. openclaw)
```

Windows (PowerShell): `./install.ps1 claude` (same subcommands).

For more detail, see the **[Human install guide](docs/INSTALL_HUMAN.md)**; to have an
agent install it for you, give it the **[LLM install guide](docs/INSTALL_LLM.md)**.

> Requires `lxml`: `pip install lxml` (Python 3.10+).
>
> **HWPX only** — a legacy `.hwp` (OLE binary) must first be converted in 한글 via **다른 이름으로 저장 → HWPX(.hwpx)**.

### Use it

Once installed, just ask your agent naturally — the skill triggers on `.hwpx` / 한글
work:

- *"Read `report.hwpx` and pull out every table as CSV."*
- *"In `paper.hwpx`, replace the abstract and add an endnote after the first sentence."*
- *"A heading in `slides.hwpx` got split from its body — fix the layout."*
- *"Insert this chart image into section 2 and rebuild the file."*

The agent will inspect the file, follow the guide, repack losslessly, and run the
verifier — then ask you to round-trip it in 한글 (LibreOffice can't render HWPX).

You can also run the tools directly:

```bash
python skills/hwpx-editing/scripts/inspect_hwpx.py mydoc.hwpx --breaks
python skills/hwpx-editing/scripts/verify.py edited.hwpx --orig original.hwpx
python skills/hwpx-editing/scripts/selftest.py     # sanity check, no file needed
```

### The traps it protects you from

A taste of the "common failures" the guide front-loads:

1. Re-deflating unchanged entries → 한글 rejects the file. *(use raw-preserving repack)*
2. Leaving `linesegarray` → broken letter/line spacing. *(strip after edits)*
3. Cloned nodes inheriting `id`s → duplicates → instability. *(reassign ids)*
4. Fixing layout at `keepWithNext` before hunting the hidden `pageBreak`. *(breaks first)*
5. Editing `content.hpf` as a raw string → backslash corruption. *(parse as XML)*

…and more (image order, `itemCnt`, wide tables in 2-column regions, endnote wrapping).

### Compatibility

| Agent | Install location | Notes |
|---|---|---|
| Claude Code | `~/.claude/skills/` (personal) or `.claude/skills/` (project) | verify with `/skills` |
| Claude Desktop | `~/.claude/skills/` | same path as Claude Code |
| Claude.ai (Pro/Max/Team/Enterprise) | Settings → Features → upload the skill zip | code execution required |
| OpenAI Codex | `~/.codex/skills/` (or `AGENTS.md` at repo root) | [AGENTS.md](AGENTS.md) included |
| Cursor | `.cursor/skills/` (project) | |
| Gemini CLI | `~/.gemini/skills/` | |
| OpenClaw | `~/.openclaw/skills/` | identical SKILL.md format |

The `SKILL.md` format is a de-facto standard shared across these agents, so one folder
works everywhere. Locations can change — if `/skills` doesn't list it, re-check the
current docs for your agent.

### Contributing & license

Issues and PRs welcome — especially real-world HWPX edge cases and fixes verified in
한글. See [CONTRIBUTING.md](CONTRIBUTING.md). Licensed under [MIT](LICENSE).

**If this saved you from a corrupted 한글 file, please ⭐ the repo — it helps others find it.**
