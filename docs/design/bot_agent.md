# Bot agent: requirements

Status: built, and tested with a fake model, replay tool and calendar. Not yet run with a real model: this needs
`ANTHROPIC_API_KEY` in `.env` and prices filled in `config/model_prices.json`. Code: `src/driver/agent/`.
Batch-file noise is not built; generated noise is.

This is the design for the **Bot** tab. It replaces section 3 of [chatbot-driver.md](chatbot-driver.md), which was
a first sketch. It follows the client rules in [client-rules.md](client-rules.md), and the domain background in
[prompts/bot/domain.md](../../prompts/bot/domain.md) (a verbatim copy of `CollaborativeAIChatbot/docs/collaborative_domain.md`,
to be copied when the bot is built).

## 1. Purpose

The bot plays members of the five squads in the group chat, the way a real member would. It holds a multi-turn
conversation with the chatbot in order to reach a goal, for example getting a no-crew request handled. Afterwards a
judge checks what happened against the test calendar.

The bot is a client, the same as the batch driver. It talks to the chatbot only through the replay tool
([client-rules.md](client-rules.md)). It reads and changes the calendar only through the test-calendar guard.

You configure it on the Bot tab, start it, and watch it run.

## 2. How the bot connects to the tools (answer: not MCP, for now)

**Recommendation:** the tools are ordinary Python functions in the driver. The model calls them through the
Anthropic Messages API, using tool use. The driver runs each call and returns the result to the model.

Why not an MCP server:

- The bot and the tools run in one process. The window, persona, calendar guard, and limits are enforced in the
  same place the tools live, so the model cannot skip them.
- It needs no second server to start and watch.
- The page can show every tool call as it happens, because the driver makes them.

When MCP would help: if you later want a Claude Code session to use the same tools by hand, wrap the same functions
as an MCP server. The functions stay the same, so this is a small addition, not a rewrite.

## 3. What the bot is told (its system prompt)

**R3.1** The system prompt has four parts, in this order:

1. **Role and rules:** `prompts/bot/system.md`. One global file, used by every goal, edited rarely. Goal files never
   contain system prompt text.
2. **Domain:** `prompts/bot/domain.md`, a verbatim copy of the domain document. Copy it, do not distill it for
   version 1. The bot needs Tango, shift naming, the calendar format, and the "No Crew" rule to write like a member
   and to check results. Keep this copy in step with the chatbot repo, as `client-rules.md` is kept in step.
3. **Roster for this run:** the personas the run may use. Each is a pseudonym, a squad, and a role if known. No real
   names and no sender IDs (section 11).
4. **Scenario:** the brief, the goal and stop condition, the dates, the noise setting, and the limits, as set on the
   Bot tab.

**R3.2** Expected results are never in the bot's prompt (section 9).

**R3.3** The system prompt is global. Every goal relies on it, because it sets the context whatever the goal is.
The goal file is a separate file and holds only the fields in section 4.

## 4. The goal file

A goal is saved in `scenarios/` as its own file, separate from the global system prompt. It has these fields.

| Field | Meaning |
|---|---|
| Brief | What the bot should do, in plain language, as you would brief a member. |
| My squad | The persona the bot writes as first. |
| Other personas | Squads and members the bot may also write as. Empty means only "My squad". |
| Window | The first and last day the bot may post on. Every `sent_at` must fall inside it. |
| Gate date | The day the request is about. Example: Friday, 13 March. |
| Noise | None, some, or heavy (section 7). |
| Goal and stop condition | When the run is done, written so the bot knows when to call `finish`. |
| Expected results | What the judge checks (section 9). Shown to the judge only. |
| Posting allowed | Which posting settings the bot may use (section 5.6). |
| Setup allowed | Whether the bot may change the test calendar to set up a condition (section 8.5). |
| Live calendar | Off: preview only. On: the test calendar may change. |
| Limits | Section 10. |

**R4.1** Two examples the brief must support:

- "Tell the chatbot that Member-2 won't have a crew on Friday."
- "Your squad is challenged with getting a crew for Saturday night. Work it out with the chatbot."

**R4.2** The brief says what the bot is trying to do. It never says what the right answer is. The bot must not know
the expected results, because it could then steer the chatbot toward them and hide a failure.

## 5. How the bot behaves in a conversation

