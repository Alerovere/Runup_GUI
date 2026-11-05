#!/usr/bin/env python3
"""Import the ZIP exported by the site-definition Colab notebook."""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forecast_service.site_package import import_site_package


def main():
    parser=argparse.ArgumentParser(description='Importa una località definita nel notebook Colab.')
    parser.add_argument('package',type=Path)
    parser.add_argument('--replace',action='store_true',help='Aggiorna una località già presente, ad esempio Borghetto.')
    parser.add_argument('--allow-demo',action='store_true',help='Consente un pacchetto dimostrativo per una prova locale.')
    args=parser.parse_args()
    slug=import_site_package(args.package,ROOT,replace=args.replace,allow_demo=args.allow_demo)
    print(f'Località importata: {slug}. Rigenerare il bollettino per aggiornare il portale.')


if __name__=='__main__':
    main()
