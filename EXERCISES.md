# Practice Session: mirrors the Datadog 90-min format

Set a timer for each phase and **talk out loud the whole time**. If you can,
record yourself. Do the phases in order: phase 3 reveals phase 2's answer.

| Phase | Time | What you do |
|---|---|---|
| 0. Project story | 5 min | Tell your project story out loud (problem, what you built, one tradeoff, teamwork, impact) |
| 1. Explore | 20 min | Understand the codebase and how data reaches the UI |
| 2. Design | 25 min | Design the feature in `docs/SPEC_categories.md`, verbally |
| 3. Review | 25 min | Review the PR on branch `pr/categories-summary` |
| Bonus | 15 min | Design `docs/SPEC_transfers.md` |

---

## Phase 1: Explore (20 min)

**Step A: Before opening any code (5 min).** Run the app and click around.
Out loud, answer these:
1. What resources do you think exist?
2. Which endpoints probably power the account list, the account detail
   view, the filter dropdown, "Load more", and the "Add transaction" form?
   Give the method, path, and query params or body for each.
3. Where do you think the balance comes from?

Tip: open your browser's DevTools, go to the Network tab, and watch the
requests. Say your guess *before* looking.

**Step B: Confirm in the code (15 min).** Answer out loud:
1. Where does the app start, and where are the routes registered?
2. Trace `GET /api/accounts/acc_1/transactions?limit=10&type=debit`
   end-to-end, from the route through the store and back to JSON on the
   page.
3. What data structures hold the data? What does it cost to look up one
   transaction by id? To list one account's transactions?
4. How does pagination work? Is it offset or cursor? What does the cursor
   actually contain, and why doesn't a new transaction break it?
5. How is the balance computed? When does it change?
6. What stops a retried POST from creating a duplicate transaction? Is
   there a gap in that protection?
7. What conventions would a new endpoint need to follow? Consider the error
   format, validation, status codes, and where logic lives.
8. Name one thing you'd flag if you owned this code.

**Also practice:** write one new test in `tests/test_api.py` and run it,
for example a test that a malformed cursor returns `400`.

## Phase 2: Design (25 min, no code)

Read `docs/SPEC_categories.md`. Talk through:
1. **Clarify:** what's ambiguous? Ask at least 2 questions, then state your
   assumptions.
2. **Data model:** what changes in `Transaction`, the CSV, and the loader?
   What about existing rows?
3. **Endpoints:** give the method, path, body, response, and status codes,
   including errors. Is each one idempotent?
4. **Fit:** how does this follow the existing codebase's patterns?
5. **Hard parts:** how do you *persist* a category change when the
   transactions CSV is append-only? How do you keep the summary from
   scanning every transaction?
6. **Tests:** name the tests you'd write.

## Phase 3: Review a PR (25 min)

```bash
git log --oneline --all            # see the PR branch
git diff main pr/categories-summary
cat docs/PR_DESCRIPTION.md         # on the PR branch
```

Or read `pr/categories-summary.diff` if you'd rather not use git.

Process:
1. **Reread the spec first.** List every "must", "must not", and "only".
2. Check **completeness**: does the PR do everything the spec asked?
3. Check **correctness**: does the code work, including edge cases?
4. Check **efficiency**: is anything iterating when it doesn't need to?
5. Check the tests: what's missing?
6. For each issue, give the location, the problem, the impact, and the
   fix, and say whether it **blocks** the PR or is a **nit**.
7. **Verify** at least two issues. Check out the branch and prove the bug
   with a curl command or a failing test.

```bash
git checkout pr/categories-summary
python -m pytest -q                # the PR's own tests pass... that's the trap
```

Then check your list against `answers/ANSWER_KEY.md`.