**R5.1** It writes as a member would: short, informal, sometimes vague, sometimes with a typo. It uses squad numbers
the way members do, and it follows the shift naming rule in the domain document: a shift is named for the day it
starts, so "Wednesday night" covers 1800 Wednesday to 0600 Thursday.

**R5.2** It answers the chatbot's questions when they are directed at one of its personas. It asks questions of its
own only when the brief calls for them. It does not answer questions directed at other members.

**R5.3** It writes only as a persona listed for the run. A message from another squad is posted as that squad's
member, using that member's pseudonym. The bot never writes as a squad that is not one of the run's personas.
Every post shows the persona it is written as (pseudonym and squad) in the run view.

**R5.4** It calls `finish` when the stop condition is met, or when a limit is reached. `finish` records a short
reason.

**R5.5** It changes the calendar only through `set_calendar`, and only when the scenario allows setup and live is
on (section 8.5).

**R5.6** Posting settings. Every message carries one. The default is `wait`. The scenario can forbid any of them.

| Setting | Meaning |
|---|---|
| `wait` (default) | Wait for this trace to finish before the next message from anyone. |
| `thread` | Post now. The persona waits for its own reply before posting again. Others may post meanwhile. |
| `none` | Post and move on at once. Only for deliberate crossing messages. |
| `sync` | Wait for every outstanding trace to finish before continuing. |

The driver enforces: a persona does not post again while its last message is unanswered, unless the setting is
`none`. A reply that arrives late is still recorded, and the log shows which message it answers.

**R5.7** The typical shape of a multi-turn scenario, about three or four exchanges:

1. The bot says the squad will have no crew, or the squad is challenged.
2. The chatbot asks which night. The bot answers: "Friday."
3. The chatbot asks whole night or partial. The bot answers: "partial, 0100 to 0200."
4. The chatbot confirms, or asks something else. The bot answers, or finishes.

The brief sets how far the bot goes. "Whole night or partial" is an example, not a required script.

## 6. Dates and the gate

**R6.1** The bot chooses each `sent_at`. The driver refuses any value outside the window. This is enforced in code.

**R6.2** When a message names a date, the driver warns if `sent_at` is after that date, or more than a set number of
days before it. It warns and does not block, because some wording is legitimately about the past.

**R6.3** The days that matter for the run are collected by the driver from three sources: the gate date, the dates
named in the bot's messages, and the dates in the chatbot's replies and traces. These are the **days in question**,
and the calendar snapshots in section 8 are taken for them.

## 7. Noise from other squads

**R7.1** Noise levels:

- **None:** only the scenario's own messages.
- **Some:** a few unrelated messages from other personas during the conversation, such as an ordinary shift swap
  for a different day.
- **Heavy:** many messages from several squads, including some that touch the same squad or the same day.

**R7.2** Noise comes from one of two sources, chosen per scenario:

- **Generated:** the bot writes it as other personas. This gives variety.
- **From a batch file:** the messages come from a saved `.jsonl` batch, interleaved at set points. This repeats
  exactly, so it is the choice for regression runs.

**R7.3** Noise messages are posted through the same path as the scenario's messages. In the run view they show the
persona they are written as, the same as any other post. Each one counts toward
`max messages`. Noise uses the `none` or `thread` setting only, unless the scenario allows more.

**R7.4** A noise message must not change the scenario's facts unless the scenario says it may. For example, it must
not cancel the no-crew request the bot is trying to make.

## 8. The calendar: before, after, and the judge's snapshots

This is the part that decides whether the judge can verify what happened.

**R8.1** Snapshots are taken by the driver's code, not by a model. A snapshot is the calendar service's raw answer
for each day in question, saved unchanged. Nothing summarises it.

**R8.2** The sequence for one run:

1. **Plan.** The tester writes a one-line plan before it posts anything: what it intends the chatbot to change, and
   on which day. Example: "I'm going to try to remove squad 54's crew for Wednesday night, 1800 to 0600."
2. **Before.** The judge receives the plan and the expected results. It takes its own snapshot, labelled `before`, for
   the days in question. It also writes the checks it will make later (section 9.3). Both are fixed before the
   conversation starts.
3. **Run.** The tester runs the conversation (section 5), with any setup steps (section 8.5) first.
4. **After.** When the last trace is final, the driver takes a snapshot labelled `after` for the same days. The judge
   may take more snapshots at any time, with its own label, for example `after-retry`.
5. **Verdict.** The judge reads the record, the transcript, the outbox, and the trace steps, and gives its verdict.

