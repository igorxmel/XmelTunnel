from xmeltunnel import changelog

TEXT = """# x

## 0.3.0

new

## 0.2.9

- fix

## 0.2.8

old
"""


def test_since_and_section():
    assert [v for v, _ in changelog.since("0.2.8", "0.3.0", TEXT)] == ["0.3.0", "0.2.9"]
    assert [v for v, _ in changelog.since("", "0.2.9", TEXT)] == ["0.2.9", "0.2.8"]
    assert changelog.section("0.3.0-rc.1", TEXT) == "new"
    assert not changelog.should_show("", "0.3.0", True)       # first run: the welcome window instead
    assert changelog.should_show("", "0.3.0", False)          # updated from a version without the mark
    assert not changelog.should_show("0.3.0", "0.3.0", False)
