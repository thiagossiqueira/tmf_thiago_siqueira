import numpy as np
import pandas as pd

from config import CONFIG
from src.utils.file_io import load_di_surface


def test_taxas_e_terms_corretos_para_2025_06_30():
    """
    Integrity test for the reconstructed nominal DI curve
    on 2025-06-30.

    Expected source hierarchy:
      - BZDIOVRA cash anchor;
      - liquid DI futures beyond the cash tenor;
      - Pre x DI swaps only beyond the longest retained future.
    """

    surface = load_di_surface(
        CONFIG["HIST_CURVE_PATH"]
    )

    actual = (
        surface[
            surface["obs_date"].eq(
                pd.Timestamp("2025-06-30")
            )
        ][
            [
                "generic_ticker_id",
                "yield",
                "tenor",
            ]
        ]
        .sort_values("tenor")
        .reset_index(drop=True)
    )

    expected = pd.DataFrame(
        [
            ("BZDIOVRA Index", 14.9000, 0.003968),
            ("OD2 Comdty", 14.9070, 0.095238),
            ("OD3 Comdty", 14.9230, 0.178571),
            ("OD4 Comdty", 14.9330, 0.265873),
            ("OD5 Comdty", 14.9330, 0.357143),
            ("OD6 Comdty", 14.9330, 0.432540),
            ("OD7 Comdty", 14.9280, 0.519841),
            ("OD8 Comdty", 14.9180, 0.603175),
            ("OD9 Comdty", 14.8970, 0.674603),
            ("OD10 Comdty", 14.8610, 0.761905),
            ("OD11 Comdty", 14.8090, 0.841270),
            ("OD12 Comdty", 14.7480, 0.920635),
            ("OD13 Comdty", 14.6750, 1.003968),
            ("OD16 Comdty", 14.3960, 1.261905),
            ("OD19 Comdty", 14.0920, 1.507937),
            ("OD22 Comdty", 13.8460, 1.746032),
            ("OD25 Comdty", 13.6070, 1.996032),
            ("OD28 Comdty", 13.4170, 2.253968),
            ("OD31 Comdty", 13.2510, 2.503968),
            ("OD32 Comdty", 13.1480, 2.753968),
            ("OD33 Comdty", 13.0970, 2.996032),
            ("OD34 Comdty", 13.0830, 3.250000),
            ("OD37 Comdty", 13.0700, 3.488095),
            ("OD38 Comdty", 13.0670, 3.730159),
            ("OD39 Comdty", 13.0940, 3.980159),
            ("OD40 Comdty", 13.0940, 4.234127),
            ("OD43 Comdty", 13.1160, 4.476190),
            ("BCSFSPDV Curncy", 13.1499, 4.960317),
            ("BCSFTPDV Curncy", 13.2302, 5.956349),
            ("BCSFUPDV Curncy", 13.2767, 6.964286),
            ("BCSFVPDV Curncy", 13.2793, 7.964286),
            ("BCSFWPDV Curncy", 13.2825, 8.960317),
            ("BCSFXPDV Curncy", 13.2746, 9.944444),
            ("BCSFYPDV Curncy", 13.2519, 10.928571),
            ("BCSFZPDV Curncy", 13.2123, 11.928571),
        ],
        columns=[
            "generic_ticker_id",
            "yield",
            "tenor",
        ],
    )

    assert len(actual) == len(expected)

    assert (
        actual["generic_ticker_id"].tolist()
        == expected["generic_ticker_id"].tolist()
    )

    assert np.allclose(
        actual["yield"].to_numpy(),
        expected["yield"].to_numpy(),
        atol=1e-6,
    )

    assert np.allclose(
        actual["tenor"].to_numpy(),
        expected["tenor"].to_numpy(),
        atol=1e-6,
    )

    assert "OD1 Comdty" not in actual[
        "generic_ticker_id"
    ].values

    assert actual["tenor"].duplicated().sum() == 0