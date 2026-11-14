"""Figures (023, research R1, FR-004, FR-005a): every amount in an answer is written by the app
from the pricing engine's value; amounts the model types itself are removed."""

from __future__ import annotations

import random
from decimal import Decimal

import pytest

from src.agent.figures import FigureBook, FigureStreamFilter, footer, format_usd

SNAP = {"aws": {"date": "2026-11-02", "revision": 2}}


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (Decimal("1780.955"), "$1,780.96"),  # half-up
        (Decimal("1780.954999"), "$1,780.95"),
        (Decimal("0"), "$0.00"),
        (Decimal("1234567.891"), "$1,234,567.89"),
        (Decimal("-2061.555"), "-$2,061.56"),
    ],
)
def test_format_usd(amount, text):
    assert format_usd(amount) == text


def test_references_are_numbered_and_rendered():
    book = FigureBook()
    assert book.add(Decimal("1780.96"), "total", duration="1_month", snapshot=SNAP) == "F1"
    assert book.add(Decimal("12.5"), "S3", duration="1_month", snapshot=SNAP) == "F2"
    out = FigureStreamFilter(book)
    text = out.feed("Total [[F1]], S3 [[F2]], bad [[F9]].") + out.flush()
    assert text == "Total $1,780.96, S3 $12.50, bad [figure unavailable]."
    assert out.used == ["F1", "F2"]


@pytest.mark.parametrize("written", ["$[[F1]]", "$ [[F1]]", "[[F1]] USD", "USD [[F1]]"])
def test_currency_around_a_reference_is_not_doubled(written):
    book = FigureBook()
    book.add(Decimal("398.85"), "total", duration="1_month", snapshot=SNAP)
    out = FigureStreamFilter(book)
    assert out.feed(f"It costs {written}.") + out.flush() == "It costs $398.85."


@pytest.mark.parametrize(
    "written",
    ["$12.50", "$ 12", "12.50 USD", "USD 12.50", "1,780.96", "40%", "12.5 %", "3.75"],
)
def test_money_the_model_writes_itself_is_removed(written):
    out = FigureStreamFilter(FigureBook())
    text = out.feed(f"It costs {written} now.") + out.flush()
    assert text == "It costs [figure removed] now."
    assert out.removed == 1


@pytest.mark.parametrize(
    "plain", ["3 services", "31 days", "1 month", "365 days", "us-east-1", "snapshot r2", "USD"]
)
def test_plain_numbers_and_words_pass_through(plain):
    out = FigureStreamFilter(FigureBook())
    assert out.feed(f"It has {plain} here.") + out.flush() == f"It has {plain} here."
    assert out.removed == 0


def test_any_chunk_split_gives_the_same_text():
    book = FigureBook()
    book.add(Decimal("1780.96"), "total", duration="1_month", snapshot=SNAP)
    source = "The total is [[F1]] per month; I'd guess $1,780.96 USD myself, over 31 days."
    expected = "The total is $1,780.96 per month; I'd guess [figure removed] myself, over 31 days."
    rng = random.Random(7)
    for _ in range(200):
        out = FigureStreamFilter(book)
        cuts = sorted(rng.sample(range(1, len(source)), rng.randint(1, 12)))
        pieces = [source[a:b] for a, b in zip([0, *cuts], [*cuts, len(source)], strict=True)]
        assert "".join(out.feed(p) for p in pieces) + out.flush() == expected


def test_text_is_released_progressively():
    out = FigureStreamFilter(FigureBook())
    assert out.feed("The architecture has ") == "The architecture has "
    assert out.feed("three collections.") == "three collections."
    # A possible amount is held back only until it can be told apart.
    assert out.feed("It has 3") == "It has "
    assert out.feed(" services.") == "3 services."


def test_footer_names_duration_and_snapshot_of_figures_used():
    book = FigureBook()
    book.add(Decimal("1"), "a", duration="1_month", snapshot=SNAP)
    book.add(Decimal("2"), "b", duration="1_month", snapshot=SNAP)
    assert footer(book, ["F1", "F2"]) == "Prices for 1 month (31 days), snapshot 2026-11-02 r2"
    assert footer(book, []) is None


def test_footer_lists_each_provider_and_duration():
    book = FigureBook()
    book.add(Decimal("1"), "a", duration="1_month",
             snapshot={"gcp": {"date": "2026-11-02", "revision": 2}})
    book.add(Decimal("2"), "b", duration="1_year",
             snapshot={"azure": {"date": "2026-11-01", "revision": 1}})
    assert footer(book, ["F1", "F2"]) == (
        "Prices for 1 month (31 days) and 1 year (365 days), "
        "snapshots azure 2026-11-01 r1, gcp 2026-11-02 r2"
    )


# --- 024: percent figures (research R7) ---------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        (Decimal("12.345"), "+12.3%"),
        (Decimal("12.35"), "+12.4%"),  # half-up
        (Decimal("-4"), "-4.0%"),
        (Decimal("0"), "0.0%"),
    ],
)
def test_percent_figures_render_with_a_sign_and_one_decimal(amount, text):
    book = FigureBook()
    ref = book.add(amount, "diff_pct", kind="percent")
    out = FigureStreamFilter(book)
    assert out.feed(f"Azure is [[{ref}]] dearer.") + out.flush() == f"Azure is {text} dearer."


def test_a_percent_sign_after_a_percent_reference_is_not_doubled():
    book = FigureBook()
    ref = book.add(Decimal("5"), "diff_pct", kind="percent")
    out = FigureStreamFilter(book)
    assert out.feed(f"[[{ref}]]% more") + out.flush() == "+5.0% more"


def test_money_figures_still_render_as_usd_and_typed_percentages_are_removed():
    book = FigureBook()
    money = book.add(Decimal("1234.561"), "total")
    out = FigureStreamFilter(book)
    text = out.feed(f"Total [[{money}]], about 12% more.") + out.flush()
    assert text == "Total $1,234.56, about [figure removed] more."


def test_footer_ignores_percent_figures():
    book = FigureBook()
    pct = book.add(Decimal("3"), "diff_pct", kind="percent")
    money = book.add(Decimal("1"), "total", duration="1_month", snapshot=SNAP)
    assert footer(book, [pct]) is None
    assert footer(book, [pct, money]) == "Prices for 1 month (31 days), snapshot 2026-11-02 r2"


def test_round_cents_matches_format_usd():
    from src.agent.figures import round_cents

    assert str(round_cents(Decimal("1780.955"))) == "1780.96"
    assert str(round_cents(Decimal("-2061.555"))) == "-2061.56"
    assert str(round_cents(Decimal("3"))) == "3.00"
