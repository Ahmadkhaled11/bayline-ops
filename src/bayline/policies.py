"""Read the Customer Service documents by a safe slug."""

from .config import docs_path
from .repository import NotFoundError


def list_documents(root=None):
    root = root or docs_path()
    result = []
    for folder in ("policies", "handbook"):
        for path in sorted((root / folder).glob("*.md")):
            title = path.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ")
            result.append({"slug": path.stem, "title": title})
    return sorted(result, key=lambda d: d["slug"])


def get_document(slug, root=None):
    root = root or docs_path()
    for folder in ("policies", "handbook"):
        if slug in {p.stem for p in (root / folder).glob("*.md")}:
            return (root / folder / (slug + ".md")).read_text(encoding="utf-8")
    raise NotFoundError("Policy document not found")
