#!/usr/bin/env python3
"""Run from any working directory; credentials are read only from the environment."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecast_service.pipeline import build_bulletin, write_bulletin


def main():
    parser = argparse.ArgumentParser(description='Genera il bollettino del portale locale.')
    parser.add_argument('--demo', action='store_true', help='Usa onde sintetiche, sempre etichettate come dimostrative.')
    parser.add_argument('--output', type=Path, default=ROOT / 'forecast_site/data')
    args = parser.parse_args()
    bulletin, csvs = build_bulletin(demo=args.demo)
    write_bulletin(bulletin, csvs, args.output)
    print(f"Bollettino {bulletin['mode']}: {len(bulletin['locations'])} località, generato {bulletin['generated_at']}")


if __name__ == '__main__':
    main()
