#!/usr/bin/env python3
"""Dry run by default. Only --send can publish to the configured test channel."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forecast_service.telegram_daily import (DeliveryError,TelegramClient,prepare_deliveries,
    restore_state,empty_state,decode_state,deliver_daily)


def main():
    parser=argparse.ArgumentParser(description='Bollettino Telegram giornaliero per Borghetto.')
    parser.add_argument('--data',type=Path,required=True,help='Cartella contenente forecast.json e social/*.png.')
    parser.add_argument('--state',type=Path,default=Path('telegram-state/receipt.json'))
    parser.add_argument('--send',action='store_true',help='Abilita l’invio reale; altrimenti verifica senza rete.')
    args=parser.parse_args();now=datetime.now(timezone.utc)
    try:
        bulletin=json.loads((args.data/'forecast.json').read_text(encoding='utf-8'))
        deliveries=prepare_deliveries(bulletin,args.data,now=now)
        if not args.send:
            for delivery in deliveries:print('Anteprima:',delivery['sector'],delivery['name'],delivery['day'])
            print(f'{len(deliveries)} infografiche verificate. Nessun messaggio inviato.');return 0
        token=os.environ.get('TELEGRAM_BOT_TOKEN','').strip();chat=os.environ.get('TELEGRAM_CHAT_ID','').strip()
        if not token or not chat:raise ValueError('Configurare TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID nei repository secrets.')
        client=TelegramClient(token,chat)
        if os.environ.get('GITHUB_ACTIONS')=='true':
            state=restore_state(os.environ['GITHUB_REPOSITORY'],os.environ['GITHUB_REPOSITORY_ID'],os.environ['TELEGRAM_DEFAULT_BRANCH'])
        else:
            state=decode_state(args.state.read_bytes()) if args.state.exists() else empty_state()
        result=deliver_daily(deliveries,client,state,args.state,now=now)
        print(f"Bollettini inviati: {result['sent']}; già inviati oggi: {result['skipped']}; esiti da verificare: {result['pending']}.")
        return 1 if result['pending'] else 0
    except (DeliveryError,ValueError,KeyError,OSError,zipfile.BadZipFile) as error:
        # API/transport exceptions are replaced upstream with token-free messages.
        print('Telegram:',str(error) if isinstance(error,(DeliveryError,ValueError)) and not isinstance(error,json.JSONDecodeError) else 'Configurazione o file non validi.',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
