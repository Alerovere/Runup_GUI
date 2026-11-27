"""Public research identity carried with every exported forecast table and card."""

RESEARCH_STATUS = 'experimental_research_non_operational'
RESEARCH_TITLE = 'Prototipo di ricerca — non validato per uso operativo'
DISCLAIMER_URL = 'https://alerovere.github.io/Runup_GUI/disclaimer.html'
RESEARCH_NOTICE = (
    'Onde a riva è uno strumento sperimentale di ricerca del progetto MARINA. '
    'Presenta elaborazioni modellistiche non validate per uso operativo. '
    'I risultati non devono essere utilizzati per previsioni operative, allerte, '
    'valutazioni di sicurezza, progettazione o decisioni gestionali. '
    'Per informazioni operative consultare i servizi ufficiali competenti.'
)
PNG_NOTICE = (
    'Non validato per uso operativo.\n'
    'Non usare per previsioni, allerte\n'
    'o decisioni gestionali.'
)


def csv_notice():
    """Repeated per row so a filtered table retains its context; no CSV preamble."""
    return dict(research_status=RESEARCH_STATUS, use_warning=RESEARCH_NOTICE,
                disclaimer_url=DISCLAIMER_URL)
