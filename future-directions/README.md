# Future Directions

Features that are architecturally sound but out of scope for the current release.
Each folder/file here is production-ready code that can be wired in when the time is right.

---

## LinkedIn Direct API — Comment Access & Engagement

**File:** `linkedin_service.py`

### What it does

A full OAuth2 client for LinkedIn's native REST API that allows reading and replying
to comments on your own posts — bypassing Buffer's Publish-only limitation.

Capabilities implemented:
- `authorize()` — browser-based OAuth2 PKCE flow with a local callback server; saves
  tokens to `data/linkedin_tokens.json` (auto-refreshes)
- `get_recent_posts()` — fetches your UGC posts from `/v2/ugcPosts`
- `get_comments(post_url_or_urn)` — fetches top-level comments from `/v2/socialActions/{urn}/comments`
- `get_comment_replies(post_urn, comment_urn)` — fetches threaded replies
- `resolve_person_name()` — best-effort commenter name lookup, cached per session
- `parse_post_url()` — extracts the activity URN from any LinkedIn post URL

### Why it was deferred

Buffer's public GraphQL API (`api.buffer.com`) only exposes the Publish product —
no engagement or comment data is available via that key. Accessing comments directly
through LinkedIn requires:

1. A LinkedIn app with the **Community Management API** product approved
   (`r_member_social` scope for reading; `w_member_social` for replying)
2. A one-time OAuth2 browser flow per user (`python main.py --auth-linkedin`)
3. Credentials stored separately from Buffer (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`)

LinkedIn's API review process for Community Management API can take days to weeks,
making it a dependency risk for an initial handoff.

### How it fits in

Once approved, wire it back into `main.py` with these three flags (already designed):

```bash
python main.py --auth-linkedin          # one-time browser OAuth flow
python main.py --comments               # interactive: pick from recent posts
python main.py --comments --post-url "https://www.linkedin.com/posts/..."
python main.py --comments --with-replies
```

The service reads from `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` in `.env`.
Tokens are saved to `data/linkedin_tokens.json` (gitignored).

### Integration with SSI strategy

Reading comments on your own posts feeds directly into the **Build Relationships**
and **Engage with Insights** SSI pillars — you can surface what resonates, identify
who's engaging, and generate targeted follow-up content. A natural next step after
wiring this in would be a `--reply-suggestions` command that uses the avatar's voice
to draft replies to open comments.

### Setup checklist (when ready)

1. Go to https://www.linkedin.com/developers/apps → New app
2. Under Products, request **Share on LinkedIn** + **Community Management API**
3. Under Auth, add redirect URL: `http://localhost:8080/callback`
4. Set in `.env`:
   ```
   LINKEDIN_CLIENT_ID=your_client_id
   LINKEDIN_CLIENT_SECRET=your_client_secret
   LINKEDIN_REDIRECT_PORT=8080
   ```
5. Move `future-directions/linkedin_service.py` → `services/linkedin_service.py`
6. Restore the four CLI flags in `main.py` (see git history)
