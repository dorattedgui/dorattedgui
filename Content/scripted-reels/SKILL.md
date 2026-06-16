# Scripted Reels Pipeline

## Pipeline Overview

```
Raw clip (.mp4)
    |
    v
[1] CUT - Silence Detection + Trim (edit.py)
    -> Detect speech/silence boundaries (silencedetect)
    -> Cross-reference with transcript to identify final takes
    -> Build keep-segments.json, render clean edit
    |
    v
[2] COLOR GRADE - FFmpeg eq filter
    -> Apply brightness/contrast/saturation adjustments
    |
    v
[3] CAPTIONS - Whisper + ASS subtitle burn-in
    -> Get word-level timestamps via whisper-cpp
    -> Group into 3-5 word phrases (max 5, natural breaks)
    -> Generate ASS file, burn into video
    |
    v
[4] MUSIC - Normalized background music mix
    -> Normalize to target LUFS (loudnorm 2-pass)
    -> Mix at 13% volume, 3s fade out
    |
    v
[5] STYLE - Apply editing style (standard or letterbox)
    -> Letterbox: 700px black bars + visual hook in top bar
    |
    v
[6] CAPTION + SCHEDULE - Write caption, schedule as trial reel
```

Steps 2-5 are rendered together in a 2-pass FFmpeg pipeline.

## Step 1: Detect speech segments

```bash
.venv/bin/python Content/scripted-reels/edit.py path/to/clip.mp4 --detect
```

Outputs a numbered list of speech segments with timestamps and durations.

## Step 2: Build keep-segments.json

Cross-reference speech segments with the transcript to identify final takes:

```json
{
  "keep": [
    {"start": 54.43, "end": 61.28, "label": "Hook"},
    {"start": 63.30, "end": 73.00, "label": "Body"}
  ]
}
```

**Rules for building keep segments:**
- Use EXACT speech segment boundaries from step 1 (silencedetect is precise)
- Do NOT manually adjust start times - this clips word beginnings
- Keep the LAST take when the speaker repeats a section
- Short phrases (< 3 words) followed by a longer version = false start, remove
- Long segments can contain multiple sub-takes - silencedetect only splits on gaps >= 0.4s
- Segments can bleed into the next section - trim segment ends when the tail contains a false start

**CRITICAL: Retake detection across segment boundaries.**

The most common editing mistake is including an incomplete take AND the complete retake of the same sentence:
1. Speaker starts a sentence, pauses
2. Silencedetect creates a boundary at the pause
3. Speaker starts the SAME sentence again in the next segment

The incomplete take lives at the END of one segment, the retake at the START of the next. If you keep both, the sentence plays twice.

**How to catch this:**
- Transcribe each raw speech segment INDIVIDUALLY (not the whole clip as one block)
- Compare the END of segment N with the START of segment N+1
- If they begin with the same words, trim the end of segment N
- Find the cut point with word-level timestamps from whisper-cpp

**Final word protection:** Always extend the last keep-segment by 0.2s beyond the silencedetect boundary to avoid clipping the final word.

## Step 3: Render + Verify

After rendering, transcribe the clean cut and review for:
1. **Duplicate content** - repeated phrases (multiple sub-takes included)
2. **False starts** - partial sentences at segment boundaries
3. **Missing content** - expected phrases that aren't there
4. **Cut-off endings** - CTA or final sentence truncated

If issues found, rebuild keep-segments and re-process. Do NOT proceed to captions until transcript is clean.

## Step 3b: Dead Space Elimination

**General rule: no dead space between sentences or cuts.** Talking-head reels must feel tight.

After transcript is clean, run a full dead-space pass:

1. **Full RMS scan** - find quiet zones using astats:
   ```bash
   ffmpeg -i edit.mp4 -af "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=/dev/stdout" -f null - 2>/dev/null
   ```
   Find every consecutive run of frames below -30dB lasting > 0.1s.

2. **Trim all gaps > 0.15s** - trim down to ~0.08s (natural micro-pause)

3. **Verify** - re-scan, no remaining quiet zones should exceed 0.17s

4. **Stutter detection** - check transcript for repeated words ("that's why and that's why")

## Source Format Handling

Source clips from iPhone are typically HEVC (H.265) with 10-bit color. The pipeline auto-converts to H.264 (yuv420p) before editing because:
- HEVC has sparse keyframes causing black frames on trim
- 10-bit color causes pixel format mismatches in filter_complex
- Conversion is cached (.h264.mp4) so subsequent renders are fast

Conversion: `-crf 16 -g 15` (keyframe every 0.5s for precise trimming).

