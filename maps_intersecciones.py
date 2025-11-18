# -*- coding: utf-8 -*-
"""
maps_intersecciones.py  (Intersecciones + siniestros + contorno + buscador + coords + medir + GMaps + toggle)
- Normaliza encabezados a minúscula al leer cada Excel.
- Título del mapa = nombre del archivo .xlsx (sin extensión).
- Buffer de 50 m para intersecciones (no interactivo).
- Buscador por nombre y código (tolerante a encabezados variados).
- Pin por coordenadas (X=longitud, Y=latitud).
- Herramienta de medición (dos puntos arrastrables; etiqueta en m/km).
- Botón para abrir la vista actual en Google Maps.
- Panel con botón Mostrar/Ocultar (estado persistente).
"""

import argparse
from pathlib import Path
import json
import pandas as pd
import folium
from html import escape
from branca.element import MacroElement, Template

COLOR_INTER    = "#1d4ed8"  # azul intersecciones
COLOR_FATAL    = "#d90429"  # rojo siniestros
COLOR_HILITE   = "#f59e0b"  # amarillo resaltado
COLOR_CONTORNO = "#9ca3af"  # plomo contorno

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
    <div id="legend-box" style="
        position: fixed; bottom: 20px; right: 20px; z-index: 9999;
        background: rgba(255,255,255,0.9); padding: 10px 12px; border-radius: 8px;
        font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15); line-height: 1.4; min-width: 240px;">
        <div style="font-weight: 600; margin-bottom: 6px;">Leyenda</div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_INTER}; border-radius:50%;"></span>
            <span>Azul: Intersección priorizada</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_FATAL}; border-radius:50%;"></span>
            <span>Rojo: Siniestro fatal</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_HILITE}; border-radius:50%;"></span>
            <span>Amarillo: Coincidencia de búsqueda</span>
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

def _safe_str(v):
    try:
        if pd.api.types.is_scalar(v):
            return "" if pd.isna(v) else str(v)
        return str(v)
    except Exception:
        return str(v)

