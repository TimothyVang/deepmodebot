# Windows process ownership

Run `control.py doctor` first. Use Windows, repo-local `TMP`/`TEMP`/`TMPDIR`, `-B`, and an exclusive build lease. Never terminate another session's processes.

The real `assets/loop/test_windows_job.py` surface creates finite benign Python/Bash/virtualenv process trees, named events and held process handles. Verify stdin closure, supervisor termination, an exited intermediate retaining stdout, direct/Bash deadlines and virtualenv descendants. Every observed descendant must exit and pipes must drain; exit code alone is insufficient.

Deadline fixtures first reach actual tree readiness through a real `Popen` subclass inside the isolated fixture interpreter. Only then does the existing `run_limited` communicate deadline begin. Bootstrap remains bounded by the fixture lifetime and is reported separately from the deadline phase. No fake processes/PIDs, mocked timeout/kill/clock, sleep-based synchronization, removed assertions or retry-until-green.

The supervisor uses the loaded physical interpreter, not a Store/venv redirector as owner. A same-interpreter child retains virtualenv context without the redirector's nested silent-breakaway Job. Verify the virtualenv executable/prefix as well as process death. This does not establish OS credential isolation or provider-side generation/billing cancellation.

Retain any readiness/cleanup failure and controller diagnostics. A historic two-second deadline/three-second readiness-window failure is evidence of an unsuccessful run, not proof of a particular transient cause. Fresh verification follows the ownership/coordination repair; do not erase or reclassify the failure.
