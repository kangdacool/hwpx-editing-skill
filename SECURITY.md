# Security Policy

This project is a local Python **skill** for editing HWPX (한글 `.hwpx`) files.
It runs on your machine, touches local files only, and **makes no network calls
and needs no credentials** — so the attack surface is small.

## Scope

Use the latest version on the `main` branch — there are no separately versioned
releases, so fixes land on `main`.

Worth reporting: a crafted `.hwpx`/`.hwp` that makes a script crash unsafely,
hang, or write outside the intended output path — or anything that could execute
code or leak data while processing a document.

## Reporting a vulnerability

Please report **privately** — do not open a public issue for a security bug.
Use GitHub's **Security → "Report a vulnerability"** (private advisory) on this
repo. I'll look into it as time allows and reply in the advisory thread. If you
can, attach a **minimal, non-confidential** `.hwpx` that reproduces it.
