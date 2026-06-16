# Instagram Carousel

Generate a branded Instagram carousel. Request: $ARGUMENTS

---

## Input Parsing

Parse `$ARGUMENTS` to determine the input type:

- **YouTube URL** (contains `youtube.com` or `youtu.be`): Pull transcript, extract key insights
- **Topic string** (anything else): Research the topic, write original content

If no arguments, ask the user what topic they want a carousel about.

---

## Pipeline

Run stages 1-3 automatically, then STOP for user approval before rendering.

### 1. INPUT

**If YouTube URL:**
- Extract the video ID from the URL
- Pull transcript using `youtube-transcript-api`:
  ```bash
  cd "$CLAUDE_PROJECT_DIR" && python3 -c "
  from youtube_transcript_api import YouTubeTranscriptApi
  ytt = YouTubeTranscriptApi()
  transcript = ytt.fetch('<VIDEO_ID>')
  text = ' '.join([s.text for s in transcript.snippets])
  print(text)
  "
  ```
- Extract the video title and transcript text

**If topic string:**
- Use the topic directly as the content brief

### 2. RESEARCH

- Search for relevant context, stats, and facts about the topic using web search
- Find 3-5 relevant images using web search (product screenshots, diagrams, relevant visuals)
- Download images to `carousels/workspace/<carousel-name>/reference/`
- Name images descriptively (e.g., `ai-dashboard.jpg`, `comparison-chart.png`)

### 3. WRITE + PREVIEW

Structure the content into carousel slides, then present a **text preview** for the user to approve before rendering.

**Slide 1 (hook):** Bold, attention-grabbing statement. 1-2 sentences max. **Must always have an image** (YouTube thumbnail, product screenshot, or relevant hero image). Optional subtitle for secondary context.

**Slides 2-7 (body):** Mix of:
- Text-only slides for key statements
- Bullet slides for lists/comparisons (max 4 bullets per slide)
- Image slides for visual evidence
- Use section titles to create structure
- Use `*asterisks*` around keywords to highlight in accent color

**Last slide (CTA):** Call to action with `button_text` (e.g., "Follow for more")

**Rules:**
- 5-8 slides total (including hook and CTA)
- Hook slide must always have an image (never text-only)
- Every 2nd-3rd slide should have an image
- Keep text concise - people swipe, not read
- Max ~150 characters per text block
- Max 4 bullets per slide
- Body text renders in bold (Inter Bold) - write accordingly (short, punchy lines)

**>>> STOP HERE. Present the slide plan to the user as a numbered list:**

```
Slide 1 (hook): "Hook text here"
  - Image: description of what image will be used
  - Annotation: "annotation text"

Slide 2 (body): Title: "Section Title"
  - Text: "Body text here"
  - Bullets: ["bullet 1", "bullet 2"]
  - Image: description
  ...

Slide N (cta): "CTA text"
  - Button: "Follow for more"
```

Ask: **"Here's the slide plan. Want me to change anything before I render?"**

Wait for the user to approve or request changes. Iterate on the text plan until they're happy.

### 4. CONFIG + IMAGES

After user approves the slide plan:

- Create the workspace directory: `carousels/workspace/<carousel-name>/`
- Download any reference images needed
- Generate `config.json` (see Config Schema below)

### 5. RENDER

```bash
cd "$CLAUDE_PROJECT_DIR"
python3 carousels/render.py "carousels/workspace/<carousel-name>"
```

### 6. REVIEW

After rendering, read each slide PNG and display them to the user.

Present a summary:
- Total slides
- Slide-by-slide breakdown (type, has image, text preview)
- Ask: "Happy with this? Any changes needed?"

**If changes requested:**
- Edit the config.json as needed
- Add/swap/regenerate images in reference/ if needed
- Re-run the render script
- Show updated slides

---

## Config Schema

File: `workspace/<carousel-name>/config.json`

```json
{
  "title": "Carousel Title (for reference only)",
  "profile": {
    "display_name": "Your Name",
    "handle": "@yourhandle"
  },
  "theme": "dark",
  "slides": [
    {
      "type": "hook",
      "text": "Bold hook statement with *accent words*.",
      "subtitle": "Optional smaller subtitle text.",
      "image": "hook-image.jpg",
      "annotation": "optional handwritten note"
    },
    {
      "type": "body",
      "title": "SECTION TITLE",
      "text": "Body paragraph with *accent words*.",
      "image": "asset:youtube-logo.png",
      "bullets": ["Point one with *accent*", "Point two", "Point three"],
      "annotation": "handwritten callout"
    },
    {
      "type": "cta",
      "text": "Call to action text.",
      "button_text": "Follow for more"
    }
  ]
}
```

### Slide Types

| Type | Purpose | Fields |
|------|---------|--------|
| `hook` | First slide, grabs attention | `text` (required), `image` (required), `subtitle` (optional), `annotation` (optional) |
| `body` | Content slides | `text`, `title`, `bullets`, `image`, `annotation` (all optional, at least one required) |
| `cta` | Last slide, call to action | `text` (required), `button_text` (optional) |

### Field Notes

- `image`: filename relative to `reference/` directory, or `asset:<filename>` to load from the shared `assets/` folder
- `title`: rendered uppercase in Bebas Neue with accent underline bar
- `text`: supports `*accent words*` syntax for colored highlighting
- `subtitle`: hook slides only, rendered smaller in gray below the main text
- `bullets`: array of strings with `*accent*` support, rendered with colored dots
- `button_text`: renders a magenta pill button on CTA slide
- `annotation`: handwritten Caveat text with a curved arrow pointing down toward content

---

## Voice & Tone

When writing carousel content, aim for:
- Direct, confident, no fluff
- Data-driven when possible (specific numbers > vague claims)
- Slightly provocative hooks that challenge assumptions
- Educational but not preachy
- Short sentences, clear structure

Customize this section to match your own brand voice.
