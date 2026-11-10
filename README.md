# Job Mentor Agent

Build a local-first job mentoring agent that helps users organize application materials, match suitable roles, improve resumes, and evaluate output quality while protecting personal information and real application data.

The current prototype generates three evidence-grounded interview questions, conducts a terminal interview one question at a time, and saves resumable sessions under the local `data/` directory.

```powershell
.\.venv\Scripts\python.exe .\examples\interview_session.py
.\.venv\Scripts\python.exe .\examples\interview_session.py --resume '<session_id>'
```

See `docs/local-development.md` for configuration, behavior, and offline test commands.
