"""Editable exposed structures for the one-off notebook, per coastal sector."""
import copy
import html


class StructureEditor:
    def __init__(self, units, defaults, *, by_unit=None):
        import ipywidgets as widgets
        if by_unit is not None and set(by_unit) != set(units):
            raise ValueError("Le proposte delle strutture devono corrispondere alle unità costiere.")
        self.units = units
        self.rows = {}
        self.widgets = widgets
        panels = []
        for key, label in units.items():
            self.rows[key] = []
            box = widgets.VBox()
            for threshold in (defaults if by_unit is None else by_unit[key]):
                self._add(key, box, threshold)
            button = widgets.Button(description='Aggiungi struttura', icon='plus')
            button.on_click(lambda _, key=key, box=box: self._add(key, box))
            panels.append(widgets.VBox([widgets.HTML(f'<b>{html.escape(label)}</b>'), box, button]))
        self.view = widgets.VBox(panels)

    def _add(self, key, box, threshold=None):
        import uuid
        w = self.widgets
        threshold = threshold or dict(id='struttura-'+uuid.uuid4().hex[:10], short_label='Nuova struttura', elevation_m=1., season='all_year')
        present = w.Checkbox(value=True, description='Presente', indent=False, layout=w.Layout(width='110px'))
        name = w.Text(value=threshold.get('short_label', threshold.get('description', '')), description='Struttura')
        elevation = w.FloatText(value=float(threshold['elevation_m']), description='Quota (m)')
        season = w.Dropdown(options=[('Tutto l’anno', 'all_year'), ('Stagione estiva', 'summer')], value=threshold['season'], description='Attività')
        row = dict(id=threshold['id'], present=present, name=name, elevation=elevation, season=season,
                   survey_statistics=copy.deepcopy(threshold.get('survey_statistics')))
        present.observe(lambda change: [setattr(field, 'disabled', not change['new']) for field in (name, elevation, season)], names='value')
        self.rows[key].append(row)
        fields = [present, name, elevation, season]
        stats = row['survey_statistics']
        if stats:
            fields.append(w.HTML(f"Quote dai punti DEM: media {stats['mean_elevation_m']:.2f} m; "
                f"minimo {stats['min_elevation_m']:.2f} m; massimo {stats['max_elevation_m']:.2f} m; "
                f"{stats['n_valid']} punti validi, {stats['n_excluded']} esclusi."))
        box.children = (*box.children, w.VBox(fields))

    def read(self):
        from forecast_service.sectors import validate_thresholds
        result = {}
        for key, rows in self.rows.items():
            thresholds = []
            for row in rows:
                if not row['present'].value:
                    continue
                label = row['name'].value.strip()
                if not label:
                    raise ValueError(f'Nome della struttura mancante in {self.units[key]}.')
                thresholds.append(dict(id=row['id'], short_label=label,
                    description='Possibile interessamento: '+label.lower(),
                    elevation_m=float(row['elevation'].value), season=row['season'].value))
                if row['survey_statistics'] is not None:
                    stats=copy.deepcopy(row['survey_statistics'])
                    stats['selected_elevation_source']='dem_point_mean' if thresholds[-1]['elevation_m']==stats['mean_elevation_m'] else 'manual_override'
                    thresholds[-1]['survey_statistics']=stats
            thresholds.sort(key=lambda value: value['elevation_m'])
            validate_thresholds(thresholds, allow_empty=True)
            result[key] = copy.deepcopy(thresholds)
        return result
