"""Regression reference: supplied Stockdon_runup_soluzione.ipynb, cell 25."""
import numpy as np
COL_DIST="distance"
COL_Z="SAMPLE_1"
COL_X="X"
COL_Y="Y"
Z_MIN=0.0
Z_MAX=1.0

def prepara_profilo(p):
    # Ordina i punti di un transetto dal mare verso terra e calcola la distanza dal primo punto a mare
    p = p.dropna(subset=[COL_Z]).sort_values(COL_DIST)
    if p[COL_Z].iloc[:10].mean() > p[COL_Z].iloc[-10:].mean():   # se il primo tratto è più alto, il mare è in fondo
        p = p.iloc[::-1]
    p = p.reset_index(drop=True)
    p['x_mare'] = np.hypot(p[COL_X] - p[COL_X].iloc[0], p[COL_Y] - p[COL_Y].iloc[0])
    return p

def pendenza_battigia(p):
    # Pendenza (m/m) della retta che interpola i punti tra Z_MIN e Z_MAX
    sopra = np.where(p[COL_Z] > Z_MAX)[0]
    fine = sopra[0] if len(sopra) > 0 else len(p)
    sel = (p[COL_Z] >= Z_MIN) & (p.index < fine)
    coeff = np.polyfit(p.loc[sel, 'x_mare'], p.loc[sel, COL_Z], 1)
    return coeff[0], sel