## Filtergraph Architecture

Single filter_complex command:
1. trim/atrim each segment with setpts=PTS-STARTPTS
2. concat all segments together (video AND audio in one concat)
3. Final setpts=PTS-STARTPTS on video to re-zero PTS

**Critical:** Video and audio MUST be concatenated together in the same concat filter. Separate concat for video and audio crossfade causes progressive A/V desync.

## Edit List Fix

H.264 encoding creates an elst (edit list) atom with media_time: -1, telling players to show black before the first frame. Strip via re-mux:

```bash
ffmpeg -fflags +genpts+igndts -i temp.mp4 -c copy -movflags +faststart output.mp4
```

## Caption Generation

**Step 1: Get word timestamps via whisper-cpp**

```bash
# Extract audio
ffmpeg -y -i path/to/edit.mp4 -vn -ar 16000 -ac 1 -c:a pcm_s16le /tmp/clip-audio.wav

# Transcribe with word-level timestamps
/opt/homebrew/Cellar/whisper-cpp/1.8.4/bin/whisper-cli \
  -m /tmp/ggml-base.bin -f /tmp/clip-audio.wav -ml 5 -oj -of /tmp/clip-whisper

# Convert to pipeline format
python3 -c "
import json
d = json.load(open('/tmp/clip-whisper.json'))
words = [{'word': s['text'].strip(), 'start': s['offsets']['from']/1000, 'end': s['offsets']['to']/1000}
         for s in d['transcription'] if s['text'].strip()]
json.dump(words, open('path/to/CLIP-words.json', 'w'), indent=2)
"
```

**Note:** whisper-cpp may crash on exit (Metal GPU cleanup bug) but still saves JSON. If JSON isn't saved, capture from stdout:
```bash
/opt/homebrew/Cellar/whisper-cpp/1.8.4/bin/whisper-cli \
  -m /tmp/ggml-base.bin -f /tmp/clip-audio.wav -ml 5 2>/dev/null | grep "^\[" > /tmp/timestamps.txt
```

**Step 2: Group words into phrases (max 5 words)**

Rules:
- **Max 5 words per phrase**, prefer 3-4
- **Merge split numbers**: 50 + ,000 = 50,000
- **Attach punctuation**: girl , -> girl,, 5 % -> 5%
- **Split compound tokens**: 's a, , and, is 5
- **Merge split words**: set + ter -> setter, open + ers -> openers
- Break at natural speech boundaries
- **Never break mid-sentence** across unrelated thoughts
- CTA keywords stay in quotes

Save as CLIP-phrases-v2.json.

**Step 3: Generate ASS subtitle file**

ASS style settings (1728x3072 canvas):
```
[V4+ Styles]
Style: Default,Helvetica Neue,90,&H00FFFFFF,&H000000FF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,1,2,3,2,50,50,250,1
```

Key parameters:
- Font: Helvetica Neue, size 90
- Color: White
- Outline: 2, Shadow: 3
- Alignment: 2 (bottom-center)
- MarginV: 1050 (chest level on talking head) for letterbox style
- MarginV: 250 (bottom bar) only if you want captions in the bottom black bar
- All text lowercase
- PlayResX: 1728, PlayResY: 3072

## Visual Hook (Top Bar) - Letterbox Style

Short, punchy headline rendered in the top black bar. First thing a viewer reads while scrolling.

**Writing rules:**
- 3-10 words max
- All lowercase
- NOT the same as the spoken hook
- Never a question
- Use numbers when possible

**Hook patterns (ranked by effectiveness):**

1. **Formula/equation** - uses symbols to express a framework
   - `awareness > interest > action`
   - `clarity + proof + urgency = decision`
   - `1 reel/week > 50 reels/week`

2. **Bold claim with number** - specific, provocative
   - `30 hours saved per week. one tool.`
   - `1000 hours of footage analyzed. here's the pattern.`

3. **Contrarian statement** - challenges conventional wisdom
   - `views don't pay the bills. customers do.`
   - `tools aren't a strategy.`

4. **Result/proof statement** - social proof in headline form
   - `morning report. business stats. no humans.`
   - `automated my pipeline. revenue went up.`

## Editing Styles

### Letterbox (PREFERRED)

700px black bars top and bottom. Top bar contains visual hook headline.

**Three-zone layout:**
```
+-------------------------+
|     TOP BLACK BAR       |  700px - HOOK TEXT (near bottom edge)
+-------------------------+
|                         |
|    TALKING HEAD VIDEO   |  ~1672px
|    (captions at chest   |
|     level, MarginV=1050)|
|                         |
+-------------------------+
|     BOTTOM BLACK BAR    |  700px - empty
+-------------------------+
```

