# ui_config.py
import flet as ft

# --- Brand palette (ajusta si quieres exactos) ---
BRAND_PRIMARY = "#dc774a"   # naranja principal
BRAND_PRIMARY_2 = "#f4a24c" # naranja claro / acento
BRAND_DARK = "#a94416"      # naranja oscuro (contraste)
BRAND_BG = "#f6f6f4"        # crema fondo
BRAND_SURFACE = "#f6f6f4"   # tarjetas
BRAND_SURFACE_2 = "#efedeb" # beige suave
BRAND_MINT = "#c1dbd0"      # verde suave
BRAND_MINT_2 = "#cad8cf"    # verde grisáceo
TEXT_MAIN = "#1f2937"       # gris oscuro moderno
TEXT_MUTED = "#6b7280"      # gris medio

# Layout
DEFAULT_PADDING = 20
DEFAULT_SECTION_SPACING = 25
INPUT_WIDTH_L = 500
INPUT_WIDTH_M = 350
INPUT_WIDTH_S = 200

# Modern UI tokens
RADIUS_L = 16
RADIUS_M = 12
RADIUS_S = 10
CARD_ELEVATION = 2

# Text styles
H1 = ft.TextStyle(size=20, weight="bold", color=TEXT_MAIN)
H2 = ft.TextStyle(size=16, weight="bold", color=TEXT_MAIN)
BODY = ft.TextStyle(size=13, color=TEXT_MAIN)
SMALL = ft.TextStyle(size=11, color=TEXT_MUTED)
