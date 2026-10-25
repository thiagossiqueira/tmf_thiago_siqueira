"""
Collect historical secondary-market trading records for the 103 thesis bonds
from the legacy SND / debentures.com.br database.

Source:
    https://www.debentures.com.br/
    exploreosnd/consultaadados/mercadosecundario/
    precosdenegociacao_r.asp

Security crosswalk:
    datos_y_modelos/db/brazil_domestic_corp_bonds/
    wp06c_103_bonds_exchange_id_crosswalk.csv

Important:
- Source is queried by ID_STOCK_EXCHANGE (legacy CETIP/SND code).
- Raw HTML responses are preserved unchanged.
- Parsed records are not treated as indicative quotes:
  they come from the SND "Precos de Negociacao" secondary-market table.
- One row per bond/date is expected.
- Lifecycle and identifier integrity checks are mandatory.
"""

from __future__ import annotations

import csv
import re
import ssl
import time
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


ROOT = Path(__file__).resolve().parents[1]

CROSSWALK = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_domestic_corp_bonds"
    / "wp06c_103_bonds_exchange_id_crosswalk.csv"
)

OUTPUT_ROOT = (
    ROOT
    / "datos_y_modelos"
    / "db"
    / "brazil_domestic_corp_bonds"
    / "snd_secondary_market"
)

RAW_DIR = OUTPUT_ROOT / "raw_html_103_bonds"

TRADES_OUT = OUTPUT_ROOT / "snd_103_bonds_trades_raw.csv"
SUMMARY_OUT = OUTPUT_ROOT / "snd_103_bonds_collection_summary.csv"

BASE_URL = (
    "https://www.debentures.com.br/"
    "exploreosnd/consultaadados/mercadosecundario/"
)

QUERY_URL = BASE_URL + "precosdenegociacao_r.asp"

START_DATE = "01/01/2010"
END_DATE = "31/12/2025"

REQUEST_DELAY_SECONDS = 1.0
MAX_ATTEMPTS = 3


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag == "tr":
            self.row = []

        elif tag in ("td", "th") and self.row is not None:
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(self.cell.split()))
            self.cell = None

        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def load_crosswalk():
    with CROSSWALK.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 103:
        raise RuntimeError(
            f"Expected 103 crosswalk rows; found {len(rows)}"
        )

    ids = [x["ID"] for x in rows]

    if len(set(ids)) != 103:
        raise RuntimeError("Bloomberg IDs are not unique.")

    assets = [
        x["ID_STOCK_EXCHANGE"].strip()
        for x in rows
    ]

    if any(not x for x in assets):
        raise RuntimeError(
            "Missing ID_STOCK_EXCHANGE in crosswalk."
        )

    return sorted(
        rows,
        key=lambda x: (
            x["ISSUE_DT"],
            x["ID"],
        ),
    )


def fetch_asset(asset):
    payload = {
        "op_exc": "Nada",
        "dt_ini": START_DATE,
        "dt_fim": END_DATE,
        "emissor": "",
        "ativo": asset.ljust(10),
        "ISIN": "",
    }

    data = urlencode(payload).encode("ascii")

    req = Request(
        QUERY_URL,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type":
                "application/x-www-form-urlencoded",
            "Referer":
                BASE_URL
                + "precosdenegociacao_f.asp?op_exc=Nada",
        },
        method="POST",
    )

    context = ssl._create_unverified_context()

    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urlopen(
                req,
                timeout=90,
                context=context,
            ) as response:
                raw = response.read()

                charset = (
                    response.headers.get_content_charset()
                    or "latin-1"
                )

            return raw, charset

        except (URLError, HTTPError, TimeoutError) as exc:
            last_error = exc

            if attempt < MAX_ATTEMPTS:
                sleep_seconds = 5 * attempt
                print(
                    f"   attempt {attempt} failed; "
                    f"retrying in {sleep_seconds}s: {exc}"
                )
                time.sleep(sleep_seconds)

    raise RuntimeError(
        f"Failed after {MAX_ATTEMPTS} attempts: {last_error}"
    )


