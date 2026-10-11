"""English and German translations have the same keys."""
import json
from pathlib import Path

TRANSLATIONS = Path(__file__).parent.parent / "custom_components/blnet/translations"


def _keys(tree, prefix=""):
    if not isinstance(tree, dict):
        return {prefix}
    return set().union(*(_keys(v, f"{prefix}.{k}") for k, v in tree.items()))


def test_same_keys():
    en = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
    de = json.loads((TRANSLATIONS / "de.json").read_text(encoding="utf-8"))
    assert _keys(en) == _keys(de)
