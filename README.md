# Finder Agent

Organizes a messy folder (Downloads, Desktop, ...) using the Claude API.
The model only *proposes* moves; the Python code validates and performs them.
There is no delete operation, and every run can be undone.

## Install (once)

1. Get an API key at https://console.anthropic.com (API usage is billed separately from a Claude.ai subscription).
2. In Terminal:
   ```
   cd path/to/finder-agent
   ./install.sh
   finder-agent setup        # paste key; stored in macOS Keychain
   ```
   If `finder-agent` isn't found, add `~/.local/bin` to your PATH (the installer prints the command).

## Use

```
finder-agent organize downloads --dry-run        # preview only
finder-agent organize desktop                    # preview, then asks y/N
finder-agent organize ~/Downloads -i "group school files by course"
finder-agent organize downloads --apply          # no prompt
finder-agent undo                                # revert the last run
```

## macOS permissions

The first time you access Desktop/Documents/Downloads, macOS may block Terminal.
Allow it under System Settings > Privacy & Security > Files and Folders
(or Full Disk Access) for Terminal/iTerm.

## Privacy

Only file *names*, extensions, sizes, and modified dates are sent to the API. File contents never leave your Mac.

## Safety checks

Moves are rejected if the source isn't in the folder, the destination escapes it or is
deeper than 2 folders, the name would change, or something already exists at the destination.
It skips files modified in the last 2 minutes, partial downloads, symlinks, and hidden files.
Undo logs live in `~/.finder_agent/logs/`.

## Config

`AGENT_MODEL` env var overrides the model (default `claude-sonnet-5-5`).
