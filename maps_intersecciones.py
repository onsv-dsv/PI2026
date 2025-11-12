# -*- coding: utf-8 -*-
"""
maps_intersecciones.py  (Intersecciones + siniestros + contorno)
- Normaliza encabezados a minúscula al leer cada Excel.
- Título del mapa = nombre del archivo .xlsx (sin extensión).
"""

import argparse
from pathlib import Path
import json
import pandas as pd
import folium
from html import escape
from branca.element import MacroElement, Template

COLOR_INTER = "#1d4ed8"  # azul intersecciones
COLOR_FATAL = "#d90429"  # rojo siniestros

# ---------------- util ----------------
def to_ubigeo6(x):
    if x is None:
        return None
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def scan_excels(excels_root: Path):
    return sorted(excels_root.rglob("*.xlsx"))

def title_from_filename(xlsx_path: Path) -> str:
    # Título = nombre del archivo sin extensión (exacto)
    return xlsx_path.stem

def add_title(m: folium.Map, text: str):
    html = f"""
    <div style="
        position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
        z-index: 9999; background: rgba(255,255,255,0.9);
        padding: 8px 14px; border-radius: 8px; font-weight: 600;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;">
        {escape(text)}
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))

def add_legend(m: folium.Map):
    html = f"""
    <div style="
        position: fixed; bottom: 20px; right: 20px; z-index: 9999;
        background: rgba(255,255,255,0.9); padding: 10px 12px; border-radius: 8px;
        font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15); line-height: 1.4;">
        <div style="font-weight: 600; margin-bottom: 6px;">Leyenda</div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_INTER}; border-radius:50%;"></span>
            <span>Azul: Intersección priorizada</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_FATAL}; border-radius:50%;"></span>
            <span>Rojo: Siniestro fatal</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))

# ---------- helpers geometrías (contornos) ----------
def features_distrito_por_ubigeo(distritos_gj: dict, target_ubi6: str):
    feats = []
    for feat in distritos_gj.get("features", []):
        props = feat.get("properties") or {}
        iddist = props.get("IDDIST")
        if to_ubigeo6(iddist) == target_ubi6:
            feats.append(feat)
    return feats

def features_provincia_por_ubigeo(prov_gj_list: list, target_ubi6: str):
    target4 = target_ubi6[:4] if target_ubi6 else None
    feats = []
    for prov_gj in prov_gj_list:
        for feat in prov_gj.get("features", []):
            props = feat.get("properties") or {}
            matched = False
            for k, v in props.items():
                if "ubigeo" in str(k).lower():
                    if to_ubigeo6(v) == target_ubi6:
                        feats.append(feat); matched = True
                        break
            if matched:
                continue
            idprov = props.get("IDPROV")
            if idprov is not None and target4 is not None:
                v = "".join(ch for ch in str(idprov) if ch.isdigit())
                v = v.zfill(4)[:4]
                if v == target4:
                    feats.append(feat)
    return feats

# ---------- punto en polígono ----------
def _point_in_ring(lon, lat, ring):
    inside = False
    if not ring: return False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if ((y1 > lat) != (y2 > lat)):
            x_inter = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
            if x_inter > lon:
                inside = not inside
    return inside

def point_in_polygon(lon, lat, polygon_coords):
    if not polygon_coords: return False
    exterior = polygon_coords[0]
    if not _point_in_ring(lon, lat, exterior):
        return False
    for hole in polygon_coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True

def point_in_features(lon, lat, feats):
    for feat in feats:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue
        if gtype == "Polygon":
            if point_in_polygon(lon, lat, coords):
                return True
        elif gtype == "MultiPolygon":
            for poly in coords:
                if point_in_polygon(lon, lat, poly):
                    return True
    return False

