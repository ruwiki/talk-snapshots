from app import speedy


def test_every_subclass_and_wiki_renders():
    d = speedy.data()
    assert len(d["subclasses"]) > 50 and len(speedy._wikis()) >= 50
    for s in d["subclasses"]:
        html = speedy.render_defect(s["key"])
        assert html and speedy.esc(s["name"]) in html
    for w in speedy._wikis():
        assert speedy.render_wiki(w)
    assert speedy.render_index()


def test_unknown_returns_none():
    assert speedy.render_defect("9:nope") is None
    assert speedy.render_wiki("nowiki_x") is None


def test_hewiki_has_no_template_but_request_page():
    html = speedy.render_defect("1:S1")
    assert "בקשות ממפעילים" in html