**Hook PNG rendering (Swift):**

drawtext can't render emoji, and uses native font metrics that produce unexpected sizing. Pre-render as PNG.

```swift
// render_hook.swift
import AppKit
import Foundation

let text = "your hook text here"
let fontSize: CGFloat = 72
let font = NSFont(name: "HelveticaNeue", size: fontSize) ?? NSFont.systemFont(ofSize: fontSize)
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.3)
shadow.shadowOffset = NSSize(width: 2, height: -2)
let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.white, .shadow: shadow]
let str = NSAttributedString(string: text, attributes: attrs)
let size = str.size()
let imgW = Int(ceil(size.width + 20))
let imgH = Int(ceil(size.height + 10))

// CRITICAL: Use NSBitmapImageRep directly at 1x scale.
// NSImage renders at 2x on Retina, breaking pixel dimensions.
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: imgW, pixelsHigh: imgH,
    bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
    colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
rep.size = NSSize(width: imgW, height: imgH)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
NSColor.clear.setFill()
NSRect(x: 0, y: 0, width: imgW, height: imgH).fill()
str.draw(at: NSPoint(x: 10, y: 5))
NSGraphicsContext.restoreGraphicsState()
let png = rep.representation(using: .png, properties: [:])!
try! png.write(to: URL(fileURLWithPath: "/tmp/hook.png"))
```

Run: `swift /tmp/render_hook.swift`

**Pass 1: Static bars + hook PNG + captions**

```bash
BAR=700
HOOK_X=$(( (1728 - HOOK_WIDTH) / 2 ))
HOOK_Y=$(( BAR - HOOK_HEIGHT - 30 ))

ffmpeg -y -i GRADED.mp4 -loop 1 -i /tmp/hook.png \
  -filter_complex "
    color=black:s=1728x${BAR}:r=30000/1001:d=DURATION[topbar];
    color=black:s=1728x${BAR}:r=30000/1001:d=DURATION[botbar];
    [0:v][topbar]overlay=x=0:y=0[wT];
    [wT][botbar]overlay=x=0:y=main_h-overlay_h[wB];
    [wB][1:v]overlay=x=${HOOK_X}:y=${HOOK_Y}:shortest=1[wH];
    [wH]ass=CAPTIONS.ass[v]
  " \
  -map "[v]" -map "0:a" \
  -c:v libx264 -crf 18 -preset fast -c:a aac -b:a 192k \
  -movflags +faststart -t DURATION TEMP_VID.mp4
```

**Pass 2: Music mix**

```bash
ffmpeg -y -i TEMP_VID.mp4 -stream_loop -1 -i MUSIC.mp3 \
  -filter_complex "
    [0:a]volume=1.0[voice];
    [1:a]volume=0.13,afade=t=out:st=FADE_START:d=3.0[music];
    [voice][music]amix=inputs=2:duration=first:normalize=0[a]
  " \
  -map "0:v" -map "[a]" -c:v copy -c:a aac -b:a 192k \
  -movflags +faststart -shortest TEMP.mp4
```

FADE_START = clip duration minus 3 seconds.

**Pass 3: Strip edit list**

```bash
ffmpeg -y -fflags +genpts+igndts -i TEMP.mp4 -c copy -movflags +faststart OUTPUT.mp4
```

## Music

Mix settings:
- Voice: 100%
- Music: 13% (volume=0.13)
- Music looped to clip length (-stream_loop -1)
- 3s fade out
- amix with normalize=0 (preserves voice volume)

**Loudness normalization:** All tracks must be normalized to the same LUFS. A typical reference is -7.41 LUFS for energetic instrumentals. Use FFmpeg loudnorm 2-pass:

```bash
# Pass 1: Measure
STATS=$(ffmpeg -i TRACK.mp3 -af "loudnorm=I=-7.41:TP=-1.0:LRA=11:print_format=json" -f null - 2>&1)
# Extract: input_i, input_tp, input_lra, input_thresh, target_offset

# Pass 2: Apply
ffmpeg -y -i TRACK.mp3 \
  -af "loudnorm=I=-7.41:TP=-1.0:LRA=11:measured_I=...:measured_TP=...:measured_LRA=...:measured_thresh=...:offset=...:linear=true" \
  NORMALIZED.mp3
```

**Track preparation:**
- Trim leading silence with silencedetect + ffmpeg -ss
- For tracks with calm intros, find the energetic section using RMS analysis
- Save originals as `-original.mp3` when trimming

