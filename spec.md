# spec.md — Immutable User Requirements (v0.3)

An updated version of my original wiki-local project (which was all .MD file, with one acting serving as a mermaid diagram, with filenames containing names of files, with summaries in them. This was the initial version, and I considered a later problem for user wiki. This 'later project' is this project as user wiki). This was a very basic ass project that I never released. To be made open-source and have /skills set up. Due to Andrej Karpathy revealing similar idea and setting it up, I'm going to make my own and open-source it. I won't be reading his GIT. Will make my own assessments.

## Required Features

- MD files to include names of files and imports
- MD library file, detailing imports and mermaid diagram of where imports are going to
- HTML to show the details as UX.
- MacOS, Linux and Windows variant of .bat files to test for imports to ensure they all are correctly linked, to save tokens and to ensure LLMs have a map of what's there. That bat file should have grep as download. This is to provide mapping of entire thing
- Each MD file to show file name, import at top, then purpose of what it does generally. Should NOT include any code. Each should be a summary.
- Any edits, should result in temporarily created diffs log files, like "To be committed", and if changes are implemented, these should be created.
- Automated journaling. For any new file creation and additions and commit and versioning, without the need for LLMs. Should be set up as a series of folders with dates, in system. To note steps here and there for detailed log.
  - This is what it should look like:
    - 2026
    - May | June
    - 1 May 2026.md | 2 June 2026.md
    - 2 May 2026.md | 4 June 2026.md
- The above should have an option to export to MD in Obsidian form for human readable file. LLMs should be able to read through this, otherwise LLMs can use automated files then correct them. To create very summarised details of what was done.
- This should be LLM/interface agnostic, and this must remain zero-dependency for maximum compatibility for any OS, and should not be using Docker. There may need to be a way to run constant updates at the back, but otherwise, maybe keeping it simple in the backend should work on ANY hardware.
- There should be noted issues logged by users and LLM, if there are issues. These must be saved in a folder called /Logged_issues. What issues have been, what are they logged. Types of issues should be organised by folder names, and each issues should be categorised folders in names of category of simple, moderate, high and critical. Folder names should denote the types of issues. Names of files should denote types of issues such as front end issues, backend issues, security issues, etc. A file, before the logged issues, should serve as a map, with category.
- On debug runs, LLMs should refer to this as historical documents. IF the issue files get too big for proper scan, they can be split off.
- In the root of wikifier folder, there should be a spec.md to NOTE the requirements of this project as SET by the user, to remind the LLMs and on the readme, there should be explicit note that this is meant to be a scalable light wiki project that can work with small projects to deep projects, and if humans need details, they can refer to .html file, and there should be ability to export just the map of files to LLMs in mermaid diagram. Otherwise, this is meant to be operated solely by LLM. The users may need to set rules from the start to use wikifier at every NEW session, in order to be able to utilise this project in order to map their own codebase, and utilise it effectively. It cannot pick up any prior history of edits and logs, and it should be recommended that LLMs import whatever previous logs into formats for this project.

## HTML Dashboard

In the HTML, a human should be able to observe this. This will not be a fancy wiki, as this will take up resources. This needs to be extremely efficient, and for any changes, the logging must be automated and logging everything, no matter how small changes take. There should be automated tools for this sort of purpose.

## Skills & Automation

There should be skills, and these should be automatically run by LLMs, though humans can operate with them if needed. This is meant to work with smaller to larger repos and having some form of automation should help here, by .bat, .sh or MacOS equivalent should be used at start. LLM can sleep while the processes continue. This can be its own while loop system that once everything is logged and updated and such, the system then at the end should wake the LLM, similar to heartbeat system.

## Core Principles (v0.3)

- **Agent-first design**: Every command and file is optimized for LLM consumption and autonomous operation.
- **Zero external dependencies**: Only native OS tools (bash, find, grep, stat, date, sed, etc.).
- **Semantic change tracking**: `record-change` captures *why* a change was made, not just that it happened.
- **Health Matrix driven workflow**: 🔴 Red / 🟡 Yellow files must be addressed before new work.
- **Heartbeat monitoring**: Passive background `monitor` loop keeps the wiki fresh without constant LLM attention.
- **Self-documenting**: The system documents its own usage via journals and health flips.
