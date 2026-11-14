"""Notebook boxes for ambiguous assignments and public coastal-sector names."""
import html


class SectorAssignmentEditor:
    def __init__(self, records, names):
        import ipywidgets as w
        self.rows = {}
        panels = []
        for record in records:
            if record['automatic'] is not None:
                continue
            key = record['transect_id']
            options = [('Scegli il settore…', None)] + [(names[k]+' ['+k+']', k) for k in record['allowed']]
            field = w.Dropdown(options=options, value=None, layout=w.Layout(width='100%'))
            self.rows[key] = field
            panels.append(w.VBox([w.HTML('<b>Transetto '+html.escape(key)+'</b> · assegnazione da confermare'), field]))
        if not panels:
            panels.append(w.HTML('Tutti i transetti hanno un’assegnazione automatica univoca. Puoi eseguire la cella successiva.'))
        self.view = w.VBox(panels, layout=w.Layout(width='100%', max_width='850px'))

    def read(self):
        missing = [key for key,field in self.rows.items() if field.value is None]
        if missing:
            raise ValueError('Scegli un settore per i transetti '+', '.join(missing)+'. Se non ci sono opzioni, verifica i poligoni.')
        return {key:field.value for key,field in self.rows.items()}


class SectorNameEditor:
    def __init__(self, names):
        import ipywidgets as w
        self.rows = {key:w.Text(value=name, layout=w.Layout(width='100%')) for key,name in names.items()}
        self.view = w.VBox([w.VBox([w.HTML('Nome pubblico · ID '+html.escape(key)),field])
            for key,field in self.rows.items()],layout=w.Layout(width='100%',max_width='850px'))

    def read(self):
        result = {key:field.value.strip() for key,field in self.rows.items()}
        if not all(result.values()):
            raise ValueError('Inserisci un nome per ciascun settore costiero.')
        return result
