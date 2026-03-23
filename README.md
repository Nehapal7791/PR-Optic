# PR-Optic
 
 AI-powered code review assistant for GitHub pull requests.
 
 PR-Optic analyzes PR diffs, generates **line-specific inline review comments**, and can **post them directly to GitHub** in a professional “senior engineer” style.
 
 ## Key capabilities
 - **Two-pass review**
   - **Triage**: choose relevant concern categories.
   - **Focused review**: generate actionable, line-specific feedback.
 - **GitHub inline comments (line-specific)**
   - Posts comments on the exact file + line where the issue is found.
   - Professional format (no icons/emojis in comment bodies).
   - Each inline comment ends with: `Reviewed by PR-Optic`.
 - **Fix verification / re-review routing**
   - If open issues exist for a PR, PR-Optic routes to verification on the next run.
 - **Dashboard UI (Streamlit)**
   - Trigger reviews.
   - Optionally post comments to GitHub.
   - Track review status and filter issues by category/severity.
 - **State persistence**
   - Tracks open issues across PR lifecycle using SQLite-backed state.
 
 ## Quick start
 
 ### 1) Install
 ```bash
 uv sync
 ```
 
 ### 2) Configure environment
 ```bash
 cp .env.example .env
 ```
 
 Populate `.env` with:
 - `GITHUB_TOKEN`
 - `GITHUB_WEBHOOK_SECRET` (only needed for webhook mode)
 - AI provider keys (depending on provider)
 
 ### 3) Run the API
 ```bash
 uv run uvicorn src.main:app --reload --port 8000
 ```
 
 ### 4) Run the dashboard
 ```bash
 streamlit run dashboard_enhanced.py
 ```
 
 ## Dashboard usage
 
 1. Open the dashboard.
 2. Go to `Review PR`.
 3. Enter:
    - `owner`
    - `repo`
    - `PR number`
 4. Enable (optional): `Post comments directly to GitHub`.
 5. Start review.
 
 When GitHub posting is enabled, PR-Optic will:
 - Post **one inline comment per issue** on the relevant file/line.
 - Post a **review summary** as the PR review body.
 
 ## API usage
 
 ### Trigger a review
```bash
curl -X POST "http://localhost:8000/api/reviews" \
  -H "Content-Type: application/json" \
  -d '{"owner":"OWNER","repo":"REPO","pull_number":123}'
```

By default, this endpoint will post review comments to GitHub (see `post_to_github`).
 
 ### Trigger a review and force GitHub posting
 Use the query parameter:
 ```bash
 curl -X POST "http://localhost:8000/api/reviews?post_to_github=true" \
   -H "Content-Type: application/json" \
   -d '{"owner":"OWNER","repo":"REPO","pull_number":123}'
 ```
 
 Notes:
 - GitHub may reject reviews on your **own PR**.
 - GitHub may reject inline comments if the line cannot be resolved in the diff.
 
 ### Get PR review status
 ```bash
 curl "http://localhost:8000/api/reviews/OWNER/REPO/123/status"
 ```
 
 ## Comment style (what is posted to GitHub)
 
 Inline comments are posted without icons/emojis and follow a consistent, professional structure:
 
 ````markdown
**CRITICAL: Security**

**Why this is a problem:**
<clear explanation>

**Impact:** <severity + consequence>

**Suggested fix:**
```text
<code>
```

Reviewed by PR-Optic
````
 
 ## Documentation
 - `CATEGORY_REVIEW_GUIDE.md` - category-by-category senior review guidance.
 - `DASHBOARD_COMPLETE_GUIDE.md` - dashboard usage.
 - `GITHUB_POSTING_PROFESSIONAL.md` - GitHub posting format and examples.
 - `T11_STATE_STORE_COMPLETE.md` - state persistence design.
 - `T12_FIX_VERIFIER_COMPLETE.md` - fix verification behavior.
 - `T13_PROMPT_LIBRARY_COMPLETE.md` - prompt library.
 
 ## Troubleshooting
 - **API offline in dashboard**
   - Start: `uv run uvicorn src.main:app --reload --port 8000`
 - **401/403 from GitHub**
   - Ensure `GITHUB_TOKEN` is valid and has required scopes for repo access and PR commenting.
 - **Inline comment rejected (422)**
   - Usually means the line is not part of the current diff.
