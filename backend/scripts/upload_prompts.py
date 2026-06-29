"""Upload PRism agent system prompts to Langfuse.

Run once (or whenever you want to push a new version):
    cd backend && .venv/bin/python scripts/upload_prompts.py

Agents will fetch the latest 'production'-labelled prompt at startup.
Fallback to hardcoded prompt if Langfuse is unreachable.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.agents.performance import SYSTEM_PROMPT as PERF_PROMPT
from app.agents.quality import SYSTEM_PROMPT as QUALITY_PROMPT
from app.agents.security import SYSTEM_PROMPT as SECURITY_PROMPT
from app.services.prompts import push_prompt

PROMPTS = [
    ("prism-security-agent",     SECURITY_PROMPT),
    ("prism-performance-agent",  PERF_PROMPT),
    ("prism-quality-agent",      QUALITY_PROMPT),
]

if __name__ == "__main__":
    ok = 0
    for name, text in PROMPTS:
        if push_prompt(name, text, labels=["production"]):
            print(f"  ✓ {name}")
            ok += 1
        else:
            print(f"  ✗ {name}  (check LANGFUSE_PUBLIC_KEY in .env)")
    print(f"\n{ok}/{len(PROMPTS)} prompts uploaded.")
