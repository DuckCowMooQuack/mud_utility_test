from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote
import getpass
import aiohttp

BASE_URL = "https://myaccount.mudomaha.com"
LOGIN_URL = f"{BASE_URL}/sap/bc/ui5_ui5/sap/zmobius/index.html"
ODATA_BASE = f"{BASE_URL}/sap/opu/odata/sap/ZUTE_ERP_UT_UMC_SRV"


def parse_sap_date(value):
    if not isinstance(value, str):
        return None

    match = re.fullmatch(r"/Date\((-?\d+)(?:[+-]\d{4})?\)/", value)
    if not match:
        return None

    return datetime.fromtimestamp(
        int(match.group(1)) / 1000,
        tz=timezone.utc,
    )


async def login(session, username, password):
    async with session.get(
        LOGIN_URL,
        params={"sap-client": "500", "sap-language": "EN"},
    ) as response:
        response.raise_for_status()

    payload = [
        ("sap-system-login-oninputprocessing", ""),
        ("sap-urlscheme", ""),
        ("sap-system-login", "onLogin"),
        ("sap-system-login-basic_auth", ""),
        ("sap-client", "500"),
        ("sap-language", "EN"),
        ("sap-accessibility", ""),
        ("sap-system-login-cookie_disabled", ""),
        ("sap-hash", ""),
        ("sap-alias", username),
        ("sap-password", password),
        ("sap-language", "EN"),
    ]

    async with session.post(
        LOGIN_URL,
        data=payload,
        headers={"Referer": LOGIN_URL, "Origin": BASE_URL},
        allow_redirects=False,
    ) as response:
        if response.status not in (301, 302, 303):
            body = (await response.text())[:500]
            raise RuntimeError(
                f"Login failed: HTTP {response.status}: {body}"
            )


async def fetch_consumption(session, contract_id, filter_value):
    contract_key = quote(contract_id, safe="")
    url = (
        f"{ODATA_BASE}/Contracts('{contract_key}')/"
        "ContractConsumptionValues"
    )

    params = {
        "$filter": filter_value,
        "$expand": "MeterReadingCategory",
        "$format": "json",
    }

    async with session.get(
        url,
        params=params,
        headers={
            "Accept": "application/json",
            "DataServiceVersion": "2.0",
            "MaxDataServiceVersion": "2.0",
        },
    ) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(
                f"Consumption request failed: HTTP {response.status}: {text[:500]}"
            )

        payload = json.loads(text)

    rows = payload["d"]["results"]
    next_url = payload["d"].get("__next")

    return rows, next_url


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--contract", required=True)
    parser.add_argument(
        "--mode",
        choices=["no-start", "early-start"],
        default="no-start",
    )
    args = parser.parse_args()

    username = (
        args.username
        or input("MUD Username: ")
    )

    password = (
        args.password
        or getpass.getpass("MUD Password: ")
    )

    if args.mode == "no-start":
        filter_value = "ConsumptionPeriodTypeID eq 'BC'"
    else:
        filter_value = (
            "StartDate ge datetime'2000-01-01T00:00:00' "
            "and ConsumptionPeriodTypeID eq 'BC'"
        )

    async with aiohttp.ClientSession() as session:
        await login(session, username, password)
        rows, next_url = await fetch_consumption(
            session,
            args.contract,
            filter_value,
        )

    dates = [
        parse_sap_date(row.get("StartDate"))
        for row in rows
    ]
    dates = [date for date in dates if date is not None]

    print(f"Rows returned: {len(rows)}")
    print(f"Has __next pagination: {bool(next_url)}")
    if next_url:
        print(f"Next URL: {next_url}")

    if dates:
        print(f"Earliest StartDate: {min(dates).isoformat()}")
        print(f"Latest StartDate:   {max(dates).isoformat()}")

    if rows:
        print("First raw row keys:")
        print(sorted(rows[0].keys()))


if __name__ == "__main__":
    asyncio.run(main())
