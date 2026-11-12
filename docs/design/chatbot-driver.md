# Chatbot Driver

A local web tool that drives tests against the EMS scheduling chatbot. It talks to the **replay tool**, which
impersonates group members and forwards their messages to the chatbot. The driver never talks to GroupMe or to
the production calendar.

It has three tabs:

1. **Batch:** open a saved batch file and send its messages.
2. **Create:** build a new batch file and save it for later runs.
3. **Bot:** an AI client that plays squad members and holds multi-turn conversations.

## 1. Interfaces

### 1.1 Replay tool (the only thing the driver calls)

Base URL from `.env` (`REPLAY_URL`, default `http://localhost:8001`).

The driver follows the client requirements in [client-rules.md](client-rules.md), a copy kept in this repo. The
summary, for readers of this repo:

1. `POST /api/send` with the message. It returns `{"status": "enqueued", "trace_id": "..."}` straight away.
2. Poll `GET /api/traces/{trace_id}` once a second until its `status` is no longer `received` or `enqueued`.
   Give up after 120 seconds and show "still processing".
3. Read `GET /api/traces/{trace_id}/outbox` once for the chatbot's replies.

Request body:

```json
{"sender_id": "<roster sender id>", "text": "Good job 35!", "sent_at": "2026-11-06T14:18", "live_calendar": true}
```

- `sender_id`: must be on the chatbot's roster. The replay tool returns 404 otherwise.
- `sent_at`: New York time, ISO 8601 without an offset is fine.
- `live_calendar`: `false` previews the calendar only.

Messages are sent one at a time, each waiting for its trace to finish, because later messages depend on the
history that earlier ones create. Never resend a message automatically; each send creates a new message.

`GET /api/members` returns the roster (sender ID, pseudonym, squad, name). The driver uses it to turn a
pseudonym into a sender ID when a batch runs, and to show names on screen.

### 1.2 Test calendar (Bot tab only)

The Bot tab reads and sets up the calendar. It uses the **test** calendar only (`CALENDAR_TEST_URL`, port 7007).
Any other address is refused in code.

### 1.3 Anthropic API (Bot tab only)

The key is read from `.env` (`ANTHROPIC_API_KEY`). It is never shown in the page or written to a file.

## 2. Batch files

A batch is a `.jsonl` file: one message per line.

### 2.1 Format

Each line is a message, with the pseudonym in place of the sender ID:

```json
{"id": "batch-0001", "created_at": "2026-03-14T13:00:00-04:00", "member": "Member-7", "text": "34 is good Saturday 1800-0600"}
```

- `id`: unique within the batch.
- `created_at`: when the message is sent, with its offset. The driver sends this as `sent_at`.
- `member`: the roster pseudonym (`Member-N`). The driver resolves it to a sender ID at run time.
- `text`: the message as the member wrote it.

**Why pseudonyms:** this repo is public. A batch saved with real sender IDs would publish them. A batch
that holds only pseudonyms is safe to commit. A real GroupMe export (which has sender IDs and names) is
converted to this format when it is imported, and the converted file stays on the local machine unless it
has been pseudonymized.

Optional first line (a header) holds the batch's name and description. Simpler still: a sidecar
`<name>.meta.json`. See question 4.

### 2.2 Batch tab

- **Open** a batch file. Every line is shown: date and time (for example `March 14, 2025 1:00:00 PM`, New York
  time), sender name, squad, and text.
- Each line has a checkbox, checked by default. Unchecked lines are skipped.
- **Run All**: sends the checked lines in file order, one at a time, waiting for each trace to finish.
- **Run from / to**: runs the checked lines whose dates fall in a range.
- **Step** (one message), **Pause / Resume**, **Stop**.
- Each line shows its status (pending, sending, sent, skipped, failed) and the chatbot's reply, or a link to the
  trace.
- A live calendar switch applies to the whole run. It is off by default for re-runs of old batches (question 6).

### 2.3 Create tab

- Start a new batch, or append to an open one.
- Add a message with: date and time, pseudonym (chosen from the roster, showing squad), and text.
- Edit or delete lines. Save writes the file; **Save as** creates a new one.
- Saved files are plain `.jsonl`, so they can be run from the Batch tab or outside this tool.

## 3. Bot tab

