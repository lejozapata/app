# app/rich_webview_window.py
import sys

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:63480/health"
    try:
        import webview  # pywebview
    except Exception as e:
        print("pywebview import failed:", e)
        return 2

    webview.create_window(
        "Editor enriquecido - SaraPsicologa",
        url,
        width=1100,
        height=780,
        resizable=True,
    )

    # En Windows, edgechromium usa WebView2
    webview.start(gui="edgechromium")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
