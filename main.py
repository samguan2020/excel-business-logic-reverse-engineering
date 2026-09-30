"""
main.py — CLI entrypoint

Usage:
    python main.py sample/finance_sample.xlsx --out report.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from src.agent import run

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Finance Excel Reverse Engineering (experimental prototype)")
    parser.add_argument("workbook", help="Path to the .xlsx workbook to reverse-engineer")
    parser.add_argument("--out", default="report.md", help="Output markdown report path")
    args = parser.parse_args()

    console.print(f"[bold cyan]Analyzing[/bold cyan] {args.workbook} ...")
    report = run(args.workbook)
    Path(args.out).write_text(report, encoding="utf-8")
    console.print(f"[bold green]Done.[/bold green] Report written to {args.out}")


if __name__ == "__main__":
    main()
