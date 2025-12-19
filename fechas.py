from datetime import date, datetime

def calcular_edad(fecha_nacimiento_raw) -> str:
    """
    Devuelve edad en años como string, o '-' si no se puede calcular.
    Soporta:
      - 'DD-MM-YYYY' (como tu Excel)
      - 'YYYY-MM-DD' (si llega así desde UI/DB)
      - date/datetime
    """
    if not fecha_nacimiento_raw:
        return "-"

    # Normalizar a date
    if isinstance(fecha_nacimiento_raw, datetime):
        fn = fecha_nacimiento_raw.date()
    elif isinstance(fecha_nacimiento_raw, date):
        fn = fecha_nacimiento_raw
    else:
        s = str(fecha_nacimiento_raw).strip()
        fn = None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
            try:
                fn = datetime.strptime(s[:10], fmt).date()
                break
            except Exception:
                pass
        if fn is None:
            return "-"

    hoy = date.today()
    edad = hoy.year - fn.year - ((hoy.month, hoy.day) < (fn.month, fn.day))
    return str(max(0, edad))
