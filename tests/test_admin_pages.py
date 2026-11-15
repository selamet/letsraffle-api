"""
Admin panel pages render the right data
"""

from datetime import datetime, timezone

from app.models import Draw, Participant, User
from tests.helpers import seed_admin_data


def test_overview_shows_totals_and_latest(admin_client, test_db):
    a, b = seed_admin_data(test_db)
    html = admin_client.get("/admin").text
    assert "ayse@example.com" in html
    assert f'href="/admin/draws/{a.id}"' in html and f'href="/admin/draws/{b.id}"' in html


def test_overview_renders_on_empty_database(admin_client):
    assert admin_client.get("/admin").status_code == 200


def test_draws_list_filter_and_search(admin_client, test_db):
    a, b = seed_admin_data(test_db)
    html = admin_client.get("/admin/draws").text
    assert f'href="/admin/draws/{a.id}"' in html and f'href="/admin/draws/{b.id}"' in html and "misafir" in html
    html = admin_client.get("/admin/draws", params={"status": "completed"}).text
    assert f'href="/admin/draws/{a.id}"' in html and f'href="/admin/draws/{b.id}"' not in html
    html = admin_client.get("/admin/draws", params={"q": "ayse@"}).text
    assert f'href="/admin/draws/{a.id}"' in html and f'href="/admin/draws/{b.id}"' not in html


def test_draws_list_survives_bad_query_values(admin_client, test_db):
    seed_admin_data(test_db)
    for params in ({"status": "foo", "page": "abc"}, {"page": "-3"}, {"page": "999"}, {"q": "%_\\"}, {"q": "9" * 40}):
        assert admin_client.get("/admin/draws", params=params).status_code == 200, params


def test_draws_pagination_links_keep_filters(admin_client, test_db):
    for _ in range(55):
        test_db.add(Draw(status="active"))
    test_db.commit()
    html = admin_client.get("/admin/draws", params={"status": "active"}).text
    assert "status=active&amp;page=2" in html or "page=2&amp;status=active" in html
    html = admin_client.get("/admin/draws", params={"status": "active", "page": "2"}).text
    assert "page=1" in html and "page=3" not in html


def test_draw_detail_shows_participants_and_matches(admin_client, test_db):
    a, b = seed_admin_data(test_db)
    html = admin_client.get(f"/admin/draws/{a.id}").text
    for text in ("Ali Kaya", "bora@example.com", "ABC_1", "Tamamlandı", "ayse@example.com"):
        assert text in html, text
    assert "Henüz çekiliş yapılmadı" not in html
    assert "Henüz çekiliş yapılmadı" in admin_client.get(f"/admin/draws/{b.id}").text


def test_unknown_draw_is_404(admin_client):
    r = admin_client.get("/admin/draws/999999")
    assert r.status_code == 404 and "Böyle bir çekiliş yok" in r.text


def test_participant_text_is_escaped(admin_client, test_db):
    d = Draw()
    test_db.add(d)
    test_db.flush()
    test_db.add(
        Participant(
            draw_id=d.id,
            first_name="<script>alert(1)</script>",
            last_name="X",
            email="x@example.com",
            address="<b>ev</b>",
        )
    )
    test_db.commit()
    html = admin_client.get(f"/admin/draws/{d.id}").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html and "<b>ev</b>" not in html
    html = admin_client.get("/admin/people", params={"q": "<script>"}).text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_dates_render_in_istanbul_time(admin_client, test_db):
    d = Draw(draw_date=datetime(2026, 11, 15, 11, 30, tzinfo=timezone.utc))
    test_db.add(d)
    test_db.commit()
    assert "15 Kas 2026 14:30" in admin_client.get(f"/admin/draws/{d.id}").text


def test_users_list_and_search(admin_client, test_db):
    seed_admin_data(test_db)
    html = admin_client.get("/admin/users").text
    assert "ayse@example.com" in html and "can@example.com" in html and "Apple" in html
    html = admin_client.get("/admin/users", params={"q": "can@"}).text
    assert "can@example.com" in html and "ayse@example.com" not in html


def test_user_detail(admin_client, test_db):
    a, _ = seed_admin_data(test_db)
    uid = test_db.query(User).filter_by(email="ayse@example.com").one().id
    html = admin_client.get(f"/admin/users/{uid}").text
    assert f'href="/admin/draws/{a.id}"' in html
    for name in ("Cem", "Ali", "Bora"):
        assert name in html


def test_unknown_user_is_404(admin_client):
    r = admin_client.get("/admin/users/999999")
    assert r.status_code == 404 and "Böyle bir kullanıcı yok" in r.text


def test_people_search(admin_client, test_db):
    a, _ = seed_admin_data(test_db)
    html = admin_client.get("/admin/people", params={"q": "ali kaya"}).text
    assert f'href="/admin/draws/{a.id}"' in html and "Bora" in html and "Cem" in html
    assert "En az 2 karakter yaz" in admin_client.get("/admin/people", params={"q": "a"}).text
    assert "Kimse bulunamadı" in admin_client.get("/admin/people", params={"q": "zzzz"}).text
    assert "Kimse bulunamadı" in admin_client.get("/admin/people", params={"q": "100%real"}).text
    empty = admin_client.get("/admin/people")
    assert empty.status_code == 200 and "Kimse bulunamadı" not in empty.text


def test_odd_input_never_becomes_a_server_error(admin_client, test_db):
    seed_admin_data(test_db)
    huge = "9" * 30
    for path, params, expected in (
        ("/admin/draws", {"q": "²"}, 200),
        ("/admin/draws", {"q": "abc\x00def"}, 200),
        ("/admin/draws", {"page": huge}, 200),
        ("/admin/users", {"page": huge}, 200),
        ("/admin/people", {"q": "ali", "page": huge}, 200),
        (f"/admin/draws/{huge}", None, 404),
        (f"/admin/users/{huge}", None, 404),
        ("/admin/draws/abc", None, 404),
        ("/admin/users/-1", None, 404),
    ):
        r = admin_client.get(path, params=params)
        assert r.status_code == expected, (path, params)
        assert "text/html" in r.headers["content-type"], (path, params)
