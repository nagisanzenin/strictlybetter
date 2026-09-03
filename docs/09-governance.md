# 09 · Governance and safety

An unattended loop that edits code and spends money needs firm boundaries. This document lists them. They are enforced by the harness where possible and by agent instructions where not.

## 9.1 Two human gates

**Gate 1, before a campaign.** The user sees and confirms: the profile, the proposed goals and guardrails with their measured sigmas and costs, the protected and frozen paths, the budget, and the branch name. The user can edit any of these. Nothing is measured for acceptance and nothing is changed until this gate passes. On Claude Code this is one structured question with the recommended set first.

**Gate 2, after a campaign.** The loop stops at a branch and a report. Merging into main, opening a pull request, tagging, deploying, publishing: human acts. A project may opt in to `auto_pr: true` (open the PR) but never to auto-merge. Not in v1.0: the engine ignores `auto_pr` and never opens a pull request.

Between the gates the loop asks nothing. If it needs a human, it halts and says why.

## 9.2 What the loop may not touch

- **Frozen paths** (the instrument): tests, benches, fixtures, eval scripts, reference outputs. Editable only in an instrument campaign, where the implementation is frozen instead.
- **External instruments** (`external_instruments` in the campaign spec, `integrity.external_paths` on a card): absolute paths outside the repo, such as a harness in a sibling repository. Content-hashed at `sb campaign start`, re-checked before every decision, and denied to the experimenter by the guard while a campaign runs.
- **Anything outside the scope** (`scope_paths`, when set): in a monorepo the campaign edits one package. Frozen and protected rules apply first; a changed file outside the scope is the integrity violation `scope:<file>`.
- **Protected paths**: CI configuration, secrets and env files, licenses, generated code, anything the user adds. The engine's defaults are `.github/`, `.gitlab-ci.yml`, `.env`, `.env.*`, `*.pem`, `*.key`, `secrets/`, `LICENSE`, `LICENSE.*`, plus the profile's and the campaign's `protected_paths`. Dependency manifests and lockfiles are a separate rule: touching one is an integrity violation unless the hypothesis's operator is `dependency`, and each touched manifest adds one sigma to the threshold.
- **The main branch** and any branch not created by the loop.
- **The network**, beyond package registries needed to build. No deployments, no external services, no telemetry. The engine itself has no network code (the selftest parses its AST for network imports); the agents' network access is the platform's.
- **Its own rules**: `.strictlybetter/metrics/*.json`, `campaign.json`, `baseline.json`, `ratchet.json`, and the harness itself are outside the experimenter's write set. The guard denies the whole state home except `inbox/` and `tmp/`, and `sb submit` fails a diff that touches `.strictlybetter/`.

Enforcement is layered: on Claude Code the PreToolUse hook runs `sb guard --stdin` and denies (exit 2) writes to frozen and protected paths, to external instruments, to files outside `scope_paths` inside a worktree, to the state home, and to anything outside an experiment worktree, while a campaign is running (`SB_GUARD=off` or a `guard.off` file disables it for a human session); on every platform `sb submit` re-checks the diff (frozen, protected, state, and scope) and the eval hash, the external hashes and the card fingerprints are re-verified before `sb measure`, `sb judge`, `sb confirm`, and `sb accept`, and `sb measure` refuses an experiment that failed integrity. The prompt tells the agent the rules; the hook and the hash make them true.

## 9.3 Budgets and the kill switch

- Hard caps on dollars, wall-clock hours, and experiment count (`budget` in the campaign spec; default 40 experiments), plus an iteration cap (200). `sb prereg` charges the experiment count before creating the worktree; `sb measure` and `sb confirm` charge wall-clock even when they fail. Exceeding any cap halts the campaign (`budget:<dimension>`) at the next `sb prereg` or `sb distill-stats`. `sb budget` prints the counters.
- Cost accounting: the orchestrator reports each experiment's token usage with `sb cost <id> --tokens-in --tokens-out [--wall-s] [--dollars] [--tier]`; when `--dollars` is absent the engine estimates from the campaign's `pricing` table (default 5 and 25 dollars per million input and output tokens) and marks the entry `estimated`. When usage is unavailable the loop counts experiments and measurement wall-clock only and the report's dollar figure stays at what was reported.
- A `STOP` file in `.strictlybetter/` (`sb stop` writes it) halts the loop at the next safe point: `sb prereg` refuses to start a new experiment, the Stop-hook driver and `sb drive` stop continuing, and `sb next` says so. `sb campaign resume` removes it.
- A safe point is: no worktree mid-edit, ledger flushed, campaign status written.

