# LinkedIn SSI Booster — Claude Code Guide

## Session startup

**Step 1 — Check active tasks.** Read the working context before doing anything else:

```
context/active/tasks.md
```

This file is in the repo root, gitignored, and crash-safe. It tracks exactly what was in flight, what's in the Buffer queue, and what comes next. If active work is listed, pick up from there — do not ask the user to re-explain context.

**Update `context/active/tasks.md` periodically during a session** — after each meaningful step (post created, image uploaded, script run, decision made). Don't wait until session end or the update will be lost if something interrupts.

**Step 2 — Check key expiry.**

```
python main.py --check-expiry
```

This checks whether any tracked API keys are within 10 days of expiry and fires a one-per-day warning if so. It is safe to run and exits immediately if nothing is expiring.

If the output shows a `[KEY EXPIRY]` or `[KEY EXPIRED]` line, rotate the key immediately and update `.env` before proceeding with any other task.

## Working context (crash-safe task tracking)

All in-progress work lives in `context/active/tasks.md` (gitignored). Structure:

```
context/
  active/
    tasks.md       ← THE file: queue snapshot, in-flight work, next actions, image URLs
  archive/
    YYYY-MM-DD_session.md   ← completed session summaries (move here when a wave is done)
```

**Rules:**
- Update `context/active/tasks.md` after each meaningful step, not just at session end
- When a content wave is fully live (all posts published + reconcile run), move its section to `context/archive/YYYY-MM-DD_wave_N.md` and trim `tasks.md`
- Never delete uploaded image URLs from the table — they are permanent links

## Standard workflow commands

These are the canonical commands. Use them (not ad-hoc variations) so the learning loop accumulates correctly.

### Curate (fetch + classify + generate ideas)
```
python main.py --curate --classify
```
`--classify` runs Model2Vec article classification before generation. Always include it — it builds SSI-component balance data over time. Add `--learn` when a batch of articles is unusually rich to extract facts into `extracted_knowledge.json`.

### Schedule (generate + push to Buffer queue)
```
python main.py --schedule --week N --channel linkedin
```
Add `--dot-report` if a post feels off or under-grounded — shows evidence breakdown per post. Add `--avatar-explain` to see exactly which facts were used.

### After posts go live (run weekly)
```
python main.py --reconcile
python main.py --ingest-history
```
`--reconcile` matches published Buffer posts to the candidate log and labels them accepted/rejected, building Bayesian acceptance priors. `--ingest-history` updates voice samples from published posts. Run both within a day or two of a publishing batch going live — do not wait weeks or the matching window closes.

### After ingesting LinkedIn comments export
```
python main.py --ingest-comments --comments-csv Comments.csv
```
Run whenever a fresh `Comments.csv` is exported from LinkedIn. File lives at root (gitignored).

### Console (interactive persona chat)
```
python main.py --console
```
Add `--verify` to enable DoT + spaCy similarity checks on each reply (slower but shows grounding quality).

### Category management (run once when adding new content pillars)
```
python main.py --list-categories
python main.py --add-category "CanadianInnovation" "Canadian tech ecosystem and policy" BUILD
python main.py --remove-category CanadianInnovation
```

## Key environment variables

| Variable | Purpose |
|---|---|
| `BUFFER_API_KEY` | Primary Buffer account (LinkedIn, X, Threads, YouTube) |
| `BUFFER_API_KEY_B` | Secondary Buffer account (Facebook, Instagram, Bluesky) |
| `BUFFER_API_KEY_B_EXPIRES` | ISO date of secondary key expiry (e.g. `2026-08-09`) |
| `OLLAMA_BASE_URL` | Ollama endpoint (default `http://localhost:11434`) |
| `OLLAMA_THINK` | Thinking mode: `false` \| `low` \| `medium` \| `high` |
| `CURATE_CLASSIFY` | Set `true` to auto-classify on every `--curate` (alternative to passing `--classify` manually) |
| `AVATAR_CONFIDENCE_POLICY` | `strict` \| `balanced` \| `draft-first` (default: `balanced`) |

## Channel routing

