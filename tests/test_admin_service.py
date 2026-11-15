"""
Admin panel read-only queries
"""

from app.models import Draw, User
from app.services.admin_service import (
    clamp_page,
    get_draw,
    get_overview,
    get_user,
    list_draws,
    list_users,
    search_people,
)
from tests.helpers import seed_admin_data


def test_overview_counts(test_db):
    seed_admin_data(test_db)
    o = get_overview(test_db)
    assert (o.users, o.draws_total, o.participants, o.devices, o.unsubscribes) == (2, 2, 4, 1, 0)
    assert o.draws_by_status == {"completed": 1, "active": 1}
    assert len(o.daily) == 30 and o.daily[-1].draws == 2 and o.daily[-1].participants == 4
    assert sum(d.draws for d in o.daily[:-1]) == 0
    assert [d.day for d in o.daily] == sorted(d.day for d in o.daily)
    ids = [d.id for d in o.latest_draws]
    assert len(ids) == 2 and ids == sorted(ids, reverse=True)


def test_overview_on_empty_database(test_db):
    o = get_overview(test_db)
    assert (o.users, o.draws_total, o.draws_by_status, o.latest_draws) == (0, 0, {}, [])
    assert len(o.daily) == 30


def test_list_draws_rows_and_filters(test_db):
    a, b = seed_admin_data(test_db)
    rows = list_draws(test_db).items
    assert {r.id: (r.creator_email, r.participant_count) for r in rows} == {
        a.id: ("ayse@example.com", 3),
        b.id: (None, 1),
    }
    assert [r.id for r in rows] == [b.id, a.id]
    assert [r.id for r in list_draws(test_db, status="completed").items] == [a.id]
    assert [r.id for r in list_draws(test_db, draw_type="manual").items] == [b.id]
    assert [r.id for r in list_draws(test_db, language="EN").items] == [a.id]
    assert len(list_draws(test_db, status="foo", draw_type="bar", language="xx").items) == 2


def test_list_draws_search(test_db):
    a, b = seed_admin_data(test_db)
    assert [r.id for r in list_draws(test_db, q="AYSE@").items] == [a.id]
    assert [r.id for r in list_draws(test_db, q=str(b.id)).items] == [b.id]
    assert [r.id for r in list_draws(test_db, q="abc_1").items] == [a.id]
    assert list_draws(test_db, q="ABC%1").items == []
    assert list_draws(test_db, q="ABCX1").items == []


def test_pagination(test_db):
    for _ in range(55):
        test_db.add(Draw())
    test_db.commit()
    p1, p2, p9 = (list_draws(test_db, page=n) for n in (1, 2, 9))
    assert (len(p1.items), p1.has_prev, p1.has_next, p1.total) == (50, False, True, 55)
    assert (len(p2.items), p2.has_prev, p2.has_next) == (5, True, False)
    assert p9.items == [] and p9.total == 55 and p9.has_next is False
    assert [clamp_page(v) for v in (None, "abc", "0", "-3", "2", 7, "")] == [1, 1, 1, 1, 2, 7, 1]


def test_draw_detail_matches(test_db):
    a, b = seed_admin_data(test_db)
    d = get_draw(test_db, a.id)
    assert d.creator_email == "ayse@example.com"
    assert [p.first_name for p in d.participants] == ["Ali", "Bora", "Cem"]
    assert [(m.giver.first_name, m.receiver.first_name) for m in d.matches] == [
        ("Ali", "Bora"),
        ("Bora", "Cem"),
        ("Cem", "Ali"),
    ]
    guest = get_draw(test_db, b.id)
    assert guest.creator_email is None and guest.matches == []
    assert get_draw(test_db, 999999) is None


def test_users(test_db):
    seed_admin_data(test_db)
    rows = {r.email: r for r in list_users(test_db).items}
    ayse, can = rows["ayse@example.com"], rows["can@example.com"]
    assert (ayse.has_password, ayse.has_apple, ayse.draw_count, ayse.device_count) == (True, False, 1, 0)
    assert (can.has_password, can.has_apple, can.has_google, can.draw_count, can.device_count) == (False, True, False, 0, 1)
    assert [r.email for r in list_users(test_db, q="CAN@").items] == ["can@example.com"]
    assert list_users(test_db, q="c_n@").items == []


def test_user_detail_participations_match_email_case_insensitively(test_db):
    a, _ = seed_admin_data(test_db)
    ayse = test_db.query(User).filter_by(email="ayse@example.com").one()
    u = get_user(test_db, ayse.id)
    assert [d.id for d in u.draws] == [a.id]
    assert [(p.participant.first_name, p.draw_id, p.drew.first_name, p.drawn_by.first_name) for p in u.participations] == [
        ("Cem", a.id, "Ali", "Bora")
    ]
    assert get_user(test_db, 999999) is None


def test_search_people_both_directions(test_db):
    a, b = seed_admin_data(test_db)
    hit = search_people(test_db, "ali kaya").items
    assert [(h.draw_id, h.draw_status, h.drew.first_name, h.drawn_by.first_name) for h in hit] == [
        (a.id, "completed", "Bora", "Cem")
    ]
    assert [h.participant.first_name for h in search_people(test_db, "BORA@EXAMPLE").items] == ["Bora"]
    pending = search_people(test_db, "100%_real").items
    assert [(h.draw_id, h.drew, h.drawn_by) for h in pending] == [(b.id, None, None)]
    assert search_people(test_db, "100%real").items == []
    assert search_people(test_db, "a").items == [] and search_people(test_db, "  ").items == []
