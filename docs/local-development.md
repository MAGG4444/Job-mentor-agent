# Local LangChain Development

## Validated environment

Validated on September 22, 2026:

- Python 3.12.10
- pip 25.0.1
- langchain 1.4.2
- langchain-core 1.6.4
- langchain-openai 1.6.4
- pydantic 2.13.5
- python-dotenv 1.2.3
- openai 3.19.0 (installed by `langchain-openai`)

The project uses the OpenAI provider and reads the model ID from the local `.env` file. LangSmith tracing is disabled by default.

## Install on Windows PowerShell

Run these commands from the cloned repository root:

```powershell
Set-Location 'C:\path\to\job-mentor'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
Copy-Item .env.example .env
notepad .env
```

In `.env`, keep `MODEL_PROVIDER=openai`, set `MODEL_NAME` to a model ID your account can access, and add your own `OPENAI_API_KEY`. Do not commit `.env` or paste the key into chat. No LangSmith API key is required.

## Run a saved terminal interview

Start a new three-question session from the fictional resume and JD fixtures:

```powershell
Set-Location 'C:\path\to\job-mentor'
.\.venv\Scripts\python.exe .\examples\interview_session.py
```

Creating a new session makes one question-generation model call. The session is saved immediately to `data/interviews/<session_id>.json`, then saved again after every accepted answer. Blank answers do not advance; `不知道` is a valid answer. Use `/exit` or Ctrl+C to pause and print the session ID and recovery command.

Resume a saved session without calling the model or requiring an API key:

```powershell
Set-Location 'C:\path\to\job-mentor'
.\.venv\Scripts\python.exe .\examples\interview_session.py --resume '<session_id>'
```

The resume path is resolved from the project location rather than the shell's current directory. Completed sessions display their completed status and do not ask the questions again. Invalid IDs, missing files, damaged JSON, and unsupported schema versions are reported without replacing the saved record.

Saved JSON contains the schema version, session ID, timezone-aware timestamps, status, resume and JD snapshots, non-secret model settings, prompt version, questions, and committed answers. It never stores the API key.

## Run the standalone diagnostic generator

```powershell
Set-Location 'C:\path\to\job-mentor'
.\.venv\Scripts\python.exe .\examples\diagnostic_questions.py
```

This command makes a small billable model call.

### Diagnostic questions

The model reads the fictional `resume.txt` and `jd.txt` fixtures and should print a JSON object containing exactly three questions. Each question has `question`, `purpose`, `resume_evidence`, and `needs_confirmation` fields. Pydantic enforces the shape and question count, and local validation rejects non-empty evidence that is not an exact substring of the resume.

The prototype uses OpenAI provider-native structured output in strict mode. If the configured model or account does not support that feature, the script exits with an explicit message instead of falling back to unvalidated text.

## Run offline tests

These tests use a fake question provider and temporary directories inside the repository. They do not read the API key or call a remote model.

```powershell
Set-Location 'C:\path\to\job-mentor'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
