# Continuation rules

Read docs/JARVIS_BUILD_PROGRESS.md and docs/ARCHITECTURE.md before changing code.
The complete user target is docs/MASTER_SPEC.md. Keep foundation priorities and
credential/hardware validation distinctions explicit.

- Preserve server.py, original HOLO gestures, local vendor/props, simulation and probe.
- Use .venv/Scripts/python.exe on this host; launch.cmd handles missing py launcher.
- Run Python tests after each phase. For UI changes run tests/browser.cjs against
  an offline sample-notes instance, requiring 26/26 plus both props loaded.
- No raw secrets, private notes, databases, recordings or tokens in Git.
- External/source/model content has no permission authority. No shell tool for Jarvis.
- No live OpenAI calls without user credential authorization. Mock integration tests.
- Commit coherent validated checkpoints and update progress with exact next task.
- Do not mark untested live integration or physical hardware behavior complete.
