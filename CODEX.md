# Codex Agent Guide — LinkedIn SSI Booster

This project runs two kinds of tasks: **social post generation** (Python + Ollama, handled by Claude Code) and **image generation** (your native image tool). This file covers the image generation workflow — the primary reason Codex is invoked here.

---

## Image Generation

### How it works

Every generation script in `scratch/` exposes an `IMAGE_SPECS` list — a list of dicts with:

```python
{
    "label":       "human-readable description",
    "prompt":      "full image generation prompt (CLIP/T5 front-loaded for FLUX)",
    "output_path": "data/images/running_in_place/rip0_header_v2a_square.png",
    "width":       1024,
    "height":      1024,
}
```

**Your job:** read `IMAGE_SPECS`, generate each image using your native image tool at the specified dimensions, and save to `output_path`. Create any missing output directories before saving.

### Finding the right script

| Article | What to generate | Script |
|---|---|---|
| RIP #0 header v1 | Original circular groove concept | `scratch/_gen_rip0_header.py` |
| RIP #0 header variants | Three variant concepts (A/B/C — pick one to generate or all) | `scratch/_gen_rip0_header_variants.py` |
| RIP #0 inline image | "The Empty Machine" cross-section | `scratch/_gen_rip0_inline_machine.py` |
| RIP #2 header | "The Black Hole Economy" | `scratch/_gen_rip2_header.py` |

Status of what's been generated vs. pending: `data/image_strategy/series/running_in_place.md`

### Visual style rules (read before generating)

`data/image_strategy/visual_style.md` — the full design system. Key rules:

- **Palette**: charcoal `#1C1C1E`, mint green `#A8D8B9`, warm cream `#F5F0E8`, dusty rose `#D4A5A0`, slate blue `#7A9BB5`. Never pure white or pure black.
- **Style**: flat 2D / 2.5D illustration. No photographic realism. No 3D render.
- **Every header needs**: an interesting stage, 2–6 small human figures, in-frame props, one luminous mint green focal element, film grain/halftone texture.
- **Perspective**: isometric axonometric (preferred), top-down aerial, or eye-level.
- **Left third clear**: landscape banners need the left third free for Substack title overlay.

### Output naming convention

```
rip{article_number}_{type}_{variant}.{ext}
```

- `type`: `header`, `inline`, `chart_bar`, `diagram`
- `variant`: `v1`, `v2a`, `v2b`, `v2c`, `approved`
- Output directory: `data/images/running_in_place/`

### Variants script — single vs. all

`scratch/_gen_rip0_header_variants.py` contains three variant specs (keys `a`, `b`, `c`). If the user asks for a specific variant, generate only that entry from `IMAGE_SPECS`. If no variant is specified, generate all three.

### What Codex does NOT handle here

- **Matplotlib charts** (`scratch/_gen_rip0_diagrams.py`) — these are Python-only, no `IMAGE_SPECS`. Run as a Python script or ask Claude Code to run them.
- **Social post scheduling** — handled by `main.py` and Claude Code. Do not modify Buffer posts or `.env`.
- **FLUX model downloads** — local GPU setup. Not relevant to your workflow.

---

## If you need more context

- Full image workflow status: `data/image_strategy/series/running_in_place.md`
- Design aesthetic and prompt strategy: `data/image_strategy/visual_style.md`
- Active task list (what Claude Code was working on): check `CLAUDE.md` for memory folder location