# ---------- siniestros ----------
def load_siniestros_csv(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp1252", "latin-1", "utf-16", "utf-8"]
    last_err = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError as e:
            last_err = e
            continue
    else:
        raise UnicodeDecodeError(f"No se pudo decodificar {path}. Último error: {last_err}")

    def pick_col(columns, *cands):
        cols = {str(c).strip().lower(): c for c in columns}
        for k in cands:
            lk = str(k).strip().lower()
            if lk in cols:
                return cols[lk]
        return None

    col_lat = pick_col(df.columns, "latitud","latitude","lat","y")
    col_lon = pick_col(df.columns, "longitud","longitude","lon","long","x")
    if not col_lat or not col_lon:
        raise KeyError(f"Siniestros: no encuentro columnas lat/lon. Encabezados={list(df.columns)}")

    df = df.copy()
    df["__lat__"] = pd.to_numeric(df[col_lat], errors="coerce")
    df["__lon__"] = pd.to_numeric(df[col_lon], errors="coerce")
    df = df.dropna(subset=["__lat__","__lon__"])
    return df

# ---------- popups ----------
_EXCLUDE_KEYS_INTER = {"ubigeo_gestor","ubigeo","departamento","provincia","distrito"}

def build_popup_inter(row: pd.Series) -> str:
    rows = []
    for col, val in row.items():
        if str(col).strip().lower() in _EXCLUDE_KEYS_INTER:
            continue
        sval = "" if pd.isna(val) else str(val)
        rows.append(
            f"<tr>"
            f"<th style='text-align:left; padding:2px 8px 2px 0; white-space:nowrap;'>{escape(str(col))}</th>"
            f"<td style='padding:2px 0;'>{escape(sval)}</td>"
            f"</tr>"
        )
    table_html = (
        "<div style='font-size:12px;'>"
        "<div style='font-weight:700; margin-bottom:6px;'>Intersección priorizada</div>"
        "<table style='border-collapse:collapse;'>"
        + "".join(rows) +
        "</table>"
        "</div>"
    )
    return table_html

def build_popup_siniestro(row: pd.Series) -> str:
    rows = []
    for col, val in row.items():
        if col in ("__lat__","__lon__"):
            continue
        sval = "" if pd.isna(val) else str(val)
        rows.append(
            f"<tr>"
            f"<th style='text-align:left; padding:2px 8px 2px 0; white-space:nowrap;'>{escape(str(col))}</th>"
            f"<td style='padding:2px 0;'>{escape(sval)}</td>"
            f"</tr>"
        )
    table_html = (
        "<div style='font-size:12px;'>"
        "<div style='font-weight:700; margin-bottom:6px;'>Siniestro fatal</div>"
        "<table style='border-collapse:collapse;'>"
        + "".join(rows) +
        "</table>"
        "</div>"
    )
    return table_html

# ---------- core ----------
def map_for_excel(xlsx_path: Path, out_dir: Path, distritos_gj: dict, provincias_gj_list: list, siniestros_df: pd.DataFrame) -> Path:
    # Leer y normalizar encabezados a minúscula
    df = pd.read_excel(xlsx_path, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Validaciones mínimas (tras normalizar)
    missing = [c for c in ("latitud","longitud") if c not in df.columns]
    if missing:
        raise KeyError(f"{xlsx_path.name}: faltan columnas {missing}")

    # Cast numérico y limpieza
    df = df.copy()
    df["latitud"]  = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud","longitud"])
    if df.empty:
        raise ValueError(f"{xlsx_path.name}: no hay filas con lat/lon válidas")

    lat0 = float(df["latitud"].mean())
    lon0 = float(df["longitud"].mean())
    m = folium.Map(location=[lat0, lon0], tiles="OpenStreetMap", zoom_start=14, control_scale=True)

    # CSS: desactivar eventos en buffers (para no bloquear clics)
    m.get_root().html.add_child(folium.Element("""
    <style>
      .leaflet-interactive.zs-buffer { pointer-events: none !important; }
    </style>
    """))

    # Título = nombre del archivo sin extensión
    add_title(m, title_from_filename(xlsx_path))
    add_legend(m)

    # FeatureGroups (orden sin panes)
    fg_contorno   = folium.FeatureGroup(name="contorno", show=True)
    fg_buffers    = folium.FeatureGroup(name="intersecciones: buffers (50m)", show=True)
    fg_puntos     = folium.FeatureGroup(name="intersecciones: puntos", show=True)
    fg_siniestros = folium.FeatureGroup(name="siniestros fatales", show=True)

    m.add_child(fg_contorno)
    m.add_child(fg_buffers)
    m.add_child(fg_puntos)
    m.add_child(fg_siniestros)

    # Contorno por UBIGEO (usando columna ya en minúscula si existe)
    target_ubi = to_ubigeo6(df["ubigeo_gestor"].dropna().iloc[0]) if "ubigeo_gestor" in df.columns and df["ubigeo_gestor"].notna().any() else None
    feats = []
    if target_ubi:
        if target_ubi.endswith("01"):
            feats = features_provincia_por_ubigeo(provincias_gj_list, target_ubi)
        else:
            feats = features_distrito_por_ubigeo(distritos_gj, target_ubi)
        if feats:
            gj_filtrado = {"type": "FeatureCollection", "features": feats}
            folium.GeoJson(
                data=gj_filtrado,
                name="Contorno territorial",
                style_function=lambda feat: {
                    "color": "#222222",
                    "weight": 2.5,
                    "opacity": 1.0,
                    "fill": True,
                    "fillColor": "#FFA500",
                    "fillOpacity": 0.6
                }
            ).add_to(fg_contorno)

    # Intersecciones
    bounds = []
    for _, row in df.iterrows():
        lat = float(row["latitud"]); lon = float(row["longitud"])

        # Buffer 50 m (no interactivo)
        folium.Circle(
            location=(lat, lon),
            radius=50,
            color=COLOR_INTER,
            weight=2,
            fill=True,
            fill_color=COLOR_INTER,
            fill_opacity=0.5,
            interactive=False,
            class_name="zs-buffer"
        ).add_to(fg_buffers)

        # Punto exacto (arriba)
        folium.CircleMarker(
            location=(lat, lon),
            radius=5,
            color=COLOR_INTER,
            weight=2,
            fill=True,
            fill_color=COLOR_INTER,
            fill_opacity=1.0,
            popup=folium.Popup(build_popup_inter(row), max_width=460),
        ).add_to(fg_puntos)

        bounds.append((lat, lon))

    # Siniestros dentro del contorno
    if feats and not siniestros_df.empty:
        for _, r in siniestros_df.iterrows():
            slat = float(r["__lat__"]); slon = float(r["__lon__"])
            if point_in_features(slon, slat, feats):
                folium.CircleMarker(
                    location=(slat, slon),
                    radius=5,
                    color=COLOR_FATAL,
                    weight=2,
                    fill=True,
                    fill_color=COLOR_FATAL,
                    fill_opacity=1.0,
                    popup=folium.Popup(build_popup_siniestro(r), max_width=480),
                ).add_to(fg_siniestros)

    # Orden top: puntos intersección y siniestros
    tpl = Template(f"""
    {{% macro script(this, kwargs) %}} 
        {fg_puntos.get_name()}.bringToFront();
        {fg_siniestros.get_name()}.bringToFront();
    {{% endmacro %}}
    """)
    me = MacroElement(); me._template = tpl
    m.get_root().add_child(me)

    if len(bounds) >= 2:
        m.fit_bounds(bounds)

    folium.LayerControl(collapsed=True).add_to(m)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_name = xlsx_path.with_suffix(".html").name
    out_path = out_dir / html_name
    m.save(str(out_path))
    return out_path

def write_index(index_path: Path, items):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lis = "\n".join(f'<li><a href="{p.name}" target="_blank">{p.name}</a></li>' for p in items)
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Mapas de Intersecciones</title></head>
<body>
<h1>Mapas generados</h1>
<ul>{lis}</ul>
</body></html>"""
    index_path.write_text(html, encoding="utf-8")

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="Generar mapas de Intersecciones (HTML) con contorno y siniestros.")
    ap.add_argument("--excels-dir",        default="./Intersecciones/excels")
    ap.add_argument("--out-dir",           default="./Intersecciones/maps")
    ap.add_argument("--distritos-geojson", default="./Data/Distritos.geojson",
                    help="GeoJSON de distritos (usa clave IDDIST).")
    ap.add_argument("--provincias-geojson", nargs="+",
                    default=["./Data/Provincias1.geojson", "./Data/Provincias2.geojson"],
                    help="Uno o más GeoJSON de provincias (propiedad con 'ubigeo' o IDPROV).")
    ap.add_argument("--siniestros-csv",    default="./Data/Siniestros.csv",
                    help="CSV de siniestros con columnas lat/lon (latitud/longitud, etc.).")
    args = ap.parse_args()

    excels_root = Path(args.excels_dir)
    out_root    = Path(args.out_dir)

    # GeoJSON distritos
    distritos_path = Path(args.distritos_geojson)
    assert distritos_path.exists(), f"No existe: {distritos_path}"
    with distritos_path.open("r", encoding="utf-8") as f:
        distritos_gj = json.load(f)

    # GeoJSON provincias
    provincias_gj_list = []
    for p in args.provincias_geojson:
        pp = Path(p)
        assert pp.exists(), f"No existe: {pp}"
        with pp.open("r", encoding="utf-8") as f:
            provincias_gj_list.append(json.load(f))

    # Siniestros
    siniestros_path = Path(args.siniestros_csv)
    assert siniestros_path.exists(), f"No existe: {siniestros_path}"
    siniestros_df = load_siniestros_csv(siniestros_path)

    excel_files = scan_excels(excels_root)
    if not excel_files:
        print(f"No se encontraron .xlsx en {excels_root.resolve()}")
        return

    generated = []
    for x in excel_files:
        try:
            out_html = map_for_excel(x, out_root, distritos_gj, provincias_gj_list, siniestros_df)
            print(f"[OK] {x.name} -> {out_html}")
            generated.append(out_html)
        except Exception as e:
            print(f"[ERROR] {x}: {e}")

    if generated:
        write_index(out_root / "_index_maps.html", generated)
        print(f"\nIndex de mapas: { (out_root / '_index_maps.html').resolve() }")

if __name__ == "__main__":
    main()
