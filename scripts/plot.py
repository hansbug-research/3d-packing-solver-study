from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    rows = list(csv.DictReader((ROOT / "derived" / "tables" / "public_thpack9.csv").open()))
    names = [row["library"].replace(" patched box", "\npatched box") for row in rows]
    bins = [int(row["bins_used"]) for row in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(names, bins, color=["#2878b5", "#5aa469", "#d98c3f", "#a35d9a"])
    ax.axhline(19, color="#b33a3a", linestyle="--", linewidth=1.2, label="volume lower bound = 19")
    ax.set_ylabel("Used containers")
    ax.set_title("ESICUP THPACK9 instance 1")
    ax.legend(loc="upper left")
    ax.bar_label(bars, padding=3)
    fig.tight_layout()
    out = ROOT / "figures" / "fig01_thpack9_bins.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=160)
    plt.close(fig)
    print(out)


if __name__ == "__main__":
    main()
