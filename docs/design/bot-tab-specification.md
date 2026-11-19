# Bot tab: specification

**Status:** draft 3. All questions answered. Changes from the sketch are marked **(change from sketch)**, with the
reason. Section 10 lists the edits to bring the sketch in line.

**Layout source:** [diagrams/ChatbotTestInteractiveTab.excalidraw](diagrams/ChatbotTestInteractiveTab.excalidraw).
The diagram owns *where* things are, roughly. This document owns *what they do*, and wins where they disagree.

**Related:** [bot_agent.md](bot_agent.md) (the automated bot, the judge, snapshots), [chatbot-driver.md](chatbot-driver.md)
section 3 (Bot tab configuration), [ux-modifications.md](ux-modifications.md) (page banner, tabs, Live Calendar).

---

## 1. Purpose

One tab for talking to the chatbot, in either of two modes that share the same conversation window and calendar:

- **Manual:** I type each message, pick which squad (and optionally which member) it is from, and see the replies.
- **Automated:** the AI tester (bot_agent.md) drives the conversation toward a goal, and the judge checks the result.

The tab shows one week of the test calendar, so I can see each change the chatbot makes without opening the Google
Sheet. Example: I pick the week of 8 March, type "I don't have a crew for Wednesday", and see the chatbot's reply in a
bubble and the change in Wednesday's cell.

**R1.1** Most of the tab's height goes to the conversation. The calendar at the top and the controls at the bottom are
kept compact.

**R1.2** This replaces the current Bot tab (`ui/src/tabs/BotTab.jsx`). Reuse the existing pieces where they fit:
`Conversation.jsx` for the message window, `useBot.js` for the automated run, `GoalForm.jsx` fields for the
Automated panel and its Advanced section.

---

## 2. Layout (top to bottom)

| # | Region | Shown in |
|---|---|---|
| 1 | Calendar bar: week navigation | Both modes |
| 2 | Week preview: 7 day cells, Sunday to Saturday | Both modes |
| 3 | Conversation window (scrolls) | Both modes |
| 4 | Mode switch: Manual / Automated | Both modes |
| 5a | Manual panel | Manual mode only |
| 5b | Automated panel | Automated mode only |

**R2.1** Regions 1–4 are common to both modes. The mode switch shows either 5a or 5b, never both.

**R2.2** All regions are the full width of the tab.

**R2.3** The conversation window takes all height left over after the other regions. It never shrinks below about
half the tab's height; if the window is short, the Automated panel scrolls instead.

**R2.4** **(change from sketch)** The calendar (regions 1–2) has a collapse control, so I can hide it and give the
conversation the full height. Collapsed, it shows one line: the week shown, e.g. `Week of 8 Mar 2026 ▸`.

---

## 3. Calendar bar

**(change from sketch)** The sketch has Week, Month and Year dropdowns. Three dropdowns to pick one week take space
and three clicks. Instead:

| Control | Type | Behaviour |
|---|---|---|
| Previous | Button `‹` | Shows the week before. |
| Week of | Date picker, shown as `8–14 Mar 2026` | Pick any day; the week that contains it (Sunday to Saturday) is shown. |
| Next | Button `›` | Shows the week after. |
| Message week | Button | Jumps to the week of the next message's date (Manual) or the start of the Date Range (Automated). |
| Collapse | Button `▾` / `▸` | Hides or shows the week preview (R2.4). |

**R3.1** Previous is on the left and Next on the right, so they read in time order.

**R3.2** When the tab opens, it shows the week that contains the Manual date (Manual mode) or the start of the Date
Range (Automated mode).

**R3.3** Navigating only changes what is shown. It never changes the calendar, the next message's date, or a run.

**R3.4** **(change from sketch)** If a change lands on a day outside the week shown, the bar shows a notice with a
link: `Changed: Thu 19 Mar (next week) · Show`. The view does not jump on its own, so it does not move while I am
reading.

