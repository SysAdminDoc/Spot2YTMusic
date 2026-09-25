import re
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
HERO = ROOT / "docs" / "hero.svg"


def test_readme_has_one_evergreen_hero_and_support_link():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    hero = HERO.read_text(encoding="utf-8")
    assert readme.startswith("![Spot2YTMusic](docs/hero.svg)\n")
    assert readme.count("docs/hero.svg") == 1
    assert "https://ko-fi.com/X8K126YVER" in readme
    assert not re.search(r"\bv\d+\.\d+\.\d+\b", hero)
    assert HERO.read_bytes() == (ROOT / "docs/marketing/concepts/hero-dark-selected.svg").read_bytes()


def test_hero_has_expected_canvas_and_accessible_title():
    root = ElementTree.parse(HERO).getroot()
    assert (root.attrib["width"], root.attrib["height"]) == ("1280", "420")
    assert root.attrib["viewBox"] == "0 0 1280 420"
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    assert root.find("svg:title", namespace).text == "Spot2YTMusic"
