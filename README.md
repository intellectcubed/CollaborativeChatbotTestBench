# chatbot-driver

A web tool that drives the EMS scheduling chatbot through the replay tool.

- **Batches:** run a set of messages in order, one at a time, and watch each trace finish. Save a batch as a
  file and rerun it later.
- **Agent:** configure and run a model that plays squad members to test the chatbot (see
  `../CollaborativeAIChatbot/docs/design/scenario_agent.md`).

The driver only talks to the replay tool's HTTP API and, for the agent's setup steps, to the **test** calendar.
It never talks to the production calendar or to GroupMe.

## Layout

    src/driver/api/       client for the replay tool
    src/driver/batches/   batch files: load, save, run
    src/driver/agent/     agent configuration and runs
    src/driver/web/       the web page and its server
    batches/              saved batches (pseudonyms only, safe to commit)
    scenarios/            agent scenario files
    runs/                 run output: transcripts and reports (not committed)
    tests/

## Setup (to be completed)

    cp .env.example .env
    python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