---

## 4. Week preview

### 4.1 Day cell

Seven day cells, Sunday to Saturday. Each cell is a small grid of **4 columns × 10 rows**:

- **Row 0:** the day and date, e.g. `Wed 11 Mar`.
- **Rows 1–9:** one shift line each, in time order. Columns: `shift start–end | squad 1 | squad 2 | squad 3`.

**R4.1** A shift has 0 to 3 squads. Unused squad columns are blank. A shift with no squads shows `—` in squad 1.

**R4.2** A squad marked No Crew shows its number followed by `(No Crew)`, in red, e.g. `43 (No Crew)`.

**R4.3** Example. Wednesday starts as:

```
Wed 11 Mar
1800–0600 | 34 | 43 |
```

I post "no crew from 1900 to 2000 for 43". The chatbot splits the shift, and the cell shows:

```
Wed 11 Mar
1800–1900 | 34 | 43           |
1900–2000 | 34 | 43 (No Crew) |
2000–0600 | 34 | 43           |
```

**R4.4** If a day has more than 9 shift lines, the cell scrolls.

**R4.5** Cells use a small monospace font so the columns line up and the whole week fits in a short strip.

### 4.2 Where the data comes from

**R4.6** Each day cell is filled by calling the calendar API for that day, to get who is scheduled. Only the **test**
calendar is used; production is never read (bot_agent.md R8.6).

**R4.7** The page gets the week from the driver, never from the calendar directly. Section 11.1 has the details.

**R4.8** The week is read:

