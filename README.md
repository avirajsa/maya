# Maya is my smart room assistant. she spoils me with everything :)


AI instructions dump (chatgpt)
Perfect. If **`~/homeassistant` is already working**, I would **not move or rebuild it**. Treat Home Assistant as infrastructure that Maya talks to.

I'd make `maya` the actual project repo and keep HA separate.

```text
~/projects/
├── maya/                         # 🧠 Maya — your personal AI assistant
│   ├── README.md
│   ├── Makefile
│   ├── pyproject.toml
│   ├── .env.example
│   ├── .gitignore
│   │
│   ├── src/
│   │   └── maya/
│   │       ├── __init__.py
│   │       │
│   │       ├── core/             # Core application
│   │       │   ├── config.py
│   │       │   ├── state.py
│   │       │   └── events.py
│   │       │
│   │       ├── voice/            # Everything voice-related
│   │       │   ├── wakeword.py
│   │       │   ├── stt.py
│   │       │   ├── tts.py
│   │       │   └── pipeline.py
│   │       │
│   │       ├── agent/            # Maya's "brain"
│   │       │   ├── agent.py
│   │       │   ├── prompts.py
│   │       │   ├── memory.py
│   │       │   └── router.py
│   │       │
│   │       ├── tools/            # Things Maya is allowed to do
│   │       │   ├── __init__.py
│   │       │   ├── lights.py
│   │       │   ├── fan.py
│   │       │   ├── music.py
│   │       │   └── system.py
│   │       │
│   │       ├── integrations/     # External systems
│   │       │   ├── homeassistant.py
│   │       │   └── mpris.py
│   │       │
│   │       └── main.py
│   │
│   ├── tests/
│   │   ├── test_agent.py
│   │   ├── test_tools.py
│   │   └── test_integrations.py
│   │
│   ├── scripts/
│   │   └── ...
│   │
│   └── docs/
│       └── architecture.md
│
└── homeassistant/                # 🏠 HA infrastructure
    ├── compose.yaml
    ├── Makefile
    └── config/
        ├── configuration.yaml
        ├── automations.yaml
        └── ...
```

### The important separation

Think of it like this:

```text
                         MAYA
                          │
                 ┌────────┴────────┐
                 │                 │
             AI / Voice        Tools
                 │                 │
                 │       ┌─────────┼──────────┐
                 │       │         │          │
                 ▼       ▼         ▼          ▼
             reasoning  lights    fan       music
                           │         │          │
                           └────┬────┘          │
                                ▼               ▼
                         HOME ASSISTANT       MPRIS
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
                  LIGHT        FAN       FAIRY LIGHT
```

So:

**Home Assistant = physical-world infrastructure**

**Maya = intelligence + voice + personality + orchestration**

That distinction will become really valuable later.

---

## Start the repo

I'd use `uv`, since that's already your Python workflow.

```bash
mkdir -p ~/projects
cd ~/projects

mkdir maya
cd maya

git init
uv init
```

Then create the source structure:

```bash
mkdir -p src/maya/{core,voice,agent,tools,integrations}
mkdir -p tests scripts docs
touch src/maya/__init__.py
touch src/maya/main.py
```

You can then install your project editable:

```bash
uv pip install -e .
```

Although we'll probably want to configure `pyproject.toml` properly before doing much more.

---

## Your first Makefile

Don't overengineer it yet.

```makefile
.PHONY: run test lint format check

run:
	uv run python -m maya.main

test:
	uv run pytest

format:
	uv run ruff format .

lint:
	uv run ruff check .

check:
	uv run ruff check .
	uv run pytest
```

Eventually:

```text
make run
make test
make format
make lint
make check
```

---

## `.env`

Don't put secrets in Git.

```env
HOME_ASSISTANT_URL=http://localhost:8123
HOME_ASSISTANT_TOKEN=

# Later
LLM_API_KEY=
```

And `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
*.pyc
```

Commit `.env.example`, **never `.env`**.

---

## And don't build all of this yet

This is the part I'd strongly recommend.

Your repo can have the architecture from day one, but the first actual Maya should be ridiculously small:

```text
Microphone
    ↓
speech-to-text
    ↓
"turn on the light"
    ↓
intent/tool
    ↓
Home Assistant API
    ↓
LIGHT ON
```

Then:

```text
"turn on the light"
"turn off the light"
"turn on the fan"
"turn off the fan"
"turn on the fairy lights"
"turn off the fairy lights"
```

Then add:

```text
                 Maya
                  │
                  ▼
             LLM Agent
                  │
          ┌───────┼────────┐
          ▼       ▼        ▼
        lights   fan     music
          │       │        │
          └───────┼────────┘
                  ▼
             integrations
```

And **only after that** add wake word, memory, contextual reasoning, etc.

The really nice thing is that your existing:

```text
~/homeassistant
```

doesn't need to become part of the Git repo. Maya can simply connect to it over:

```text
http://localhost:8123
```

So if you eventually publish Maya on GitHub, people can clone the repo without getting your personal Home Assistant database/config mixed into it.

**I'd make `~/projects/maya` the clean, public-facing project and leave `~/homeassistant` as your private machine infrastructure.**

