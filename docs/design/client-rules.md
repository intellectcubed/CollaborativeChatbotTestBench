<!-- Copied from CollaborativeAIChatbot/docs/design/external_client.md. Keep the two in step when the API changes. -->

# Requirements for a client that drives the chatbot from outside

Status: draft. Describes the replay tool's HTTP API as it is today, plus one open decision (section 6).
The client is a developer tool that replays saved GroupMe logs (or any scripted scenario) through the
processor, and checks what the chatbot said back.

## 1. Purpose

The client sends messages as if they came from group members, then reports for each message:

- whether the processor accepted it,
- whether the chatbot replied, and what it said,
- which channel each reply went to (so it is clear whether a reply reached the group chat or was only logged).

It does not decide whether a reply is correct. That comparison is done by the developer.

## 2. Service

- Base URL: the replay tool, default `http://localhost:8001`. It is for local use only.
- No authentication today. Do not expose the service beyond the developer's machine.
- Everything is JSON over HTTP. Times are ISO 8601 strings.

## 3. Endpoints the client uses

| Purpose | Call | Notes |
|---|---|---|
| Send one message | `POST /api/send` | Body below. Returns at once, before the chatbot has replied. |
| Trace status | `GET /api/traces/{trace_id}` | Poll this until the status is final (section 5). |
| Replies | `GET /api/traces/{trace_id}/outbox` | Read once the trace is final. |
| Sender lookup | `GET /api/members` | Maps `sender_id` to roster pseudonym and squad. Real names are included: local use only. |

`POST /api/send` body:

```json
{"sender_id": "1000000001", "text": "Good job 35!", "sent_at": "2026-11-06T14:18", "live_calendar": true}
```

- `sender_id` (required): must be a roster member. Unknown IDs get `404`.
- `text` (required): the message as the member wrote it. The client does not redact it; the processor does.
- `sent_at` (optional): ISO 8601. Naive values are read as America/New_York. Omit it for "now".
- `live_calendar` (optional, default `true`): `false` makes the calendar preview-only for this message.

`POST /api/send` response, on success:

```json
{"status": "enqueued", "trace_id": "7c63743786f94d17a3f5c9e0f3ad1b36"}
```

Other `status` values the client must handle:

| status | Meaning | Will there be a reply? |
|---|---|---|
| `enqueued` | Accepted. Poll the trace. | Possibly. |
| `duplicate` | This message was already delivered (same trace). | Client should not expect a new reply. |
| `ignored` | Sent by a system or bot sender, so not for the chatbot. (A trace that ends `ignored` is different: see 5.2.) | No. |
| `dropped` | The PII filter could not keep any text: the message was empty, or was only 911 call details. Nothing was stored. | No. Final. |
| `uncertain` | The PII filter could not decide and flagged it. | No. Final. |

## 4. Errors

| HTTP | Meaning | Client action |
|---|---|---|
| `404` | Unknown `sender_id`. | Report it and skip the message. Do not retry. |
| `422` | Bad body (for example an unparsable `sent_at`). | Fix the input. Do not retry. |
| `502` | The processor was unreachable. The message may or may not have been queued. | Do not resend automatically (section 5.4). Report it and stop, unless a person decides to resend. |
| other `5xx` | Unexpected. | As for `502`. |

## 5. Polling for the reply

### 5.1 Sequence for one message

1. `POST /api/send`. Keep `trace_id` from the response.
2. If the status is not `enqueued`, the message is finished (see the table in section 3). Record it and go to 5.5.
3. Poll `GET /api/traces/{trace_id}` until its `status` is final (5.2).
4. Call `GET /api/traces/{trace_id}/outbox` once. This is the list of replies (5.3).
5. Record the result (5.5).

### 5.2 Which trace statuses mean "still working"

- Working: `received`, `enqueued`.
- Final: everything else. Known final values: `done`, `ignored`, `error`, `flagged`, `duplicate`, `filtered_dropped`, `filtered_uncertain`, `enqueue_failed`.
- `ignored` at this stage means the chatbot read the message and judged that it needed no action. The message is still
  kept in the chat history, and no reply is expected. A message with no scheduling words goes through this path: it is
  not dropped before the chatbot sees it.