An AI client that plays squad members. It posts messages, waits for the replies, and keeps the conversation
going while it follows its goal. It also answers the chatbot's questions when they're directed at it.

### 3.1 Configuration

Set on the page, then **Go**. Saved per scenario as a file in `scenarios/`.

| Setting | Notes |
|---|---|
| Goal | Plain language, with the stop condition. This is what bounds the bot's autonomy, so write it precisely: a goal can name the squads, dates, and setup changes that are allowed. |
| Expected results | What should be true afterwards, in plain language. Checked by the judge (section 3.6), never shown to the chatbot. |
| Personas | Which squads and members the bot may write as. Two squads for a squad-to-squad conversation. |
| Date window | For example March 1 to March 31, 2026. Every `sent_at` must fall inside it. |
| Setup allowed | Yes or no: may the bot change the test calendar to set up conditions (section 3.3). |
| Starting history | Optional batch file to load first, so the chatbot has context. |
| Tester model | Picked from the list the provider returns. Starts at `claude-opus-5-5`. |
| Judge model | Same list, but a different model from the tester by default, so it does not repeat the tester's mistakes. Starts at `claude-sonnet-5-5`. |
| Temperature | 0 for the most repeatable runs; higher for more varied wording. |
| Repeat | How many times to run this scenario. Default 1. Several runs are only made when asked; the results are reported as "passed N of M". |
| Max messages, max turns | Hard stops. |
| Reply timeout | How long to wait for each reply before continuing. |
| Max cost | Stops the run when the model spend passes this amount. |
| Live calendar | Off: preview. On: changes the test calendar. |

