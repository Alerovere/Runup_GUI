"""Field selectors for XYZ transects and source-dependent slope controls."""
from forecast_service.gnss_setup import inspect_gnss


class GNSSFieldEditor:
    def __init__(self,path):
        import ipywidgets as w
        self.schema = inspect_gnss(path)
        fields = self.schema['fields']; numeric=self.schema['numeric_fields']
        def default(names,options):return next((key for key in names if key in options),None)
        self.id = w.Dropdown(options=[('Seleziona…',None)]+[(key,key) for key in fields],
            value=default(['transect_id','TR_ID','id','ID'],fields),layout=w.Layout(width='100%'))
        self.slope = w.Dropdown(options=[('Nessuno',None)]+[(key,key) for key in numeric],
            value=default(['tan_beta','slope','beta'],numeric),layout=w.Layout(width='100%'))
        self.r2 = w.Dropdown(options=[('Nessuno',None)]+[(key,key) for key in numeric],
            value=default(['r2','r_squared','R2'],numeric),layout=w.Layout(width='100%'))
        self.method = w.Dropdown(options=[('Ricalcola su tutti i punti XYZ','xyz'),('Usa il campo pendenza selezionato','attribute')],
            value='xyz',layout=w.Layout(width='100%'))
        self.crs = w.Text(value=self.schema['crs'],layout=w.Layout(width='100%'))
        self.correction = w.FloatText(value=0.,layout=w.Layout(width='100%'))
        self.reference = w.Text(value='Riferimento delle quote GNSS da verificare',layout=w.Layout(width='100%'))
        pairs=[('Identificativo del transetto',self.id),('Sorgente della pendenza',self.method),
            ('Campo pendenza β, in m/m (facoltativo nel ricalcolo)',self.slope),('Campo R² fornito, per confronto (facoltativo)',self.r2),
            ('CRS delle coordinate GNSS (letto dal file, se dichiarato)',self.crs),
            ('Correzione da sommare alle sole quote GNSS (m)',self.correction),('Riferimento verticale delle quote GNSS',self.reference)]
        self.view=w.VBox([w.HTML('Le quote sono la <b>terza coordinata Z dei vertici</b>, in metri. Non si ricavano dal DEM. Con il ricalcolo, i campi β e R² forniti restano valori di confronto.')]+
            [w.VBox([w.HTML(label),field]) for label,field in pairs],layout=w.Layout(width='100%',max_width='850px'))

    def read(self):
        import math
        if self.id.value is None:raise ValueError('Seleziona il campo identificativo dei transetti GNSS.')
        if self.method.value=='attribute' and self.slope.value is None:raise ValueError('Seleziona il campo della pendenza GNSS.')
        if not self.crs.value.strip() or not self.reference.value.strip() or not math.isfinite(self.correction.value):
            raise ValueError('Completa CRS, riferimento e correzione delle quote GNSS.')
        return dict(id_field=self.id.value,slope_field=self.slope.value,r2_field=self.r2.value,
            slope_source=self.method.value,geojson_crs=self.crs.value.strip(),z_correction_m=float(self.correction.value),
            vertical_reference=self.reference.value.strip())


class ProfileFitEditor:
    def __init__(self,*,gnss=False,z_min=0.,z_max=1.,orientation='auto'):
        import ipywidgets as w
        self.gnss=gnss
        self.orientation=w.Dropdown(options=[('Automatico (controllare il grafico)','auto'),
            ('Il primo punto è a mare','distance_increases_landward'),('L’ultimo punto è a mare','distance_increases_seaward')],
            value=orientation,layout=w.Layout(width='100%'))
        fields=[w.HTML('<b>Orientamento del transetto</b>'),self.orientation]
        self.z_min,self.z_max=None,None
        if gnss:
            fields.insert(0,w.HTML('Transetti GNSS già sulla battigia: si usano <b>tutti i vertici</b>, senza Zmin e Zmax.'))
        else:
            self.z_min=w.FloatText(value=float(z_min),description='Zmin (m)')
            self.z_max=w.FloatText(value=float(z_max),description='Zmax (m)')
            fields=[w.HTML('<b>Tratto di battigia da selezionare nel profilo DEM</b>'),self.z_min,self.z_max]+fields
        self.view=w.VBox(fields,layout=w.Layout(width='100%',max_width='850px'))

    def read(self):
        import math
        lo=None if self.gnss else float(self.z_min.value)
        hi=None if self.gnss else float(self.z_max.value)
        if not self.gnss and (not math.isfinite(lo) or not math.isfinite(hi) or lo>=hi):
            raise ValueError('Zmin e Zmax devono essere finite e crescenti.')
        return dict(z_min=lo,z_max=hi,orientation=self.orientation.value)