def build_popup_inter(row: pd.Series) -> str:
    rows = []
    for col, val in row.items():
        if str(col).strip().lower() in _EXCLUDE_KEYS_INTER:
            continue
        sval = _safe_str(val)
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
        sval = _safe_str(val)
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
    df = pd.read_excel(xlsx_path, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = [c for c in ("latitud","longitud") if c not in df.columns]
    if missing:
        raise KeyError(f"{xlsx_path.name}: faltan columnas {missing}")

    df = df.copy()
    df["latitud"]  = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud","longitud"])
    if df.empty:
        raise ValueError(f"{xlsx_path.name}: no hay filas con lat/lon válidas")

    # columnas candidatas para nombre/código (tolerantes)
    NAME_CANDS = ["nombre_interseccion","interseccion","descripcion","descripcion_interseccion","nombre"]
    CODE_CANDS = ["codigo_interseccion","codigo","id_interseccion","id"]

    def pick_col(columns, cands):
        cols = {str(c).strip().lower(): c for c in columns}
        for k in cands:
            lk = str(k).strip().lower()
            if lk in cols:
                return cols[lk]
        return None

    col_name = pick_col(df.columns, NAME_CANDS)
    col_code = pick_col(df.columns, CODE_CANDS)

    lat0 = float(df["latitud"].mean())
    lon0 = float(df["longitud"].mean())
    m = folium.Map(location=[lat0, lon0], tiles="OpenStreetMap", zoom_start=14, control_scale=True)

    # CSS (NO f-string)
    m.get_root().html.add_child(folium.Element("""
    <style>
      .leaflet-interactive.zs-buffer { pointer-events: none !important; }

      .searchbar-wrap {
        position: fixed; right: 20px; bottom: 140px;
        z-index: 10000; background: rgba(255,255,255,0.95);
        border: 1px solid #e5e7eb;
        padding: 10px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        font-family: system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;
        display: flex; flex-direction: column; gap: 8px; min-width: 300px; max-width: 92vw;
      }

      .searchbar-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
      .searchbar-title { font-weight: 700; font-size: 14px; color: #111827; }
      .toggle-btn { border: 0; border-radius: 8px; padding: 4px 10px; font-weight: 700; cursor: pointer; background: #111827; color: #fff; }
      .tools-body { display: flex; flex-direction: column; gap: 8px; }

      .row-flex { display:flex; gap:8px; align-items:center; }
      .col-flex { display:flex; flex-direction:column; gap:8px; }
      .row-flex input, .col-flex input { border:1px solid #e5e7eb; border-radius:8px; padding:6px 8px; font-size:13px; flex:1; }
      .row-flex button, .col-flex button { border:0; border-radius:8px; padding:6px 10px; font-weight:600; cursor:pointer; }
      .btn-dark  { background:#111827; color:#fff; }
      .btn-gray  { background:#6b7280; color:#fff; }
      .btn-green { background:#065f46; color:#fff; }
      .btn-red   { background:#991b1b; color:#fff; }
      .pill { font-size:12px; padding:4px 8px; border-radius:999px; }
      .dist-on-line { background: rgba(17,24,39,0.85); color: #fff; padding: 2px 6px; border-radius: 6px; font-size: 12px; border: 1px solid rgba(255,255,255,0.2); }

      .searchbar-wrap.collapsed { padding: 8px 10px; }
      .searchbar-wrap.collapsed .tools-body { display: none; }

      @media (max-width: 480px) {
        .searchbar-wrap { right: 12px; bottom: 12px; min-width: 240px; }
      }
    </style>
    """))

    add_title(m, title_from_filename(xlsx_path))
    add_legend(m)

    fg_contorno   = folium.FeatureGroup(name="contorno", show=True)
    fg_buffers    = folium.FeatureGroup(name="intersecciones: buffers (50m)", show=True)
    fg_puntos     = folium.FeatureGroup(name="intersecciones: puntos", show=True)
    fg_siniestros = folium.FeatureGroup(name="siniestros fatales", show=True)

    m.add_child(fg_contorno)
    m.add_child(fg_buffers)
    m.add_child(fg_puntos)
    m.add_child(fg_siniestros)

    # Contorno
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
                    "fillColor": COLOR_CONTORNO,
                    "fillOpacity": 0.3
                }
            ).add_to(fg_contorno)

    # Intersecciones
    bounds = []
    for _, row in df.iterrows():
        lat = float(row["latitud"]); lon = float(row["longitud"])

        # Valores para tooltip (búsqueda)
        name_raw = _safe_str(row.get(col_name, "")) if col_name else ""
        code_raw = _safe_str(row.get(col_code, "")) if col_code else ""

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

        marker = folium.CircleMarker(
            location=(lat, lon),
            radius=5,
            color=COLOR_INTER,
            weight=2,
            fill=True,
            fill_color=COLOR_INTER,
            fill_opacity=1.0,
            popup=folium.Popup(build_popup_inter(row), max_width=460),
        )
        tooltip_text = (name_raw or "").lower() + " | " + (code_raw or "").lower()
        folium.Tooltip(tooltip_text, sticky=False, opacity=0).add_to(marker)
        marker.add_to(fg_puntos)

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

    # Llevar capas al frente (Template sin f-string; reemplazo)
    tpl_front = Template("""
    {% macro script(this, kwargs) %}
        {{fg_puntos}}.bringToFront();
        {{fg_siniestros}}.bringToFront();
    {% endmacro %}
    """.replace("{{fg_puntos}}", fg_puntos.get_name()).replace("{{fg_siniestros}}", fg_siniestros.get_name()))
    me_front = MacroElement(); me_front._template = tpl_front
    m.get_root().add_child(me_front)

    if len(bounds) >= 2:
        m.fit_bounds(bounds)

    folium.LayerControl(collapsed=True).add_to(m)

    # ---------- UI derecha: buscador + coords + medir + GMaps + Toggle ----------
    tpl = """
    {% macro html(this, kwargs) %}
      <div class="searchbar-wrap" id="zs_tools">
        <div class="searchbar-header">
          <div class="searchbar-title">Herramientas</div>
          <button id="btn_toggle_box" class="toggle-btn" title="Mostrar/Ocultar">⯆ Ocultar</button>
        </div>

        <div class="tools-body">
          <div class="col-flex">
            <input id="q_name" type="text" placeholder="Buscar por nombre">
            <input id="q_code" type="text" placeholder="Buscar por código">
          </div>
          <div class="row-flex">
            <button id="btn_search" class="btn-dark">Buscar</button>
            <button id="btn_clear" class="btn-gray">Limpiar</button>
          </div>

          <hr style="border:none;border-top:1px solid #e5e7eb; margin:4px 0;">

          <div class="col-flex" title="Coordenadas en grados decimales">
            <input id="q_x" type="text" placeholder="Longitud Ejem: -77.15435">
            <div class="row-flex">
              <input id="q_y" type="text" placeholder="Latitud Ejem: -15.54648">
              <button id="btn_xy_go" class="btn-green" title="Centrar en coordenadas">🔍</button>
              <button id="btn_xy_clear" class="btn-red"   title="Quitar pin de coordenadas">✕</button>
            </div>
          </div>

          <div class="row-flex">
            <button id="btn_measure_toggle" class="btn-dark pill" title="Medir distancia">Medir distancia</button>
            <span id="measure_state" style="font-size:12px; color:#991b1b">Desactivado</span>
          </div>

          <div class="row-flex">
            <button id="btn_open_gmaps" class="btn-dark" title="Abrir esta vista en Google Maps">Abrir en Google Maps</button>
          </div>
        </div>
      </div>
    {% endmacro %}

    {% macro script(this, kwargs) %}
      (function() {
        var puntosLayer = __FG_PUNTOS__;
        var defaultColor = '__COLOR_INTER__';
        var hiliteColor  = '__COLOR_HILITE__';

        // ---------- Toggle colapsar/expandir ----------
        var box = document.getElementById('zs_tools');
        var btnToggle = document.getElementById('btn_toggle_box');
        var saved = null;
        try { saved = localStorage.getItem('zs_tools_collapsed'); } catch(e) {}
        if (saved === '1') {
          box.classList.add('collapsed');
          btnToggle.textContent = '⯈ Mostrar';
        }
        function toggleBox() {
          var collapsed = box.classList.toggle('collapsed');
          btnToggle.textContent = collapsed ? '⯈ Mostrar' : '⯆ Ocultar';
          try { localStorage.setItem('zs_tools_collapsed', collapsed ? '1' : '0'); } catch(e) {}
        }
        btnToggle.addEventListener('click', toggleBox);

        // ---------- Esperar a que el mapa esté disponible ----------
        var ly_map = null;
        function ensureMap(cb) {
          var tries = 0;
          (function wait() {
            ly_map = (puntosLayer && puntosLayer._map) ? puntosLayer._map : null;
            if (ly_map) { cb(); return; }
            if (tries++ < 80) { setTimeout(wait, 50); }
          })();
        }

        ensureMap(function initTools() {
          // ---------- Utilidades ----------
          function eachMarker(fn) {
            if (!puntosLayer || !puntosLayer._layers) return;
            Object.values(puntosLayer._layers).forEach(function(ly) {
              if (ly && typeof ly.setStyle === 'function') fn(ly);
            });
          }

          function getTooltipText(ly) {
            try {
              var t = ly.getTooltip();
              return t ? String(t.getContent() || '').toLowerCase() : '';
            } catch(e) { return ''; }
          }

          function clearHighlights() {
            eachMarker(function(ly) {
              ly.setStyle({ color: defaultColor, fillColor: defaultColor });
            });
          }

          // ---------- Búsqueda ----------
          function searchAndHighlight() {
            var qn_raw = (document.getElementById('q_name').value || '');
            var qc_raw = (document.getElementById('q_code').value || '');
            var qn = qn_raw.toLowerCase();
            var qc = qc_raw.toLowerCase();

            var useName = qn_raw.trim().length > 0;
            var useCode = qc_raw.trim().length > 0;

            clearHighlights();
            if (!useName && !useCode) return;

            var matchedLatLngs = [];
            eachMarker(function(ly) {
              var txt = getTooltipText(ly); // "nombre | codigo"
              var parts = txt.split('|', 2);
              var nameTxt = (parts[0] || '').trim();
              var codeTxt = (parts[1] || '').trim();

              var matchName = useName ? (nameTxt.indexOf(qn) !== -1) : false;
              var matchCode = useCode ? (codeTxt.indexOf(qc) !== -1) : false;

              if (matchName || matchCode) {
                ly.setStyle({ color: hiliteColor, fillColor: hiliteColor });
                if (ly.getLatLng) matchedLatLngs.push(ly.getLatLng());
              }
            });

            if (matchedLatLngs.length > 0) {
              var group = L.featureGroup(matchedLatLngs.map(function(ll) { return L.marker(ll); }));
              try { ly_map.fitBounds(group.getBounds().pad(0.2)); } catch(e) {}
            }
          }

          document.getElementById('btn_search').addEventListener('click', searchAndHighlight);
          document.getElementById('btn_clear').addEventListener('click', function() {
            document.getElementById('q_name').value = '';
            document.getElementById('q_code').value = '';
            clearHighlights();
          });
          ['q_name','q_code'].forEach(function(id) {
            var el = document.getElementById(id);
            el.addEventListener('keydown', function(ev) { if (ev.key === 'Enter') searchAndHighlight(); });
          });

          // ---------- Pin por coordenadas ----------
          var coordLayer = L.layerGroup().addTo(ly_map);
          function goToXY() {
            var x = parseFloat((document.getElementById('q_x').value || '').replace(',', '.'));
            var y = parseFloat((document.getElementById('q_y').value || '').replace(',', '.'));
            if (!isFinite(x) || !isFinite(y)) return;
            coordLayer.clearLayers();
            var mk = L.marker([y, x], { draggable:false, title: 'Punto (Y,X): '+y+', '+x });
            mk.addTo(coordLayer);
            ly_map.setView([y, x], Math.max(ly_map.getZoom(), 17));
          }
          function clearXY() { coordLayer.clearLayers(); }
          document.getElementById('btn_xy_go').addEventListener('click', goToXY);
          document.getElementById('btn_xy_clear').addEventListener('click', clearXY);

          // ---------- Medición ----------
          var measuring = false;
          var mA = null, mB = null, mLine = null;

          function haversine(lat1, lon1, lat2, lon2) {
            var R = 6371000;
            var dLat = (lat2-lat1) * Math.PI/180;
            var dLon = (lon2-lon1) * Math.PI/180;
            var a = Math.sin(dLat/2)*Math.sin(dLat/2) +
                    Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180) *
                    Math.sin(dLon/2)*Math.sin(dLon/2);
            var c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            return R * c;
          }

          function updateMeasure() {
            if (!(mA && mB)) return;
            var a = mA.getLatLng(), b = mB.getLatLng();
            var d = haversine(a.lat, a.lng, b.lat, b.lng);
            var txt = (d >= 1000) ? (d/1000).toFixed(3)+' km' : Math.round(d)+' m';

            if (!mLine) {
              mLine = L.polyline([a, b], { color: '#111827', weight: 3, dashArray: '6,4' })
                .bindTooltip(txt, { permanent:true, direction:'center', className:'dist-on-line' })
                .addTo(ly_map);
            } else {
              mLine.setLatLngs([a, b]);
              mLine.setTooltipContent(txt);
            }
          }

          function clearMeasure() {
            if (mA) ly_map.removeLayer(mA); mA = null;
            if (mB) ly_map.removeLayer(mB); mB = null;
            if (mLine) ly_map.removeLayer(mLine); mLine = null;
          }

          function toggleMeasure() {
            measuring = !measuring;
            var stateSpan = document.getElementById('measure_state');
            stateSpan.textContent = measuring ? 'Activo' : 'Desactivado';
            stateSpan.style.color = measuring ? '#065f46' : '#991b1b';
            if (!measuring) {
              clearMeasure();
              ly_map.getContainer().style.cursor = '';
              return;
            }
            ly_map.getContainer().style.cursor = 'crosshair';
          }

          document.getElementById('btn_measure_toggle').addEventListener('click', toggleMeasure);

          ly_map.on('click', function(ev) {
            if (!measuring) return;
            if (!mA) {
              mA = L.marker(ev.latlng, { draggable:true, title:'Punto A' }).addTo(ly_map);
              mA.on('drag', updateMeasure);
            } else if (!mB) {
              mB = L.marker(ev.latlng, { draggable:true, title:'Punto B' }).addTo(ly_map);
              mB.on('drag', updateMeasure);
            } else {
              mB.setLatLng(ev.latlng);
            }
            updateMeasure();
          });

          // ---------- Abrir vista actual en Google Maps ----------
          function openInGoogleMaps() {
            var c = ly_map.getCenter();
            var z = ly_map.getZoom();
            var url = 'https://www.google.com/maps/@' + c.lat + ',' + c.lng + ',' + z + 'z';
            window.open(url, '_blank');
          }
          document.getElementById('btn_open_gmaps').addEventListener('click', openInGoogleMaps);
        });
      })();
    {% endmacro %}
    """
    tpl = tpl.replace("__FG_PUNTOS__", fg_puntos.get_name()) \
             .replace("__COLOR_INTER__", COLOR_INTER) \
             .replace("__COLOR_HILITE__", COLOR_HILITE)

    search_ui = Template(tpl)
    me_search = MacroElement(); me_search._template = search_ui
    m.get_root().add_child(me_search)

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
    ap = argparse.ArgumentParser(description="Generar mapas de Intersecciones (HTML) con contorno, siniestros, buscador, medición y toggle.")
    ap.add_argument("--excels-dir",        default="./Intersecciones/excels")
    ap.add_argument("--out-dir",           default="./Intersecciones/maps")
    ap.add_argument("--distritos-geojson", default="./Data/Distritos.geojson", help="GeoJSON de distritos (usa clave IDDIST).")
    ap.add_argument("--provincias-geojson", nargs="+", default=["./Data/Provincias1.geojson", "./Data/Provincias2.geojson"], help="Uno o más GeoJSON de provincias (propiedad con 'ubigeo' o IDPROV).")
    ap.add_argument("--siniestros-csv",    default="./Data/Siniestros.csv", help="CSV de siniestros con columnas lat/lon (latitud/longitud, etc.).")
    args = ap.parse_args()

    excels_root = Path(args.excels_dir)
    out_root    = Path(args.out_dir)

    distritos_path = Path(args.distritos_geojson)
    assert distritos_path.exists(), f"No existe: {distritos_path}"
    with distritos_path.open("r", encoding="utf-8") as f:
        distritos_gj = json.load(f)

    provincias_gj_list = []
    for p in args.provincias_geojson:
        pp = Path(p)
        assert pp.exists(), f"No existe: {pp}"
        with pp.open("r", encoding="utf-8") as f:
            provincias_gj_list.append(json.load(f))

    siniestros_path = Path(args.siniestros_csv)
    assert siniestros_path.exists(), f"No existe: {siniestros_path}"
    siniestros_df = load_siniestros_csv(siniestros_path)

    excel_files = scan_excels(excels_root)
    if not excel_files:
        print(f"No se encontraron .xlsx en {excels_root.resolve()}")
        return

    # --- SOLO EL PRIMERO (quitar para procesar todos) ---
    #excel_files = excel_files[:1]
    #print(f"Procesando solo el primer archivo: {excel_files[0].name}")
    
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
