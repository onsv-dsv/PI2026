# -*- coding: utf-8 -*-
"""
municipalidades_build.py  (versión con excel_relpath)

Lee el CSV fuente de municipalidades y genera:
- data/municipalidades_catalog.csv      (para procesos)
- data/municipalidades.json             (para la web)
- NUEVO: columna 'excel_relpath' con la ruta esperada del Excel por municipalidad.

Uso:
  python municipalidades_build.py --in-file ./Data/MUNICIPALIDADES.csv
"""
import argparse
from pathlib import Path
import pandas as pd

def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    return (s.replace("á", "a").replace("é", "e").replace("í", "i")
             .replace("ó", "o").replace("ú", "u").replace("ñ", "n"))

def to_ubigeo6(x):
    if pd.isna(x): return None
    s = str(x).strip()
    if s.endswith(".0"): s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    if not s: return None
    return s.zfill(6)[:6]

def clean_part_for_slug(s: str) -> str:
    t = str(s or "").strip()
    t = (t.replace("á","a").replace("é","e").replace("í","i")
           .replace("ó","o").replace("ú","u").replace("ñ","n"))
    t = " ".join(t.split())
    return t.upper().replace(" ", "_")

def autodetect_sep(first_line: str):
    if first_line.count(";") >= max(first_line.count(","), first_line.count("\t")): return ";"
    if first_line.count(",") >= first_line.count("\t"): return ","
    if "\t" in first_line: return "\t"
    return ";"

def read_csv_smart(path: Path, sep: str = None, encoding: str = None) -> pd.DataFrame:
    text = path.read_text(encoding=encoding or "utf-8", errors="ignore")
    use_sep = sep or autodetect_sep(text.splitlines()[0] if text.splitlines() else ";")
    try:
        return pd.read_csv(path, dtype=str, encoding=encoding or "utf-8", sep=use_sep)
    except Exception:
        return pd.read_csv(path, dtype=str, encoding=encoding or "latin-1", sep=use_sep)

def pick(df: pd.DataFrame, *cands, required=False):
    colmap = {str(c).strip(): c for c in df.columns}
    for k in cands:
        for v in (k, k.upper(), k.lower(), k.title()):
            if v in colmap: return colmap[v]
    colmap_norm = {norm(c): c for c in df.columns}
    for k in cands:
        if norm(k) in colmap_norm: return colmap_norm[norm(k)]
    if required:
        raise KeyError(f"No encontré columnas {cands}. Encabezados: {list(df.columns)}")
    return None

def main():
    ap = argparse.ArgumentParser(description="Construye catálogo de municipalidades (CSV + JSON).")
    ap.add_argument("--in-file", default="./Data/MUNICIPALIDADES.csv")
    ap.add_argument("--out-dir", default="./data")
    ap.add_argument("--sep", default=None)
    ap.add_argument("--encoding", default=None)
    args = ap.parse_args()

    in_path = Path(args.in_file)
    out_dir = Path(args.out_dir)
    assert in_path.exists(), f"No existe {in_path}"
    out_dir.mkdir(parents=True, exist_ok=True)

    df_raw = read_csv_smart(in_path, sep=args.sep, encoding=args.encoding)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    c_ubigeo = pick(df_raw, "UBIGEO", "codigo_ubigeo", "ubigeo_muni", required=True)
    c_dep    = pick(df_raw, "DEPARTAMENTO", "depa", "dep", "region", required=True)
    c_prov   = pick(df_raw, "PROVINCIA", "prov", required=True)
    c_dist   = pick(df_raw, "DISTRITO", "dist", required=True)
    c_tipo   = pick(df_raw, "TIPO", "tipo", "categoria")
    c_name   = pick(df_raw, "NOMBRE", "name", "razon_social", "municipalidad")

    dep_disp  = df_raw[c_dep].astype(str).str.strip()
    prov_disp = df_raw[c_prov].astype(str).str.strip()
    dist_disp = df_raw[c_dist].astype(str).str.strip()

    slug = dep_disp.map(clean_part_for_slug) + "-" + \
           prov_disp.map(clean_part_for_slug) + "-" + \
           dist_disp.map(clean_part_for_slug)

    df_out = pd.DataFrame({
        "ubigeo": df_raw[c_ubigeo].map(to_ubigeo6),
        "departamento": dep_disp,
        "provincia": prov_disp,
        "distrito": dist_disp,
        "slug": slug
    })
    if c_tipo: df_out["tipo"] = df_raw[c_tipo].astype(str).str.strip()
    if c_name: df_out["name"] = df_raw[c_name].astype(str).str.strip()

    # Nueva columna con la RUTA relativa de Excel por muni (no jerárquica)
    df_out["excel_relpath"] = "ZonasEscolares/excels/" + df_out["slug"] + ".xlsx"

    df_out = df_out[df_out["ubigeo"].notna()].drop_duplicates(subset=["ubigeo"])

    csv_out = out_dir / "municipalidades_catalog.csv"
    json_out = out_dir / "municipalidades.json"
    df_out.to_csv(csv_out, index=False, encoding="utf-8")
    df_out.to_json(json_out, orient="records", force_ascii=False, indent=2)

    print("Catálogo generado:")
    print(" CSV :", csv_out)
    print(" JSON:", json_out)
    print("Columnas:", list(df_out.columns))

if __name__ == "__main__":
    main()