- **Primary account** (`BUFFER_API_KEY`): `linkedin`, `x`, `threads`, `youtube`
- **Secondary account** (`BUFFER_API_KEY_B`): `facebook`, `instagram`, `bluesky`

The routing is automatic. Running `--channel facebook` will use `BUFFER_API_KEY_B` with the `SOCIAL_SYSTEM_PROMPT` tone (more direct, less polished than LinkedIn).

## Post review files

All draft and final post copy lives in `data/post_reviews/`. Each file contains:
- Draft, critique, and final version for each post
- Buffer IDs and scheduled dates
- Prompt rules and persona changes derived from feedback

Do not regenerate posts that already have a `### Final Version` section unless explicitly asked.

## Critical rule: no duplicate images across Buffer posts

**Every Buffer post that goes live must have a unique image. Never reuse the same image on more than one post within the same platform.**

**Why:** If a follower sees the same photo twice, they assume it is the old post and scroll past without registering it as new content. The image is the first signal. A repeated image kills reach before the copy is even read.

**Enforcement checklist (run before any `--apply` or schedule step):**
1. List every image URL or local path assigned to each queued post.
2. Group by platform (LinkedIn, Threads, X, Facebook, Instagram, Bluesky separately).
3. Within each platform, every image must be unique — no file path or URL may appear twice.
4. Cross-platform reuse within the same wave (same article, same day) is acceptable but should still be minimised where distinct images exist.

**The `_apply_post_images.py` script enforces this at runtime** — it will exit before making any API calls if a duplicate is detected within a platform.

**When building a new image map:** assign images in order of uniqueness priority — release post gets the header, each follow-up gets a distinct inline image. If you run out of unique images, generate new ones rather than reusing.

## Image update workflow

To attach new images to existing queued Buffer posts:
```
python scratch/_apply_post_images.py            # dry-run: shows plan
python scratch/_apply_post_images.py --apply    # uploads to freeimage.host + patches Buffer
```
No extra API keys required — only `BUFFER_API_KEY` and `BUFFER_API_KEY_B` from `.env`.

**Image hosting:** Upload to freeimage.host via base64 POST. Key: `6d207e02198a847aa98d0a2a901485a5`. Returns permanent `iili.io` URLs. 0x0.st is permanently down; catbox.moe now requires auth.

```python
def upload_image(path):
    import base64, requests
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = requests.post("https://freeimage.host/api/1/upload",
        data={"key": "6d207e02198a847aa98d0a2a901485a5", "action": "upload",
              "source": b64, "format": "json"}, timeout=120)
    return resp.json()["image"]["url"]
```

## Buffer API patterns (hard-won — do not re-derive)

The Buffer GraphQL API is at `https://api.buffer.com`. Use `services/buffer_service.py` → `buf._query(gql, vars)`.

**Channel IDs are hardcoded** in `memory/reference_buffer_channel_ids.md`. Never call the discovery API when you already have them.

### Querying posts

Never use `post(id: $id)` — that argument does not exist. Always use the `posts` query:

```graphql
query GetPosts($input: PostsInput!, $first: Int) {
  posts(input: $input, first: $first) {
    edges { node { id dueAt status text assets { ... on ImageAsset { source } } } }
  }
}
```
Variables: `{ "input": { "organizationId": org_id, "filter": { "channelIds": [cid], "status": ["draft","scheduled"] } }, "first": 50 }`

- `status` accepts: `"draft"`, `"scheduled"`, `"sent"` — include `"sent"` when editing recently-published posts
- **ImageAsset fields:** `source` = image URL (string), `thumbnail` = string, `image` = nested `ImageMetadata` object with no URL
- Asset URL to pass into createPost/editPost: `{ "image": { "url": source_url } }`

### Creating posts (`createPost`)

```python
buf._query(CREATE, {"input": {
    "channelId": channel_id,
    "text": text,
    "schedulingType": "automatic",
    "mode": "customScheduled",
    "dueAt": "2026-06-02T16:00:00.000Z",  # UTC ISO8601
    "saveToDraft": True,
    "assets": [{"image": {"url": image_url}}],  # omit if no image
    "metadata": { ... },  # platform-specific, see below
}})
```