def parse_trades(html, bond):
    asset = bond["ID_STOCK_EXCHANGE"].strip()
    expected_isin = bond["ID_ISIN"].strip().upper()

    parser = TableParser()
    parser.feed(html)

    output = []

    for row in parser.rows:
        cleaned = [
            value.strip()
            for value in row
            if value.strip()
        ]

        if asset not in cleaned:
            continue

        if not any(
            re.fullmatch(
                r"\d{2}/\d{2}/\d{4}",
                value,
            )
            for value in cleaned
        ):
            continue

        if len(cleaned) < 10:
            raise RuntimeError(
                f"Unexpected SND row for {asset}: {cleaned}"
            )

        record = {
            "bloomberg_id": bond["ID"],
            "ativo": cleaned[2],
            "isin": cleaned[3],
            "trade_date": cleaned[0],
            "emissor_snd": cleaned[1],
            "quantity_raw": cleaned[4],
            "num_trades_raw": cleaned[5],
            "pu_min_raw": cleaned[6],
            "pu_avg_raw": cleaned[7],
            "pu_max_raw": cleaned[8],
            "pct_pu_curve_raw": cleaned[9],
            "source": "SND_debentures.com.br",
        }

        if record["ativo"].strip() != asset:
            raise RuntimeError(
                f"Asset mismatch for {bond['ID']}: "
                f"{record['ativo']} != {asset}"
            )

        if record["isin"].strip().upper() != expected_isin:
            raise RuntimeError(
                f"ISIN mismatch for {bond['ID']}: "
                f"{record['isin']} != {expected_isin}"
            )

        output.append(record)

    return output


def main():
    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    RAW_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    bonds = load_crosswalk()

    all_trades = []
    summary = []

    for i, bond in enumerate(bonds, start=1):
        bb_id = bond["ID"]
        asset = bond["ID_STOCK_EXCHANGE"].strip()
        isin = bond["ID_ISIN"].strip()

        raw_path = (
            RAW_DIR
            / f"snd_{asset}_20100101_20251231.html"
        )

        print(
            f"[{i:03d}/103] "
            f"{bb_id} -> {asset} -> {isin}"
        )

        if raw_path.exists():
            raw = raw_path.read_bytes()
            charset = "latin-1"
            source_status = "existing_raw"

        else:
            raw, charset = fetch_asset(asset)
            raw_path.write_bytes(raw)
            source_status = "downloaded"
            time.sleep(REQUEST_DELAY_SECONDS)

        html = raw.decode(
            charset,
            errors="replace",
        )

        bond_trades = parse_trades(
            html,
            bond,
        )

        dates = [
            datetime.strptime(
                x["trade_date"],
                "%d/%m/%Y",
            )
            for x in bond_trades
        ]

        issue_dt = datetime.strptime(
            bond["ISSUE_DT"][:10],
            "%Y-%m-%d",
        )

        maturity = datetime.strptime(
            bond["MATURITY"][:10],
            "%Y-%m-%d",
        )

        before_issue = [
            d for d in dates
            if d < issue_dt
        ]

        on_after_maturity = [
            d for d in dates
            if d >= maturity
        ]

        if before_issue:
            raise RuntimeError(
                f"{asset}: {len(before_issue)} "
                "trades before issue."
            )

        if on_after_maturity:
            raise RuntimeError(
                f"{asset}: {len(on_after_maturity)} "
                "trades on/after maturity."
            )

        if len(dates) != len(set(dates)):
            raise RuntimeError(
                f"{asset}: duplicate bond-date records."
            )

        all_trades.extend(bond_trades)

        summary.append({
            "bloomberg_id": bb_id,
            "ativo": asset,
            "isin": isin,
            "issue_dt": bond["ISSUE_DT"],
            "maturity": bond["MATURITY"],
            "trade_days": len(dates),
            "first_trade":
                min(dates).strftime("%Y-%m-%d")
                if dates else "",
            "last_trade":
                max(dates).strftime("%Y-%m-%d")
                if dates else "",
            "raw_status": source_status,
        })

        print(
            f"   trade-days={len(dates)} "
            f"first="
            f"{min(dates).date() if dates else 'NONE'} "
            f"last="
            f"{max(dates).date() if dates else 'NONE'} "
            f"[{source_status}]"
        )

    trade_fields = [
        "bloomberg_id",
        "ativo",
        "isin",
        "trade_date",
        "emissor_snd",
        "quantity_raw",
        "num_trades_raw",
        "pu_min_raw",
        "pu_avg_raw",
        "pu_max_raw",
        "pct_pu_curve_raw",
        "source",
    ]

    with TRADES_OUT.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=trade_fields,
        )
        writer.writeheader()
        writer.writerows(all_trades)

    summary_fields = [
        "bloomberg_id",
        "ativo",
        "isin",
        "issue_dt",
        "maturity",
        "trade_days",
        "first_trade",
        "last_trade",
        "raw_status",
    ]

    with SUMMARY_OUT.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=summary_fields,
        )
        writer.writeheader()
        writer.writerows(summary)

    print("\n=== SND COLLECTION COMPLETE ===")
    print("Bonds:", len(summary))
    print("Bonds with >=1 trade:", sum(
        int(x["trade_days"]) > 0
        for x in summary
    ))
    print("Total bond-trade-days:", len(all_trades))
    print("Raw directory:", RAW_DIR)
    print("Trades:", TRADES_OUT)
    print("Summary:", SUMMARY_OUT)


if __name__ == "__main__":
    main()
