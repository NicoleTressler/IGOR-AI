#!/usr/bin/env python3
"""
finder_agent.py - a small AI agent that organizes a folder on your Mac.

Design (plan -> validate -> execute -> undo):
  1. SCAN     read file *metadata* only (name, type, size, date). No file contents.
  2. PLAN     ask Claude for a JSON list of moves.
  3. VALIDATE reject anything unsafe (outside the folder, overwrites, unknown files).
  4. EXECUTE  dry-run by default; --apply actually moves files and writes an undo log.
  5. UNDO     reverse the most recent run.

The model never touches the filesystem. It only proposes; this code decides.
There is deliberately no delete operation.

Setup:
  pip install anthropic
  export ANTHROPIC_API_KEY=sk-ant-...

Usage:
  python finder_agent.py organize ~/Downloads
  python finder_agent.py organize ~/Downloads -i "group school files by course"
  python finder_agent.py organize ~/Downloads --apply
  python finder_agent.py undo
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import anthropic

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5")
LOG_DIR = Path.home() / ".finder_agent"
SKIP_NAMES = {".DS_Store", ".localized"}
MAX_FILES = 300  # keep prompts small; run again for the rest

SYSTEM_PROMPT = """You organize files in a single folder.
You receive a JSON list of items (name, is_dir, ext, size_kb, modified).
Return ONLY JSON, no prose, no code fences, in exactly this shape:
{"moves": [{"from": "<existing item name>", "to": "<Folder>/<same item name>", "reason": "<short>"}]}
Rules:
- Only move files (is_dir=false). Never move existing folders.
- Destination must be a relative path of at most 2 levels, e.g. "Images/Screenshots/foo.png".
- Keep the file name unchanged.
- Prefer reusing existing folders. Create few, broad, clearly named new folders.
- Leave a file alone (omit it) if you are unsure where it belongs.
- Follow the user's extra instructions if given."""


def scan(root: Path) -> list[dict]:
    items = []
    for p in sorted(root.iterdir()):
        if p.name in SKIP_NAMES or p.name.startswith("."):
            continue
        st = p.stat()
        items.append({
            "name": p.name,
            "is_dir": p.is_dir(),
            "ext": p.suffix.lower(),
            "size_kb": round(st.st_size / 1024),
            "modified": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)),
        })
        if len(items) >= MAX_FILES:
            break
    return items


def plan(items: list[dict], instructions: str) -> list[dict]:
    client = anthropic.Anthropic()
    user_msg = json.dumps(items)
    if instructions:
        user_msg += f"\n\nExtra instructions: {instructions}"
    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)["moves"]


def validate(root: Path, items: list[dict], moves: list[dict]):
    files = {i["name"] for i in items if not i["is_dir"]}
    ok, rejected, used_dests = [], [], set()
    for m in moves:
        src_name, dest_rel = m.get("from", ""), m.get("to", "")
        problem = None
        dest = (root / dest_rel).resolve()
        if src_name not in files:
            problem = "source is not a known file in this folder"
        elif Path(dest_rel).is_absolute() or ".." in Path(dest_rel).parts:
            problem = "destination escapes the folder"
        elif root.resolve() not in dest.parents:
            problem = "destination outside the folder"
        elif Path(dest_rel).name != src_name:
            problem = "file name must not change"
        elif dest.exists() or dest in used_dests:
            problem = "destination already exists"
        if problem:
            rejected.append((m, problem))
        else:
            used_dests.add(dest)
            ok.append({"src": str((root / src_name).resolve()),
                       "dest": str(dest), "reason": m.get("reason", "")})
    return ok, rejected


def execute(moves: list[dict], apply: bool) -> None:
    for m in moves:
        print(f"  {Path(m['src']).name}  ->  {Path(m['dest']).parent.name}/   ({m['reason']})")
    if not apply:
        print("\nDry run only. Re-run with --apply to move files.")
        return
    done = []
    for m in moves:
        Path(m["dest"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(m["src"], m["dest"])
        done.append(m)
    LOG_DIR.mkdir(exist_ok=True)
    log = LOG_DIR / f"run-{int(time.time())}.json"
    log.write_text(json.dumps(done, indent=2))
    print(f"\nMoved {len(done)} files. Undo log: {log}")


def undo() -> None:
    logs = sorted(LOG_DIR.glob("run-*.json"))
    if not logs:
        sys.exit("Nothing to undo.")
    latest = logs[-1]
    for m in reversed(json.loads(latest.read_text())):
        if Path(m["dest"]).exists() and not Path(m["src"]).exists():
            shutil.move(m["dest"], m["src"])
            parent = Path(m["dest"]).parent
            if not any(parent.iterdir()):
                parent.rmdir()  # remove folder we created if now empty
    latest.rename(latest.with_suffix(".undone"))
    print(f"Reverted {latest.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="AI-assisted folder organizer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    org = sub.add_parser("organize")
    org.add_argument("folder")
    org.add_argument("-i", "--instructions", default="")
    org.add_argument("--apply", action="store_true")
    sub.add_parser("undo")
    args = ap.parse_args()

    if args.cmd == "undo":
        return undo()

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"Not a folder: {root}")
    if root == Path.home().resolve():
        sys.exit("Refusing to organize your entire home folder. Pick a subfolder.")

    items = scan(root)
    print(f"Scanned {len(items)} items in {root}")
    moves = plan(items, args.instructions)
    ok, rejected = validate(root, items, moves)
    print(f"\nProposed {len(ok)} moves ({len(rejected)} rejected by safety checks):")
    execute(ok, args.apply)
    for m, why in rejected:
        print(f"  skipped {m.get('from')}: {why}")


if __name__ == "__main__":
    main()
