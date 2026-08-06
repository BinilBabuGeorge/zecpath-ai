# Zecpath AI System

AI microservices layer for the Zecpath job portal — resume screening, voice/video
interviews, behavior analysis, and hiring decisions. See `docs/CODE_STANDARDS.md`
for coding conventions, and the Day 2 architecture doc for how these services
communicate (REST / Queue / Webhook).

## Project Structure

```
zecpath-ai/
├── data/               # Local/sample data (real data is gitignored)
├── parsers/            # Resume/document text & field extraction utilities
├── ats_engine/         # 1.0 ATS AI Service — resume scoring & ranking
├── screening_ai/       # 2.0 Screening AI Service — voice screening calls
├── interview_ai/       # 3.0 Interview Intelligence Service — HR/technical/final interviews
├── scoring/            # 5.0 Decision & Scoring Service — aggregation & final decision
├── utils/              # Shared code: logger, config, base service interface
├── tests/              # Pytest test suite, one file per module
├── docs/               # Code standards & other project docs
├── logs/               # Rotating log output (gitignored except .gitkeep)
├── requirements.txt
├── .gitignore
└── README.md
```

> Note: Behavior Analysis (4.0 in the Day 2 architecture) will get its own
> `behavior_ai/` folder once that module is scoped — for now its logic can
> be prototyped inside `interview_ai/`.

## Setup

1. **Clone the repo**
   ```bash
   git clone <your-repo-url>
   cd zecpath-ai
   ```

2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Copy environment variables**
   ```bash
   cp .env.example .env
   # then fill in real values
   ```

5. **Run the test suite**
   ```bash
   pytest --cov=. --cov-report=term-missing
   ```

6. **Run a service directly (for local testing)**
   ```bash
   python -m ats_engine.service
   ```

## Logging

All modules log through `utils/logger.py`. Logs are written to the console
and to `logs/zecpath_ai.log` (rotated at 5MB, 3 backups kept).

## Adding a New Service

1. Create a new folder (e.g. `behavior_ai/`) with an `__init__.py` and a `service.py`.
2. Subclass `utils.base_service.BaseAIService` and implement `process()`.
3. Add a matching `tests/test_<service>.py`.
4. Document its input/output contract at the top of `service.py`, matching the
   Day 2 I/O specification.
