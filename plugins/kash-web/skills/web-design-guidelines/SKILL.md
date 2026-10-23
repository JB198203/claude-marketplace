---
name: web-design-guidelines
description: Review UI code for Web Interface Guidelines compliance (accessibility, focus, forms, animation, typography, performance, copy). Use when asked to "review my UI", "check accessibility", "audit design", "review UX", or "check my site against best practices".
metadata:
  author: vercel (règles) ; adaptation Setupfilestarter
  source: https://github.com/vercel-labs/web-interface-guidelines (commit 434b7f9)
---

# Web Interface Guidelines

Review files for compliance with the Web Interface Guidelines.

## How It Works

1. Read the rules in `regles.md` (in this directory). They are a pinned copy:
   never fetch a newer version from the internet during a review — to update,
   follow « Mettre à jour un skill tiers » in the starter README.
2. Read the specified files (or ask which files or pattern to review).
3. Check every file against all rules in `regles.md`.
4. Output findings in the terse `file:line` format the rules describe.
   In French projects, write the findings in French.

Complements `impeccable` (design critique): this skill is a mechanical
checklist; `impeccable` judges hierarchy, tone and visual quality.