## Color Grade

Per recording session, settings vary. A baseline that works for natural indoor lighting:

```
Brightness: -15%, Contrast: +5%, Saturation: -10%
FFmpeg: eq=brightness=-0.15:contrast=1.05:saturation=0.9
```

Adjust per batch based on your actual lighting. Save settings in tracker notes.

## Encoding Settings

| Parameter | Value | Reason |
|-----------|-------|--------|
| Codec | libx264 | Universal compatibility |
| CRF | 18 | Visually lossless |
| Preset | fast | Good speed/quality balance |
| Audio | AAC 192kbps | Standard for social media |
| Container | MP4 + faststart | Progressive download |

## Common Issues

**Black first frame** - Fixed by edit list re-mux step.

**A/V desync (audio drifts)** - Caused by audio crossfades separate from video concat. Always concat together.

**Clipped word starts** - Don't adjust segment start times from silencedetect output.

**Too much space between segments** - Increase TAIL_TRIM_S (default 0.08s).

## Tracker

tracker.json tracks every clip across all batches.

### Pipeline Statuses

| Status | Meaning |
|--------|---------|
| raw | Raw clip extracted, not yet edited |
| in_progress | Currently being edited (skip when picking next) |
| cut | Clean cut rendered |
| color_graded | Color grade applied |
| captioned | Captions burned in |
| music | Music mixed in |
| final_review | Ready for manual review |
| ready | Approved, caption written |
| scheduled | Scheduled, awaiting publish |
| trial | Published as trial, monitoring |
| promoted | Promoted from trial to full post |

### Tracker Fields

**Identity:**
- id: batch-date/clip-number
- batch / clip_number / title / hook

**Pipeline:**
- status, style, visual_hook, music_track
- raw_path / cut_path / final_path

**Publishing:**
- caption, cta_keyword, scheduled_date, posted_date
- trial_date, promoted_date, instagram_url

**Performance:**
- trial_views, trial_likes, trial_comments, trial_saves, trial_shares
- views, likes, comments, saves, shares (after promotion)

### Session Workflow

At session start, read tracker.json. When picking "next reel," select the first clip at raw status. Never pick in_progress (occupied by parallel session). Set chosen clip to in_progress before starting work.

## Post-Render Self-Review Checklist

Before presenting a video for review, verify ALL:

**Audio QA:**
- Run full RMS scan. No quiet zones > 0.17s below -30dB.
- Concat junction audit - silencedetect with tight threshold:
  ```bash
  ffmpeg -nostats -i EDIT.mp4 -af "silencedetect=noise=-30dB:d=0.05" -f null - 2>&1 | grep silence_
  ```
  For each keep-segment boundary, verify no silence > 50ms within ±150ms of concat point.
- Transcribe final render and verify:
  - No repeated words/phrases (stutters)
  - No false starts at boundaries
  - Flow reads naturally as continuous speech

**Linguistic false-start scan:**
- Verb collision - two main verbs in a row for same subject
- List + double verb - lists take ONE verb
- Incomplete clause + restart - clauses that don't grammatically resolve
- Repeated sentence opener - same opening 3-4 words twice within ~10s
- Connector with no antecedent - "and"/"but"/"so" where prior thought didn't finish

**Caption QA:**
- All quoted speech properly closed
- Product names spelled correctly
- CTA keyword in quotes
- No phrase exceeds 5 words
- All text lowercase
- No emojis, no hashtags

**Visual QA:**
- No black first frame
- Letterbox bars visible from frame 0
- Hook text readable from first frame
- Hook doesn't overflow top bar (max 2 lines)
- Captions don't overlap with video unintentionally

## Script Writing Rules

### Performance Lessons

The single biggest predictor of performance is **duration**:
- Under 40s: best performers
- 50-57s: middling
- 60s+: high skip rates

**Target duration: 30-40 seconds max.** One sharp point per video. No filler, no lists of 3 mistakes, no multi-step breakdowns.

### Hook Rules

**What works:**
- Specific, visual, personal result in first sentence
- "Here's what I built and what it does" framing
- Concrete outcomes with specifics (times, numbers, tools)

**What doesn't:**
- Question hooks (high skip rate)
- Generic/negative frames
- Teaching/lecturing tone

### Voice Translation

Scripts should sound like how you actually talk, not how they read on paper:

| Don't write | Write instead |
|-------------|---------------|
| Numbered lists | Connected sentences |
| Technical specifics | Plain language |
| Neutral phrasing | Conversational punches |
| Jumping into content | Transition bridges ("And I know this because...", "Here's the thing") |
| Compact sentences | Expand with emphasis |
| Brand names | "us" / "we" |
| Passive voice | "You" and "I" - direct |
| Perfect grammar | Natural speech ("gonna", "real quick") |