- Treat an unknown value as final, and record it as-is.

The status is read from `GET /api/traces/{trace_id}`. The same response contains the steps, which the client can
log for debugging but should not need.

### 5.3 Reading the replies

`GET /api/traces/{trace_id}/outbox` returns a list, one row per reply, oldest first. Fields used:

| Field | Meaning |
|---|---|
| `kind` | What the reply is for: for example `clarify` (a question) or `confirm`. |
| `text` | The reply text, exactly as the chatbot wrote it. |
| `to_member` | Pseudonym of the member it is addressed to. |
| `channel` | Where it was delivered: `replay` (shown in the replay tool), `log` (recorded, not delivered), or `-`. |
| `status` | `sent` (delivered), `failed`, `skipped`, `pending` (still being sent: poll again), `already_sent`. |
| `error` | Reason, when `status` is `failed`. |

Poll the outbox again while any row is `pending`, within the 120-second limit in 5.4.

An empty list is a valid result: the chatbot had nothing to say. Record it as "no reply", not as an error.

### 5.4 Timing and retries

- Poll interval: 1 second. Do not poll faster than once a second.
- Give up after 120 seconds. Record the trace as "still processing" and move on. Do not treat it as failed.
- A trace that is still `received` or `enqueued` after the timeout may finish later. The client may check it again
  in a later run, using the saved `trace_id`.
- Never resend a message automatically. Each `POST /api/send` creates a new message (a new trace), so a resend
  after a timeout or `502` can duplicate the message in the chat history and make the chatbot act twice.
- Send messages one at a time, in order. Each message is part of the history for the next one, so a scenario is
  only meaningful when earlier messages have finished before later ones are sent.

### 5.5 What to record per message

- `trace_id`, the input message (as sent), `sent_at`, and `sender_id`. Do not write `sender_id` into shared logs or
  committed files. Use the roster pseudonym there.
- The initial `status` from `POST /api/send`.
- The final trace `status`, or "still processing".
- Each outbox row: `kind`, `text`, `channel`, `status`, `error`.
- A verdict for the message, derived as in section 7.

## 6. Open decision: which channel counts as "reached the group"

Today the replay path (`X-Source: replay`, which `/api/send` always uses) routes replies to the `replay` channel.
Live GroupMe messages route to `log` (see `config/channels.toml`), and no GroupMe channel exists yet. So a reply
to an external driver will never be marked as reaching the group chat.

Options:

1. The client reports the channel as-is, and the developer decides what it means. No server change.
2. Add a per-request setting so an external driver's messages are routed to a channel that represents the group
   (for example a `group` channel that records delivery without sending to GroupMe). Needs a config entry and
   one line in `/api/send`.

Recommendation: option 1 for now, with a `reached_group` field on the client's own report that is only ever set
once a real group channel exists.

## 7. Verdict for one message (client-side)

| Trace final status | Outbox | Verdict |
|---|---|---|
| `done` | one or more rows with `status: sent` | Replied (with the channel shown). |
| `done` | empty | No reply. |
| `done`, outbox rows `failed` | — | Reply failed to send. |
| `ignored` | — | Processed and stored in the history; the chatbot judged no reply was needed. |
| `filtered_dropped`, `filtered_uncertain`, `duplicate` | — | Not processed. |
| `error`, `enqueue_failed` | — | Processing error. |
| still working after timeout | — | Still processing. |

## 8. Out of scope for the client

- Deciding whether a reply is correct (that is the developer's comparison, or the labeled-example scorer).
- Calendar state. Checking the calendar is a separate step, after the message is final.
- Retrying failed messages, or any reordering.

## 9. Possible future endpoint (not built)

If the polling loop above turns out to be awkward for clients, add `POST /api/messages`. It would perform the send,
wait up to a set time, and return the trace status and outbox in one response. `POST /api/send` would stay as it is,
because the browser uses it. Build it only if the polling sequence in section 5 proves hard to use.