### Editing posts (`editPost`)

`EditPostInput` requires `id`, `schedulingType`, `mode`, and `dueAt` even for text-only edits. Always fetch the current `dueAt` first (via the posts query above), then pass it back unchanged.

```python
buf._query(EDIT, {"input": {
    "id": post_id,
    "text": new_text,
    "schedulingType": "automatic",
    "mode": "customScheduled",
    "dueAt": fetched_due_at,
    "saveToDraft": is_draft,
    "assets": [{"image": {"url": source_url}}],  # re-pass if post has an image
    "metadata": { ... },  # required for FB/IG, see below
}})
```

Editing a sent post returns `"Account is not allowed to perform this action"` — this is expected, not a bug.

### Platform-specific metadata

Facebook and Instagram posts require `metadata.{platform}.type = "post"`. Instagram also requires `shouldShareToFeed`.

```python
# Facebook
"metadata": {"facebook": {"type": "post"}}

# Instagram
"metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}}
```

Bluesky: **300 character limit total** (Buffer counts full URL length, not a short version). Keep text + `\n\n` + URL under 300 chars.

### Mutation response shapes

```graphql
# createPost
{ createPost { ... on PostActionSuccess { post { id } } ... on MutationError { message } } }

# editPost
{ editPost { ... on PostActionSuccess { post { id status dueAt } } ... on MutationError { message } } }
```

Check `"message" in result.get("editPost", {})` to detect errors.

## B-channel post generation rules

These rules apply whenever generating or scheduling posts for Account B (Facebook, Instagram, Bluesky):

### Word to avoid: "map"
Do **not** use the word "map" (or "mapping") in any generated post copy. This includes phrases like "structural map", "ecosystem map", "map the landscape", etc.

**Why:** "Mapping the ecosystem" is a well-worn failure mode — passive, never maintained, never addresses the underlying broken incentive structures that made the ecosystem illegible in the first place. Nobody is sufficiently motivated to maintain a passive map. The word evokes cynicism, not credibility.

**When reviewing or editing copy:** If the word "map" appears (including in older drafts), replace it. Acceptable substitutes: "diagnosis", "architecture", "structural analysis", "framework", "the actual answer", "what comes next".

Exception: may appear in a critique of others doing exactly this ("endless ecosystem mapping exercises that go nowhere").

### Link policy
- **Never use LinkedIn shortened links (lnkd.in/...) on any channel other than LinkedIn.**
- Always use the canonical source URL — Substack article URL, GitHub, etc.
- FH article URL: `https://networkforappliedtech.substack.com/p/fracturing-hyperreality`
- RIP series URLs follow the pattern: `https://networkforappliedtech.substack.com/p/<slug>`

### Instagram link policy
- **Never put URLs in Instagram post captions.** Instagram does not render them as clickable links — they appear as dead text.
- Always end Instagram captions with "link in bio" (or "link in bio." as the last line before hashtags) when linking to an article.
- The actual URL belongs in the Instagram profile bio. Update the bio link (or Linktree stack) when a new article wave goes out.
- If Linktree API is wired up: push the new article URL to Linktree as part of the same post-generation script that schedules Buffer posts.
- This rule applies to all Instagram posts regardless of content type — FH, RIP, or any future series.

### Image policy
- **Facebook and Bluesky**: Pull the header image (or most relevant inline image) directly from the Substack article. Attach via `assets: [{ image: { url: "..." } }]` in the Buffer API.
- **Instagram**: Leave as a Buffer Idea by default — image must be manually curated before scheduling. Exception: if the user explicitly approves a Substack image for a specific Instagram post, create it as a scheduled post with that image attached.
- Substack S3 image URLs are permanent: `https://substack-post-media.s3.amazonaws.com/public/images/<id>.<ext>`
- Use the substackcdn.com proxy URLs only as a fallback.

### Scheduling policy
- Posts scheduled for tomorrow should be rescheduled to **now + 1 hour** when pushing a batch forward.
- Instagram ideas have a target date noted in their text — move them to scheduled when an image is confirmed.

## Private repo only

This repo should **not** be pushed to any public upstream. Push only to the private origin remote.
