# -*- coding: utf-8 -*-
"""
Crea un GeoJSON combinado SOLO para los UBIGEO del catálogo:
- UBIGEO que termina en '01' -> geometría de Provincias (pueden ser varios archivos)
- UBIGEO que termina != '01' -> geometría de Distritos

Uso (con defaults):
  python mix_ubigeo_geojson.py

Uso (pasando rutas):
  python mix_ubigeo_geojson.py \
    --distritos   ./Data/Distritos.geojson \
    --provincias  ./Data/Provincias1.geojson ./Data/Provincias2.geojson \
    --catalog-csv ./data/municipalidades_catalog.csv \
    --out         ./Mapas/ubigeo_mix.geojson
"""
import argparse
import json
from pathlib import Path
import pandas as pd

# ---------------- Args (con defaults en ./Data y ./data) ----------------
ap = argparse.ArgumentParser(
    description="Mezclar geometrías por UBIGEO (provincia para XXYY01, distrito para el resto) filtrando por catálogo."
)
ap.add_argument("--distritos",  default="./Data/Distritos.geojson",
                help="GeoJSON de distritos (ruta por defecto).")
ap.add_argument("--provincias", nargs="+",
                default=["./Data/Provincias1.geojson", "./Data/Provincias2.geojson"],
                help="Uno o más GeoJSON de provincias (rutas por defecto).")
ap.add_argument("--catalog-csv", default="./data/municipalidades_catalog.csv",
                help="CSV del catálogo con columna 'ubigeo' (ruta por defecto).")
ap.add_argument("--out", default="./Mapas/ubigeo_mix.geojson",
                help="Ruta de salida del GeoJSON combinado.")
args = ap.parse_args()

# Log de rutas efectivas
print("[Rutas] distritos   ->", Path(args.distritos).resolve())
print("[Rutas] provincias  ->", [str(Path(p).resolve()) for p in args.provincias])
print("[Rutas] catalog_csv ->", Path(args.catalog_csv).resolve())
print("[Rutas] out         ->", Path(args.out).resolve())

# ---------------- Utilitarios ----------------
def to_ubigeo6(x):
    if x is None:
        return None
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def load_catalog_ubigeos(path: Path) -> set:
    df = pd.read_csv(path, dtype=str)
    col = None
    for c in df.columns:
        if str(c).strip().lower() == "ubigeo":
            col = c
            break
    if col is None:
        raise KeyError(f"El catálogo no contiene columna 'ubigeo' (encabezados: {list(df.columns)})")
    ubis = df[col].dropna().map(to_ubigeo6)
    return set(u for u in ubis if u)

def pick_ubigeo_key(props: dict):
    for k in props.keys():
        if "ubigeo" in str(k).lower().strip():
            return k
    return None

def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"{path} no es un FeatureCollection válido")
    return data

def build_index_by_ubigeo(data: dict) -> dict:
    """Devuelve dict ubigeo6 -> (geometry, properties) para un FeatureCollection."""
    idx = {}
    for feat in data.get("features", []):
        if not isinstance(feat, dict) or feat.get("type") != "Feature":
            continue
        props = feat.get("properties") or {}
        key = pick_ubigeo_key(props)
        if not key:
            continue
        u6 = to_ubigeo6(props.get(key))
        if not u6:
            continue
        # La última ocurrencia con el mismo UBIGEO sobrescribe
        idx[u6] = (feat.get("geometry"), props)
    return idx

def merge_indexes(index_list) -> dict:
    """Une varios índices ubigeo->(geom, props). Prioriza los últimos (sobrescribe si hay duplicado)."""
    merged = {}
    dups = set()
    for idx in index_list:
        for u6, val in idx.items():
            if u6 in merged:
                dups.add(u6)
            merged[u6] = val
    if dups:
        print(f"[Aviso] UBIGEO duplicados entre archivos de provincias: {len(dups)} (se usó la última ocurrencia).")
    return merged

# ---------------- Pipeline ----------------
def main():
    p_dist = Path(args.distritos)
    p_out  = Path(args.out)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    assert p_dist.exists(), f"No existe: {p_dist}"
    for fp in args.provincias:
        assert Path(fp).exists(), f"No existe: {fp}"
    assert Path(args.catalog_csv).exists(), f"No existe: {args.catalog_csv}"

    # 1) UBIGEO válidos del catálogo
    ubigeos_catalogo = load_catalog_ubigeos(Path(args.catalog_csv))

    # 2) Índices de geometrías
    print("[Info] Cargando distritos…")
    gj_dist = load_geojson(p_dist)
    idx_dist = build_index_by_ubigeo(gj_dist)

    print(f"[Info] Cargando provincias ({len(args.provincias)} archivo/s)…")
    prov_indexes = []
    for fp in args.provincias:
        gj = load_geojson(Path(fp))
        prov_indexes.append(build_index_by_ubigeo(gj))
    idx_prov = merge_indexes(prov_indexes)

    # 3) Construir solo para los UBIGEO del catálogo
    features = []
    n_from_prov = 0
    n_from_dist = 0
    skipped = []

    for u6 in sorted(ubigeos_catalogo):
        if u6.endswith("01"):
            geom_props = idx_prov.get(u6)
            if not geom_props:
                skipped.append(("prov_missing", u6))
                continue
            geom, props = geom_props
            src = "provincias"
            n_from_prov += 1
        else:
            geom_props = idx_dist.get(u6)
            if not geom_props:
                skipped.append(("dist_missing", u6))
                continue
            geom, props = geom_props
            src = "distritos"
            n_from_dist += 1

        new_props = dict(props) if isinstance(props, dict) else {}
        new_props["UBIGEO"] = u6
        new_props["source"] = src

        features.append({
            "type": "Feature",
            "properties": new_props,
            "geometry": geom
        })

    out_fc = {"type": "FeatureCollection", "features": features}

    with p_out.open("w", encoding="utf-8") as f:
        json.dump(out_fc, f, ensure_ascii=False)

    print(f"\nGenerado: {p_out.resolve()}")
    print(f"  features totales: {len(features)}")
    print(f"  desde Provincias: {n_from_prov}")
    print(f"  desde Distritos : {n_from_dist}")
    if skipped:
        print("  Omitidos por falta de geometría en fuente (primeros 30):")
        for why, u in skipped[:30]:
            print(f"   - {u} ({why})")
        if len(skipped) > 30:
            print(f"   ... (+{len(skipped)-30} más)")

if __name__ == "__main__":
    main()