Overall instructions (the bot's role and rules) are one prompt file, `prompts/bot/system.md`. Each scenario adds
its own goal and personas on top of that.

### 3.2 Dates

The bot chooses each `sent_at`. The driver checks it against the window and refuses anything outside. Example: to
test a request for Saturday March 14, the bot posts on an earlier day, for example March 10. If the message names
a date, the driver warns when `sent_at` is after that date, or more than a set number of days before it.

### 3.3 Setup steps

The bot can set up the test calendar when it judges that a condition is needed, within the scenario's goal and its
guardrails (window, personas, live setting, limits). It may do this before the conversation or in the middle of it.
Examples:

- Remove a crew from a day, then send a no-crew request for that day, which the chatbot should not find a crew to
  remove for.
- Schedule a crew on a day, then say "you won't have a crew for that day or part of it".

Setup steps are written to the log. They are refused for any calendar other than the test one.

### 3.4 Log

The page shows, in order:

- what the bot sent, and the date it set,
- the chatbot's replies, with the channel,
- each tool check (window, persona, calendar read, calendar change) and its result,
- the calendar state before and after,
- the final verdict and reason.

The log can be saved to `runs/`. A run's files are not committed.

### 3.5 Tools the bot has

Its model calls are given these tools, which the driver runs:

- `list_members`: the personas it may use (pseudonyms and squads).
- `post_message(member, text, sent_at)`: posts through the replay tool and waits for the reply.
- `get_history(squad, until)`: the context the chatbot would see.
- `get_calendar_day(date)`: reads the test calendar.
- `set_calendar(...)`: runs a setup step (test calendar only, and only in setup or when live is on).
- `finish(passed, reason)`: ends the run.

### 3.6 Posting order

By default the bot waits: a persona does not post again until the chatbot has answered its last message. This
keeps each conversation in order, because the chatbot's answer depends on the history.

Simultaneous chatter needs more. Two members can talk over each other, and that is what happens in a real group
chat. Each message the bot posts carries one of these settings. The bot chooses them, and it may use `thread`, `none` and
`sync` whenever it judges that the conversation calls for them. A scenario can forbid a setting (for example, a
scenario that only tests a plain question and answer can forbid `none`):

| Setting | Meaning |
|---|---|
| `wait` (default) | Wait for this trace to finish before the next message from anyone. |
| `thread` | Post now; the persona that posted it waits for its own reply before speaking again. Other personas may post meanwhile. |
| `none` | Post and move on at once. Used only for deliberate crossing messages. |
| `sync` | A barrier: wait for every outstanding trace to finish before continuing. |

Rules the driver enforces:

- A persona never posts again while its own last message is unanswered, unless the step is `none`.
- Replies that arrive late are still recorded, and the log shows which message they answer.
- A trace still running when the run ends is reported as "still processing", and the judge is told.

### 3.7 Expected results and the judge

The bot's goal tells it what to do. The **expected results** tell the judge what should be true afterwards. They
are separate, on purpose:

- The **tester** sees the goal only. If it knew the answer it wanted, it could steer the chatbot toward the right
  answer and hide a failure.
- The **chatbot under test** never sees either.
- The **judge** sees the expected results, the transcript, the chatbot's replies (outbox), the trace steps, and the
  calendar before and after for the dates the run used. It does not see the tester's reasoning.

The judge is a separate model call (its own model setting). It returns one line per expected result:

| Field | Meaning |
|---|---|
| `expectation` | The expected result, as written. |
| `verdict` | `pass`, `fail` or `unclear`. |
| `evidence` | Quotes or values it relied on: a reply, a calendar line, a trace step. |
| `reason` | One or two sentences. |

Judge rules:

- It must cite evidence. A verdict with no evidence is recorded as `unclear`.
- `unclear` is shown separately from `fail`, so a missing check is not counted as a bug.
- The judge may say that the chatbot's replies were fine but the calendar was wrong, or the reverse. Both are shown.

**Calendar records.** The bot can ask the calendar service for any day during the run, and it will. The judge
does not rely on that. The driver writes its own record of the calendar: the whole schedule for each date the run
touched, taken before the first message and again after the last trace finishes, plus the difference between the
two. The judge reads that record. Each record is the calendar service's raw answer for that day, not a summary,
so the judge sees exactly what the chatbot's changes did and when the bot might have looked at them.

Deterministic checks (question 7 in the earlier draft) can sit beside the judge later: for example, "squad 54 has
no crew 1800-0600 on this date" can be a plain check that does not need a model.

## 4. Running it

The driver runs only in Docker, in its own compose project, separate from the chatbot's.

- `docker compose up` starts the driver. The page is at `http://localhost:8010`. Port 8010 is used because the
  chatbot's ingest already uses 8000 on the host.
- **Development:** `./src` is mounted into the container, and the server reloads when a file changes. A code edit
  shows on the next request, with no rebuild.
- **Rebuild** (`docker compose up -d --build`) only when `pyproject.toml` changes, because that changes the installed
  dependencies. Use a rebuild to check the container matches the committed code.
- The driver reaches the replay tool and the test calendar on the host, at the ports the chatbot's compose file
  publishes (`REPLAY_URL=http://host.docker.internal:8001`, `CALENDAR_TEST_URL=http://host.docker.internal:7007`).
  It does not join the chatbot's Docker network, so the two projects stay independent.
- `.env` is passed to the container if it exists. Nothing secret is entered in the page.
- `batches/`, `scenarios/` and `runs/` are mounted from the host, so saved files and run output survive restarts.
- The driver is not configured to reach GroupMe or the production calendar. Containers can usually reach the
  internet, so this is enforced by the code (the calendar guard refuses anything but the test calendar) rather than
  by the network.

## 5. Decisions

1. Create mode uses the same `.jsonl` format as the batch file.
2. The Batch tab shows the roster name, not the name in the file.
3. `set_calendar` calls the test calendar's API directly.
4. Pausing waits for the current message to finish.
5. The bot answers only questions directed at one of its personas.
6. Post-run checking is done by a judge against expected results (section 3.7).
7. The tester does not see expected results. The judge does not see the tester's reasoning.
8. The bot has autonomy: it chooses its personas, posting settings, when to set up the calendar, and when to finish.
   The scenario's goal bounds that autonomy, and it can name exact squads, dates and allowed setup changes.
9. The judge uses a different model from the tester by default.
10. A scenario runs once unless its repeat count is set. When repeated, results are reported as "passed N of M".
11. The calendar records cover the dates the run touched, plus any date the bot queried.
12. The client rules are copied into this repo ([client-rules.md](client-rules.md)) so the spec reads on its own.

## 5a. Open questions

None outstanding. Tell me if the Tamil in your last message meant something other than the scenario goal; I read it
that way.

## 6. Suggested order of work

1. Replay client and batch file reader (no UI). Test it against the replay tool with a small batch.
2. Batch tab: open, show, checkboxes, Run All, stop.
3. Create tab, and saving batches.
4. Bot tab, starting with scripted messages (no model), then add the model.
5. Setup steps and deterministic checks.
