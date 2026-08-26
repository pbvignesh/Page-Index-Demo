"""Load analysis skills. A skill is a markdown file in skills/ describing how to
perform one kind of analysis. Add a skill = add a file."""
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
_SHARED = {"guardrails"}  # applied with every analysis, not selectable on its own


def load_skill(name: str) -> str:
    path = SKILLS_DIR / f"{name}.md"
    return path.read_text() if path.exists() else ""


def list_skills() -> list[str]:
    names = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        if path.stem not in _SHARED:
            names.append(path.stem)
    return names


def catalog() -> str:
    """One line per selectable skill (its first descriptive line), for the router."""
    lines = []
    for name in list_skills():
        description = _first_description_line(load_skill(name))
        lines.append(f"- {name}: {description}")
    return "\n".join(lines)


def _first_description_line(skill_text: str) -> str:
    for line in skill_text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""
