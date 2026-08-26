"""Load analysis skills. A skill is a markdown file in skills/ that tells the
analyst *how* to perform one kind of analysis. Add a skill = add a .md file."""
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
# markdown files that are shared context, not selectable analysis skills
_META = {"guardrails"}


def load_skill(name: str) -> str:
    p = SKILLS_DIR / f"{name}.md"
    return p.read_text() if p.exists() else ""


def list_skills() -> list[str]:
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md") if p.stem not in _META)


def catalog() -> str:
    """One-line description per selectable skill, for the router prompt."""
    lines = []
    for name in list_skills():
        first = ""
        for ln in load_skill(name).splitlines():
            if ln.strip() and not ln.startswith("#"):
                first = ln.strip()
                break
        lines.append(f"- {name}: {first}")
    return "\n".join(lines)
