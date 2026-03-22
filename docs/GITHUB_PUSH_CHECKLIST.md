# GitHub Push Readiness Checklist

Final checklist before pushing to a public repository.

---

## Code Quality

- [ ] `cd backend && pytest --tb=short -q` → **141 passed**
- [ ] `cd frontend && npm run test -- --run` → **190 tests passed**
- [ ] `cd frontend && npm run build` → exits 0
- [ ] `cd frontend && npm run lint` → exits 0
- [ ] `cd frontend && npx playwright test` → **14 passed** (run `npx playwright install chromium` first if needed)

## README

- [ ] `README.md` written, final quality, all 13 sections present
- [ ] Screenshot image paths match files in `docs/images/`
- [ ] Test counts in README match `CURRENT_STATE.md` (141 / 190 / 14)
- [ ] No exaggerated claims — every number is verifiable from source-of-truth docs

## Screenshots

- [ ] All 7 screenshots captured per `docs/SCREENSHOT_CAPTURE_PLAN.md`
- [ ] Files placed in `docs/images/` with correct filenames
- [ ] Images are reasonable size (< 500KB each; compress if needed)
- [ ] No sensitive data visible (no API keys, no real user data, no production URLs)

## Documentation Alignment

- [ ] `PROJECT.md` — architecture and phase table match current state
- [ ] `DECISIONS.md` — no stale constraints; evaluation/metrics decisions up to date
- [ ] `TASK.md` — reflects Phase 6 done + next-task suggestions
- [ ] `CURRENT_STATE.md` — test counts, feature list, automated checks table correct
- [ ] `DEMO_SCRIPT.md` — walkthrough matches actual UI flow

## Repository Hygiene

- [ ] No `.env` files committed (only `.env.example` files)
- [ ] No `node_modules/`, `__pycache__/`, `.venv/`, `dist/` in git
- [ ] No credentials or API keys anywhere in tracked files
- [ ] `test.txt` in root — removed if it's junk
- [ ] `.gitignore` covers standard exclusions
- [ ] `LICENSE` file present (MIT)

## Git State

- [ ] `git status` shows no unexpected untracked files
- [ ] `git diff --stat` shows only intended changes
- [ ] Clean commit with descriptive message
- [ ] Branch is ready to push (or is `main`)

---

## Push

```bash
cd /Users/samarthshete/Desktop/ContextLens

# Stage files
git add README.md docs/images/ docs/SCREENSHOT_CAPTURE_PLAN.md docs/LOCAL_VERIFICATION_CHECKLIST.md docs/GITHUB_PUSH_CHECKLIST.md DEMO_SCRIPT.md

# If screenshots are captured:
git add docs/images/*.png

# Review what's staged
git diff --cached --stat

# Commit
git commit -m "Prepare repository for public release: README, screenshots, verification checklists"

# Push
git push origin main
```
