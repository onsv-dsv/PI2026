# -*- coding: utf-8 -*-
"""
process_colegios_min.py

Lee el Excel de colegios priorizados, calcula ubigeo_gestor (provincial => XXYY01)
y exporta un CLEAN (CSV y XLSX) en ZonasEscolares/processed/.

Uso:
  python process_colegios_min.py \
    --input-excel ./ZonasEscolares/Colegios_Priorizados_PI2026.xlsx
"""
import argparse
from pathlib import Path
from typing import Optional, Iterable
import pandas as pd

# ----------------------------
# Utilitarios
# ----------------------------
_TRUE = {"true", "1", "si", "sí", "x", "t", "y"}
_FALSE = {"false", "0", "no", "n", "f", "flase"}

def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    return (s.replace("á","a").replace("é","e").replace("í","i")
             .replace("ó","o").replace("ú","u").replace("ñ","n"))

def to_ubigeo6(x) -> Optional[str]:
    if pd.isna(x): return None
    s = str(x).strip()
    if s.endswith(".0"): s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def to_bool(x) -> bool:
    if isinstance(x, bool): return x
    if pd.isna(x): return False
    s = norm(str(x))
    if s in _FALSE: return False
    if s in _TRUE:  return True
    return bool(s)

def pick_column(df: pd.DataFrame, *candidates: Iterable[str], required=False) -> Optional[str]:
    colmap = {norm(c): c for c in df.columns}
    for k in candidates:
        if norm(k) in colmap:
            return colmap[norm(k)]
    if required:
        raise KeyError(f"No encontré columnas {candidates}. Encabezados: {list(df.columns)}")
    return None

# ----------------------------
# Transformación principal
# ----------------------------
def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve un CLEAN con ubigeo_gestor (al inicio) y columnas útiles:
    ubigeo_gestor, ubigeo_original, codigo_ce, descripcion, latitud, longitud,
    alumnos, docentes, siniestros, mantenimiento, competencia_via
    """
    col_codigo = pick_column(df, "codigo_ce","codigo colegio","codigo_modular","codigo", required=True)
    col_ubigeo = pick_column(df, "ubigeo","ubigeo_ie", required=True)
    col_desc   = pick_column(df, "descripcion","nombre","nombre_ie", required=True)
    col_lat    = pick_column(df, "latitud","lat")
    col_lon    = pick_column(df, "longitud","lon","long")
    col_alum   = pick_column(df, "alumnos","estudiantes","matriculados")
    col_doc    = pick_column(df, "docentes")
    col_sin    = pick_column(df, "siniestros","siniestros_ie","n_siniestros")
    col_compv  = pick_column(df, "competencia_via","competencia de via", required=True)
    col_mant   = pick_column(df, "mantenimiento","mant")

    out = pd.DataFrame()
    out["codigo_ce"] = df[col_codigo]
    out["descripcion"] = df[col_desc]
    out["ubigeo_original"] = df[col_ubigeo].map(to_ubigeo6)
    out["competencia_via"] = df[col_compv].astype(str).map(norm)

    # ubigeo_gestor: si es provincial => XXYY01
    def compute_gestor(u, cv):
        if not u: return None
        return u[:4] + "01" if (cv or "").startswith("provinc") else u
    out["ubigeo_gestor"] = [compute_gestor(u, cv) for u, cv in zip(out["ubigeo_original"], out["competencia_via"])]

    if col_lat:  out["latitud"] = pd.to_numeric(df[col_lat], errors="coerce")
    if col_lon:  out["longitud"] = pd.to_numeric(df[col_lon], errors="coerce")
    if col_alum: out["alumnos"] = pd.to_numeric(df[col_alum], errors="coerce").astype("Int64")
    if col_doc:  out["docentes"] = pd.to_numeric(df[col_doc], errors="coerce").astype("Int64")
    if col_sin:  out["siniestros"] = pd.to_numeric(df[col_sin], errors="coerce").astype("Int64")
    out["mantenimiento"] = df[col_mant].map(to_bool) if col_mant else False

    # Orden final (ubigeo_gestor al inicio)
    cols_final = ["ubigeo_gestor", "ubigeo_original", "codigo_ce", "descripcion",
                  "latitud", "longitud", "alumnos", "docentes", "siniestros",
                  "mantenimiento", "competencia_via"]
    cols_final = [c for c in cols_final if c in out.columns]
    return out[cols_final]

# ----------------------------
# Export
# ----------------------------
def ensure_structure(project_root: Path):
    zs = project_root / "ZonasEscolares"
    processed = zs / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    return processed

def save_clean(df_clean: pd.DataFrame, processed_dir: Path, basename="Colegios_priorizados_PI2026_clean"):
    xlsx_path = processed_dir / f"{basename}.xlsx"
    csv_path  = processed_dir / f"{basename}.csv"
    df_clean.to_excel(xlsx_path, index=False)
    df_clean.to_csv(csv_path, index=False, encoding="utf-8")
    return xlsx_path, csv_path

# -----------------------

# ----------------------------
# Main
# ----------------------------
def main():
    ap = argparse.ArgumentParser(description="Genera CLEAN con ubigeo_gestor para PI2026 (solo hasta export).")
    ap.add_argument("--input-excel", default="./ZonasEscolares/Colegios_Priorizados_PI2026.xlsx")
    ap.add_argument("--sheet-name", default=None)
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()

    in_path = Path(args.input_excel)
    root = Path(args.project_root)
    assert in_path.exists(), f"No existe: {in_path}"

    # ======= AQUÍ SE LEE LA LISTA DE COLEGIOS PRIORIZADOS =======
    if args.sheet_name:
        df_raw = pd.read_excel(in_path, sheet_name=args.sheet_name)
    else:
        xlsx = pd.ExcelFile(in_path)
        df_raw = pd.read_excel(in_path, sheet_name=xlsx.sheet_names[0])
    # ============================================================

    df_clean = transform(df_raw)
    processed_dir = ensure_structure(root)
    clean_xlsx, clean_csv = save_clean(df_clean, processed_dir)

    print("=== CLEAN GENERADO ===")
    print("Excel:", clean_xlsx)
    print("CSV  :", clean_csv)

if __name__ == "__main__":
    main()