## 9.4 Halt conditions (the loop stops itself)

The principle is the Toyota one: the machine stops when it detects a defect rather than continuing to produce. Halt, not discard, on:

- two consecutive integrity violations at `sb submit` (frozen, protected, state, or out-of-scope path touched; eval hash changed; dependency manifest touched outside the `dependency` operator); a clean submit resets the count
- an external instrument whose content hash differs from the one taken at `sb campaign start` (`external-tampered:<path>`), or a metric card that changed or disappeared (`card-tampered:<id>`, `card-missing:<id>`); checked before `sb measure` while running, `sb judge`, `sb confirm`, and `sb accept`
- a goal or guardrail that has no valid baseline or no measured sigma at `sb campaign start` (the world changed under the loop: toolchain update, service down), or a goal whose minimum detectable effect exceeds 50% on this host (`instrument-unusable`; `--allow-unusable` overrides)
- the judge returning `gamed` twice in a row (the hypothesis generator has drifted toward gaming and needs a human look)
- a holdout gap ratio above 0.75 averaged over the last five acceptances (`04-anti-overfitting.md` §4.4)
- budget or iteration cap exhausted (`budget:<dimension>`)
- `sb campaign halt --reason`, the human's own kill switch

Not in v1.0: a halt on three consecutive harness errors (the constant is reserved; the counter is never incremented) and a halt on disk or memory pressure on the measurement host.

Halts are written to `campaign.json` (`status: halted`, `halt_reason`, `halted_at`) and to the ledger, and surfaced at the next session start (`sb session-start` prints one line). `sb campaign resume` clears the halt and the consecutive counters after a human has looked.

## 9.5 Provenance

Every accepted commit contains, in its message, a `strictlybetter provenance` block: the experiment id and campaign, the operator class, the hypothesis, the pre-registration hash, the diff size and touched dependency manifests, each goal's and guardrail's baseline and confirmed value with delta, sigma, and threshold, the judge's verdict and pattern, and the confirmation level, rounds, holdout flag, paired flag, and κ_eff. A change without this block did not come from the loop. Reviewers and future agents can audit any commit without the ledger file.

## 9.6 Secrets and data

- The loop never reads or writes secrets. Protected path defaults include `.env*`, `*.pem`, `secrets/`, and platform credential paths.
- Holdout data for confirmation is stored outside the experimenter's worktree: seed and argument values on the card's confirm level (or in `campaign.json` after a rotation), and `dir` holdouts under `.strictlybetter/holdout/`, copied into the clean checkout at confirm only. The engine never puts them in a worktree or in any experiment-facing output (`sb next`, `sb measure`, `sb judge`); not reading the card file directly is the experimenter agent's instruction boundary, not an engine wall.
- Nothing from the repo is sent anywhere the user's agent platform does not already send it.

## 9.7 What a reviewer should check

The report and the provenance blocks are designed so that review is fast:

1. Are the goals and guardrails the ones I would have chosen? (Gate 1 record.)
2. Did any accepted change touch something surprising? (`diff_lines`, `new_deps`, `files` in `sb ledger view <id>`.)
3. Do the confirmation numbers hold on my machine? (`sb measure <id> --fidelity confirm` reproduces them, and works after the campaign has ended.)
4. What did the judge flag as suspicious, and what extra check cleared it?
5. What did it cost, and what is the cost per accepted improvement?

If any answer is uncomfortable, the branch is discarded and the ledger still teaches the next campaign what not to do.