**R8.3** The driver computes the difference between each pair of snapshots, for each day, in code. The judge sees
the raw snapshots and the difference, and it may not change either.

**R8.4** The judge's snapshot tool only reads. It is the driver's snapshot function, called with a label, so the raw
answer is saved the same way as the driver's own.

**R8.5** Setup steps (the bot sets up a condition before or during the run) are written to the log with the calendar
state before and after each one. They are allowed only on the test calendar (port 7007), and only when the scenario
allows setup. The guard refuses any other address in code, not by instruction.

**R8.6** Production (port 8007) is never read or changed by the bot or the judge. This is enforced in code.

## 9. Expected results and the judge

**R9.1** The expected results are written by you, with the scenario. The tester does not see them. The judge does.

**R9.2** The judge uses a stronger model than the tester. Its default is in section 13.

**R9.3** The judge works in two calls, in the same conversation, so it commits to its checks before it sees the
result:

- **Before the run:** given the plan and the expected results, it writes the checks it will make. A check says what
  it will look at (for example, "the calendar line for Wednesday after the run shows squad 54 as No Crew from 1800"),
  and where (raw snapshot, reply, or trace step). It also takes its `before` snapshot.
- **After the run:** given the transcript, the raw snapshots, and the difference, it gives a verdict on each check,
  and on each expected result.

**R9.4** Each verdict has these fields:

| Field | Meaning |
|---|---|
| `check` | What was checked, as written before the run. |
| `verdict` | `pass`, `fail`, or `unclear`. |
| `evidence` | The quote, calendar line, or trace step it relied on. |
| `reason` | One or two sentences. |

**R9.5** A verdict with no evidence is recorded as `unclear`. `unclear` is shown apart from `fail`, so a missing
check is not counted as a bug.

**R9.6** The judge reports the chatbot's replies and the calendar as two separate results. "The reply was right, but
the calendar was not changed" is a valid and important finding, and so is the reverse.

**R9.6a** Confirmations are optional. The administrator does not always reply after a change, though the calendar is
always updated. So for a calendar change, the calendar is the evidence: the judge verifies the change there, and it
does not count a missing confirmation as a failure. A confirmation is checked only when the goal asks for one. The
chatbot's `announce_results` policy stays off for this reason.

**R9.7** The judge checks the calendar against the domain rules. For example: a squad with no crew stays in the
entry as "No Crew"; the entry is split at the partial-shift boundary; the other squads' territories and Tango are
recalculated for the affected hours. The domain document is the reference.

**R9.8** The judge has these tools, and no others:

- read the test calendar for any date (read only),
- take a labelled snapshot of a day (through the driver),
- read the transcript, the outbox, and the trace steps.

It cannot post messages, change the calendar, or change its own instructions.

**R9.9** Later, deterministic checks can sit beside the judge: for example, "squad 54 has no crew 1800 to 0600 on this
date" as a plain comparison with no model. When both exist, a deterministic result decides pass or fail, and the
judge's verdict is shown beside it.

## 10. Limits, cost, and the kill switch

**R10.1** Each run has these limits, set on the Bot tab and saved with the scenario:

- maximum messages posted to the chatbot,
- maximum model calls (turns), for the tester and the judge together,
- how long to wait for each reply,
- maximum model spend for the run (tester and judge together).

**R10.2** A global budget cap is set in `.env` (`BOT_BUDGET_USD`). The driver checks it before every model call. When
the cap is reached, no more model calls are made. This is the kill switch, and it is required by the project's
budget rule.

**R10.3** The bot's spending is counted separately from the chatbot's, so testing cannot use up the chatbot's budget.

**R10.4** A run that hits a limit stops and says which limit it hit. It never stops silently.

## 11. Privacy and safety

**R11.1** The model sees only roster pseudonyms and squad numbers, in its prompt, its tool results, and its replies.
Real names and sender IDs are mapped in code, and only in code.

**R11.2** The calendar output that goes to a model is passed through the same mapping. If the calendar shows a real
name, the name is replaced before the model sees it.

**R11.3** The bot writes only invented messages. It writes no real incident, patient, or address details. Scenario
briefs are invented as well. This follows the rule that 911 call details must never reach an LLM.

**R11.4** The API key is read from `.env` only. It is never shown on the page, written to a file, or logged.

**R11.5** Transcripts and reports are written under `runs/`. They are not committed.