**Filler words to include:** "simply", "because", "literally", "and the thing is", "here's the thing"

**Never include:** "In this video", "Hey guys", marketing buzzwords, hashtags, emoji in scripts.

### Script Structure (30-40s)

```
HOOK (0-3s): Specific personal result. One sentence.
BRIDGE (3-5s): "Because..." or "And I know this because..."
BODY (5-25s): One insight as story or demo. No lists.
CLOSER (25-35s): Bring it back to viewer. "Most people do X. I do Y."
CTA (if applicable): "Comment [word] below and I'll send you..."
```

**No script should exceed 120 words.**

## Instagram Caption Style

Captions follow consistent structure. All lowercase, no hashtags.

**Structure:**
1. **CTA first** - if video has a keyword trigger, lead with it: `comment "keyword" below and i'll send you...`
2. **Core insight** - 1-2 punchy sentences
3. **Supporting points** - key insights from video
4. **Closing line** - reinforces or creates urgency

**CTA rules:**
- If keyword CTA exists: lead with it in quotes. Don't also add follow CTA.
- If no keyword: end with `follow @yourhandle for more.`
- Never use both in same caption.
- Never invent a keyword from the topic.

**Tone:** Direct, confident, no fluff. No emojis. No hashtags.

## Scheduling (via Metricool API)

Reels are scheduled as **trial reels**. Trial reels go to non-followers first, you see performance, then promote to full post if they perform.

**CRITICAL rules:**
- Always use `instagramData.type = "TRIAL_REEL"` (NOT "REEL")
- Always set `shareTrialAutomatically: false`
- Always use Python urllib (not curl) to avoid shell escaping issues with newlines
- Never retry a failed schedule without checking existing posts first
- Upload video to a public host (e.g. tmpfiles.org), use the /dl/ URL

**API request (Python):**

```python
import json, urllib.request

data = {
    "text": "caption text here",
    "publicationDate": {
        "dateTime": "2026-MM-DDTHH:MM:00",
        "timezone": "Your/Timezone"
    },
    "draft": False,
    "autoPublish": True,
    "saveExternalMediaFiles": True,
    "providers": [{"network": "INSTAGRAM"}],
    "instagramData": {
        "type": "TRIAL_REEL",
        "shareTrialAutomatically": False
    },
    "media": ["http://tmpfiles.org/dl/XXXXX/filename.mp4"]
}

url = "https://app.metricool.com/api/v2/scheduler/posts?userId=YOUR_USER_ID&blogId=YOUR_BLOG_ID"
req = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("X-Mc-Auth", "YOUR_TOKEN")
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(f"Scheduled: post ID {result['data']['id']}")
```

**You'll need from Metricool:**
- userId (in your account settings)
- blogId (the connected Instagram account ID)
- API token (X-Mc-Auth header)

**Trial reel workflow:**
1. Schedule as trial reel
2. Update tracker: status to scheduled, set scheduled_date
3. After publish, update status to trial, set posted_date and trial_date
4. Pull trial metrics, update trial_* fields
5. If performance is good, manually promote to full post in Instagram
6. After promotion, update status to promoted, pull full metrics

## Performance Analytics (Metricool)

```python
import json, urllib.request, urllib.parse

token = "YOUR_TOKEN"
params = urllib.parse.urlencode({
    "userId": "YOUR_USER_ID",
    "blogId": "YOUR_BLOG_ID",
    "from": "2026-MM-DDT00:00:00",
    "to": "2026-MM-DDT23:59:59"
})
url = f"https://app.metricool.com/api/v2/analytics/reels/instagram?{params}"
req = urllib.request.Request(url)
req.add_header("X-Mc-Auth", token)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read().decode("utf-8", errors="replace"))

for reel in data["data"]:
    print(f"{reel['publishedAt']['dateTime'][:10]} | "
          f"{reel['views']} views | {reel['likes']} likes | "
          f"{reel['saved']} saves | {reel['shares']} shares | "
          f"reach: {reel['reach']} | avg watch: {reel['averageWatchTime']}s | "
          f"skip: {reel['reelsSkipRate']}%")
```

Fields available: views, likes, comments, saved, shares, reach, impressionsTotal, engagement, averageWatchTime, videoViewTotalTime, durationSeconds, reelsSkipRate, url, reelId.

**Note:** Instagram does not expose follower gain per post via API. Track follower growth separately.
