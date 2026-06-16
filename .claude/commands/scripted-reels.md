# Scripted Reels Pipeline

Orchestrate the scripted reels editing pipeline. Request: $ARGUMENTS

## Instructions

Read the SKILL.md and tracker.json to understand the full pipeline and current state:

1. `Content/scripted-reels/SKILL.md` - Full pipeline reference
2. `Content/scripted-reels/tracker.json` - Clip database with statuses

## Session Start

1. Read SKILL.md and tracker.json
2. Summarize current state: how many clips at each status, which need work
3. Execute the user's request

## Common Requests

- **"edit the next N videos"** - Take the next N clips at `raw` status through the full pipeline. Present each for review before moving to next.
- **"schedule clip N"** - Write caption, upload, schedule as TRIAL_REEL. Update tracker.
- **"check performance"** - Pull analytics, update tracker with metrics, show summary.
- **"status"** - Show tracker summary: clips by status, recent performance.

## Pipeline Rules (non-negotiable)

- **Captions**: Max 5 words per phrase. Group from word-level Whisper timestamps. Natural speech breaks only.
- **Music**: Always normalize to a consistent LUFS before mixing. Volume at 13%. Trim leading silence.
- **Scheduling**: Always TRIAL_REEL with shareTrialAutomatically: false. Use Python urllib, not curl.
- **Tracker**: Update status after each pipeline step.
- **Re-mux**: Always strip edit list after H.264 encoding (fixes black first frame).