**R11.6** The bot reaches the chatbot only through the replay tool, and the calendar only through the test guard. It
does not reach GroupMe or production.

## 12. The Bot tab

**R12.1** Configuration: the fields in section 4, the models (section 13), the temperature, and the limits. These sit
in the top portion of the tab. The buttons are Load goal, Save goal, Go, and Stop. The expected results box is labelled
"judge only" on the page.

**R12.2** Layout. The top portion holds the configuration. The main area is the conversation, which scrolls until the
run ends.

- Each post the agent sends is left-aligned, in blue. It shows the persona it is written as (pseudonym and squad),
  its posting setting, and its trace ID in a small grey font.
- Each chatbot reply is right-aligned, in red. It shows its channel and the trace ID in small grey font.
- The message in flight is highlighted yellow, as on the Batch tab.
- Setup steps and tool results appear as small notes between the posts.

**R12.3** After the `before` snapshot, the page shows the raw calendar for each day in question. After the `after`
snapshot, it shows the difference beside it.

**R12.4** The plan and the judge's checks are shown before the conversation, so you can see what will be checked.
The verdicts are shown at the end, with evidence.

**R12.5** Stop finishes the step in progress, then ends the run. The final status says that it was stopped.

**R12.6** The page shows the spend so far against the run's cap, and against the global cap.

**R12.7** Trace references. Every bubble shows its trace ID in small grey font. Each ID is the one returned by
`POST /api/send`, and it also covers the replies that message caused. Opening it needs a link in the replay tool
(`#trace=<id>`). That is a change in the chatbot repo, not built yet.

**R12.8** Run lock. Only one run at a time across the batch tab and the bot tab. Go on either tab is disabled while
the other is running, and the page says which run holds the lock.

## 13. Models and defaults (confirmed)

| Role | Default | Notes |
|---|---|---|
| Tester | `claude-sonnet-5-5` | Cheaper over a long conversation. Can be set to Opus on the page. |
| Judge | `claude-opus-5-5` | Stronger than the tester, as you asked. |

The earlier sketch had these the other way round. These defaults were confirmed in review: the judge is the stronger
model.

Both are picked from the provider's model list on the page, as the chatbot's models are. The temperature is per
scenario. The tester's temperature defaults to 0.7; the judge's is 0.

## 14. Output

For each run, a folder under `runs/`, named by scenario and time:

- `transcript.jsonl`: every post, reply, tool call, tool result, and model call, with token counts and cost.
- `snapshots/`: one raw JSON file per day per label (`before`, `after`, and any the judge took).
- `report.md`: the plan, the judge's checks, the verdicts with evidence, the chatbot's replies, the calendar
  difference, and any refusals (window, persona, limits, guard).
- `summary.json`: scenario, models, temperatures, counts, cost, and the final status.

When a scenario is repeated, the results are reported as "passed N of M".

## 15. Build order

Build in stages, and test each one before the next:

- **Stage A, scripted:** no model. The scenario lists the posts. This tests the driver's tools, the window and persona
  checks, the snapshots, the guard, and the report. It runs the same every time.
- **Stage B, tester model:** a multi-turn conversation with a model, the plan, and the limits. No judge yet.
- **Stage C, noise:** generated noise, then noise from a batch file.
- **Stage D, judge:** the two-call judge, with pre-committed checks, the snapshots, and verdicts.

Start with the scenarios you named: the no-crew request, the challenged squad that needs a crew, and the Saturday
check. The last one can be verified from the calendar alone.

## 16. Open questions

1. **Models.** Confirmed: tester Sonnet, judge Opus (section 13).
2. **The judge sees the plan.** Section 8.2 has the judge read the tester's one-line plan, because the judge needs to
   know what was attempted. The plan states an intention, not the tester's reasoning. Earlier, we said the judge would
   not see the tester's reasoning. Confirm this reading.
3. **Noise source.** Generated or batch file by default? This doc says generated for variety, with batch files for
   regression.
4. **Gate date.** Warn only (R6.2), or block a `sent_at` after the gate date?
5. **Budget numbers.** What should `BOT_BUDGET_USD` and the per-run cap be for the first runs? Suggest a small global
   cap and a per-run cap of a few cents until the tools are trusted.
6. **Setup in the middle of a run.** Allowed when the scenario says so (R8.5). Confirm this is wanted, or allow setup
   only before the conversation starts.