1. When the tab opens and whenever the week shown changes.
2. After **every chatbot reply** is final, in both modes, when Live Calendar is on (R4.11).
3. When an automated run ends (this is also the judge's `after` snapshot).

### 4.3 Showing changes

**R4.9** No highlighting. After each read, the cells simply show the new state; the change is visible because the
cell's lines change.

**R4.10** The page still compares each read with the one before it, day by day, in code. That comparison is used only
for the calendar note under the reply (R5.10) and the notice for changes outside the week shown (R3.4). It does not
style the cells.

**R4.11** With **Live Calendar** off (banner checkbox), the chatbot's changes are previews and the test calendar does
not change. The week preview does not re-read after replies and shows one line under the week:
`Live Calendar is off: the calendar does not change.` Preview changes are not drawn.

---

## 5. Conversation window

**R5.1** Scrolls, full width. The newest message is always at the bottom.

**R5.2** When I press Send, my message appears at once in a new bubble at the bottom, and the window scrolls up so it
is in view. Each reply appears the same way when it arrives. Exception: if I have scrolled up to read earlier
messages, the window stays where it is and a `New messages ↓` button appears; clicking it scrolls to the bottom.

### 5.1 Message bubbles

**(change from bot_agent.md R12.2:** replies are now green, not red.)

| | Member message | Chatbot reply |
|---|---|---|
| Side | Left | Right |
| Colour | Blue | Green |
| Header line | Date and time sent · member · squad · trace ID with copy icon (once the driver has it) | Date and time sent · Chatbot · squad · trace ID with copy icon · tokens in / out |
| Body | The message text | The reply text |

**R5.3** **Header line.** Small font, above the bubble (outside it), aligned with the bubble's side. Examples:

- Member message: `Tue 10 Mar 09:05 · Pat Example · squad 43 · trace 3f9a2c1b ⧉`
- Chatbot reply: `Tue 10 Mar 09:06 · Chatbot · squad 43 · trace 3f9a2c1b ⧉`

For a reply, the squad is the squad it is replying to, and the time is the reply's own `sent_at`. The replay
tool's outbox rows do not carry a time today, so the reply shows the time of the message it answers.

**R5.3a** **Names are shown, not masked.** This tab simulates a client of the chat, so the page shows each member's
real name from the roster, in the Member dropdown and in the bubble headers. (Real names are still kept away from the
bot's models; that rule is about what a model sees, not what the page shows.)

**R5.4** **Body.** The message text in normal font, inside the bubble. Line breaks in the text are kept. Long messages
wrap; a bubble is at most about 70% of the window's width.

**R5.5** **Trace ID.** On both bubbles, shown as its first 8 characters. It is the ID `POST /api/send` returns for
the member's message, which also covers the replies it caused, so a member bubble and its replies show the same ID.
The member bubble goes up as soon as `POST /api/manual/send` returns, with the trace ID from that answer in its title
(the answer also carries `sent_at`, `name` and `squad`); the status poll's copy of the same message is not shown again. The copy icon `⧉` copies the **full** trace ID to the
clipboard and shows `Copied` for about a second.

**R5.6** **Who sent it.** A member message sent by the AI tester in Automated mode has a small `bot` tag at the end of
its header line. Manual messages have no tag.

**R5.7** **Waiting.** While the chatbot is working on a reply, a small right-side placeholder bubble shows `…`. It is
replaced by the reply, or by a grey note if the reply timed out or failed.

**R5.7a** **Tokens.** Once a message's trace is finished, the reply title also shows the chatbot's model use for that
message: `tokens 3,334 in / 236 out`, summed over the trace's `llm:` steps (hover for the number of model calls). It
is shown once per message, on its first reply, or on the title-only line when there is no message. The same count
is on the Batch tab. In Automated mode the tester model never sees it.

**R5.8** If one message causes more than one reply, each reply has its own bubble, all with the same trace ID.

**R5.8a** **A finished turn with no message.** When the chatbot finishes a turn without sending a message (it acted, or
decided to do nothing), or did not take the message at all (`ignored`, `dropped`, ...), the right side still shows
the reply's header line, with no bubble under it, ending `✓ done, no message (<trace status>)`. Every message is
seen to be finished. The driver records it as a `reply` event with `no_message: true` and `trace_status`, in both
modes, and the judge's transcript includes it. A timeout is different: it is not finished, so it stays a grey note.

### 5.2 Notes between bubbles

**R5.9** Notes are small grey text, centred, with no bubble: calendar changes, setup steps, the tester's plan, the
judge's checks and verdicts, and run stops.

**R5.10** A calendar change after a reply also appears as a note under that reply, e.g.
`calendar: Wed 11 Mar 1900–2000, 43 No Crew`. It ties each change to the reply that caused it, and it stays in the
history after the cells have changed again.

**R5.11** Switching modes does not clear the window. **(change from sketch)** A **Clear** button at the top right of the
window clears it, to start a fresh conversation. An automated Go also clears it.

---

## 6. Mode switch and panels

### 6.1 Mode switch

**R6.1** A two-position switch: **Manual** | **Automated**. Default: Manual. The page remembers the last mode.

**R6.2** Disabled while a manual reply is pending or an automated run is going.

**R6.3** Disabled while a batch run is going on the Batch tab (run lock, bot_agent.md R12.8). The page says which run
holds the lock.

### 6.2 Manual panel (5a)

First line:

| Control | Type | Behaviour |
|---|---|---|
| Date | Date picker | The date of the next message. |
| Time | Time field `HH:MM` | **(change from sketch)** The time of the next message. Default 09:00. |
| Time Between | Number, minutes, with up/down | Added to the date and time after each message is sent. Default 5. |
| Squad | Dropdown | The squad the message is from. Squads from the roster file, in number order. Picking a squad selects its first member by name. |
| Member | Dropdown | **(change from sketch: was "Persona")** Every member in the roster file, by real name, in name order. Picking a member sets Squad to that member's squad. |

Second line:

| Control | Type | Behaviour |
|---|---|---|
| Message | Text box, full width | The message. Enter sends; Shift+Enter adds a new line. |
| Send | Button | Posts the message (section 6.4) and waits for the replies. |

**R6.4** **Time Between** changes only the message's `sent_at`. The driver does not wait that long. Example: Date
10 Mar, Time 09:00, Time Between 5. The first message is sent at 09:00, the second at 09:05, the third at 09:10. After
each Send, the Time field moves forward, so I can see and change the next time before sending.

**R6.5** **Squad** and **Member** follow each other. Any member can speak for a squad, so picking a squad is enough: its
first member by name is selected. To test a different member, for example on the second message, pick that member;
the squad changes to theirs. The send request carries the squad and the member's name, and the driver sends the
message to the chatbot with that member's sender ID, name and squad (section 11.2).

**R6.6** Send is disabled while the message is empty, while a reply is pending, and while a batch run holds the lock.

**R6.7** Manual messages always use the posting setting `wait`. There is no setting control in Manual mode.

### 6.3 Automated panel (5b)

First line:

| Control | Type | Behaviour |
|---|---|---|
| Choose File | Button | Opens a goal file (`.json`, usually from `scenarios/`) with the browser's file picker, and fills in the fields below and in Advanced. |
| Current file | Text, not editable | The file name loaded, without the path. |
| Noise | Dropdown | `none` / `some` / `heavy` (bot_agent.md section 7). |
| Squad | Dropdown | The squad the bot writes as. |
| Member driving conversation | Switch: **Same** / **Many** | See R6.8. |

Second line:

| Control | Type | Behaviour |
|---|---|---|
| Date Range | Two date pickers, From and To | Every `sent_at` must fall inside it. |
| Time Between | Number, minutes, with up/down | **(change from sketch)** The usual gap between the bot's messages. Default 5. See R6.8a. |

Then three text boxes on the left, each about three lines high, with the model dropdowns on the right:

| Control | Behaviour |
|---|---|
| Goal | What the bot should try, in plain language. |
| Stop When | When the run is done. |
| Expected Results | What the judge checks, one per line. Labelled "judge only": the tester never sees it. |
| Tester Model | The model that plays the members. Default `claude-sonnet-5-5`. |
| Judge Model | The model that checks the result. Default `claude-opus-5-5`. No warning when it is the same as the tester. |

Buttons:

| Control | Behaviour |
|---|---|
| Go | Clears the conversation and starts the run. Disabled while a run is going or a batch run holds the lock. |
| Stop | Finishes the step in progress, then ends the run (bot_agent.md R12.5). Enabled only while a run is going. |
| Advanced ▸ | Opens the Advanced section (R6.9). |

**R6.8** **Member driving conversation:**

- **Same:** the bot always writes as the same member of the chosen squad (the first member).
- **Many:** the bot takes turns among the members of the chosen squad. One member may say something and another
  comment on it or finish the thought, as in a real squad chat.

In the goal file this sets `personas`: Same is the first member only; Many is every member of the squad. It never
adds members of other squads. Noise (other squads) is set separately.

**R6.8a** **Time Between in Automated mode.** Like Manual mode, it changes only `sent_at`; the driver does not wait.
The bot still chooses the day it posts on (bot_agent.md R6), so:

- Within a day, each message's `sent_at` is the previous one plus Time Between, set by the driver.
- When the bot moves to a later day, it gives the day and the start time; Time Between applies again from there.
- The driver still refuses any `sent_at` outside the Date Range.

The value is saved in the goal file as `time_between_min`.

**R6.9** **Advanced** is collapsed by default and holds the goal settings that are not on the main panel:

- Goal name and **Save goal**
- Gate date
- Posting allowed (`wait` / `thread` / `none` / `sync`)
- Setup allowed
- Tester temperature and judge temperature
- Limits: max messages, max turns, reply timeout, max cost

**R6.10** The run status and spend (this run, against the cap) are shown on one line next to Go and Stop, as now.

### 6.4 Sending a message (both modes)

**R6.11** Manual and automated messages go through the same path as the batch runs (`POST /api/send` on the replay
tool), with `live_calendar` taken from the banner checkbox.

**R6.12** After the replies are final, the week is read again (R4.8) and the changes are shown (R4.9).

---

## 7. The judge (Automated mode)

**(change from sketch: the judge panel is not on the sketch.)** A separate judge panel would take room from the
conversation. Instead, for the first version:

**R7.1** The judge's output appears in the conversation window, as notes:

- Before the first post: the tester's plan and the judge's checks, each on one line.
- At the end: one note per check, with its verdict (`pass` / `fail` / `unclear`) and a `details` link that expands
  the evidence and reason in place.

**R7.2** The status line next to Go and Stop shows the judge summary when the run ends, e.g.
`judge: 3 checks · 2 pass · 1 fail`.

**R7.3** Later, if it is needed: a judge drawer that slides over the right side of the conversation. Not part of this
version.

---

## 8. States

| State | Mode switch | Send | Go | Stop | Calendar navigation |
|---|---|---|---|---|---|
| Idle | Enabled | Enabled when there is text | Enabled | Disabled | Enabled |
| Manual: waiting for reply | Disabled | Disabled | — | — | Enabled |
| Automated: running | Disabled | — | Disabled | Enabled | Enabled |
| Batch run going (Batch tab) | Disabled | Disabled | Disabled | Disabled | Enabled |

---

## 9. Open questions

None. Decided in round 2: no highlighting (R4.9); no calendar update with Live Calendar off (R4.11); Manual always
uses `wait` (R6.7); Time Between applies in Automated mode too (R6.8a).

---

## 10. Edits to bring the sketch in line

**Calendar bar**

1. Replace the Week, Month and Year dropdowns with: `‹` button, a "Week of" date picker showing `8–14 Mar 2026`,
   `›` button.
2. Delete the separate Next and Previous buttons (now `‹` / `›`, Previous on the left).
3. Add a **Message week** button and a collapse chevron `▾` at the right end of the bar.
4. Leave room under the bar for the one-line notice (changes outside this week, or "Live Calendar is off").

**Week preview**

5. In one day cell, draw the 4 × 10 grid with the example from R4.3 (Wednesday's three split lines), so the format is
   in the picture, not only in the side note.

**Conversation window**

6. Add a **Clear** button at the top right.
7. Label the bubbles: member posts left, chatbot replies right (the sketch has three left and one right; add a reply
   bubble or two so it reads as a dialogue).
8. Add a small calendar note under one reply, e.g. `calendar: Wed 11 Mar 1900–2000, 43 No Crew`.

**Manual panel**

9. Add a **Time** field (`HH:MM`) after the date picker.
10. Reorder the first line: Date, Time, Time Between, Squad, Member.
11. Rename **Persona** to **Member**, and show its default as `(first member)`.

**Automated panel**

12. Add **Time Between** after the Date Range.
13. Add an **Advanced ▸** button next to Go and Stop.
14. Add a status line to the right of Go and Stop (run state, spend, judge summary).

**Labels**

15. The "Manual" and "Automated" labels to the left of the two panels are outside the page frame. Fine for the
    sketch; just note in the diagram that only one panel shows at a time.

---

## 11. Technical notes

### 11.1 Reading the calendar for the week preview

**T1** **Calendar API.** Each day is read with the calendar service's `get_schedule_day` action, which returns who is
scheduled on that day:

```
GET {CALENDAR_TEST_URL}/?action=get_schedule_day&date=YYYYMMDD
```

- `CALENDAR_TEST_URL` defaults to `http://localhost:7007` (`src/driver/config.py`).
- The driver already has this call: `CalendarService.raw_day(day)` in `src/driver/calendar_test.py`. Reuse it. It
  goes through the guard (`check_url`), which refuses any address other than the test calendar, including
  production (port 8007).
- The answer is `{"success": true, "day_schedule": "<JSON text>"}`. `day_schedule(raw)` in the same file parses the
  JSON text.

**T2** **Shape of a day.** As the test calendar answers (checked against port 7007 on 15 Nov 2026):

```json
{
  "day": "Monday 2026-11-16",
  "shifts": [
    {"name": "18:00 - 00:00 Shift", "start_time": "18:00", "end_time": "00:00", "tango": 43,
     "segments": [
       {"start_time": "18:00", "end_time": "00:00",
        "squads": [{"id": 42, "territories": [35, 42, 54], "active": true},
                   {"id": 43, "territories": [34, 43], "active": true}]}
     ]},
    {"name": "00:00 - 06:00 Shift", "start_time": "00:00", "end_time": "06:00", "tango": 42,
     "segments": [{"start_time": "00:00", "end_time": "06:00", "squads": [{"id": 42, "active": true}]}]}
  ]
}
```

Mapping to cell lines (R4.1):

| Cell column | From |
|---|---|
| One line | One **segment** of a shift. A split shift has several segments, so it shows as several lines. |
| Shift start–end | `segments[k].start_time`, `end_time`, e.g. `18:00` shown as `1800` |
| Squad 1, 2, 3 | `segments[k].squads[0..2].id` |
| `(No Crew)` | `squads[j].active == false` |

Lines keep the calendar's own order (a night can be listed as 1800–0000 then 0000–0600), so they are not sorted.
`territories` and `tango` are not shown. The parser (`src/driver/calendar_week.py`) also accepts a shift without
segments (the shape the older tests use). If a day cannot be read, the cell shows the raw text in small font rather
than nothing.

**T3** **Driver endpoint.** New:

```
GET /api/calendar/week?start=YYYY-MM-DD
```

- `start` is the Sunday of the week. The driver reads the seven days and returns, for each: the date, the raw answer
  (unchanged), and the parsed shift lines from T2.
- The seven reads run in parallel, so a refresh takes about as long as one read.
- A day that fails is returned with an error message and no lines; the other days are still shown. The cell shows
  `could not read` with the error on hover.

**T4** **When it is called.** As in R4.8: tab open, week change, after every final reply while Live Calendar is on,
and at the end of an automated run. Reads only; this endpoint never calls `addShift` or `noCrew`.

**T5** **Comparing reads.** The driver keeps the last week read per session, and returns the day-by-day differences
with each new read. They are used for the calendar notes (R5.10) and the outside-this-week notice (R3.4). Reuse the
comparison in `src/driver/agent/run_state.py` (`diff_text`) where it fits.

**T6** **Automated runs.** The judge's `before` and `after` snapshots already call `raw_day`
(`src/driver/agent/run.py`). The week preview at the end of a run uses the same `after` answers for the days they
cover, so the page and the judge see the same data.

### 11.2 The roster file

**T7** The Bot tab's members come from the chat's roster file, with columns `name, sender_id, squad`:

- Default path: `../CollaborativeAIChatbot/data/groupme_87780377_roster.csv` (next to this project). Set
  `ROSTER_CSV` to use another file. In Docker, docker-compose mounts that folder read-only at `/app/roster`
  (`ROSTER_DIR` changes the folder).
- `GET /api/roster` returns each member's name, sender ID and squad, sorted by name. It also adds the chatbot's member
  ID (`member`, e.g. `Member-2`) when the replay tool can be reached. Automated runs use that ID, so real names never
  reach the bot's models. Without the file, it falls back to the replay tool's roster.
- The file is read on each request, so an edit shows on the next page load.

**T8** Sending: `POST /api/manual/send` takes `squad` and `name`. The driver looks the member up in the roster file and
calls the replay tool's `POST /api/send` with `sender_id`, `name` and `squad`. Today the replay tool reads only
`sender_id`, and takes the name from its own roster; all 24 sender IDs in the roster file are on the chatbot's roster,
so the chatbot sees the same member. Using `name` and `squad` from the request would be a change in the chatbot repo.

