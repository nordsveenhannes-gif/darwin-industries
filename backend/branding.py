INTERNAL_NAME = "Hosko’s Shady Shenanigans"
CLIENT_NAME = "Shenanigan Systems"
CLIENT_TAGLINE = "Websites, automation, and suspiciously efficient systems."

def client_logo_html(compact: bool = False) -> str:
    wordmark = "SS" if compact else "SHENANIGAN SYSTEMS"
    return f"""
    <span class="ss-logo" aria-label="{CLIENT_NAME}">
      <span class="ss-mark">S<span>S</span></span>
      <span class="ss-word">{wordmark}</span>
    </span>
    """

def client_logo_css() -> str:
    return """
    .ss-logo{display:inline-flex;align-items:center;gap:10px;font-weight:900;letter-spacing:.08em}
    .ss-mark{display:inline-grid;place-items:center;width:40px;height:40px;border:1px solid #ff6a00;
      border-radius:12px;background:linear-gradient(145deg,#16111d,#09080d);color:#f6f2ea;
      font:900 17px/1 ui-monospace,Consolas,monospace;box-shadow:0 0 22px rgba(255,106,0,.18)}
    .ss-mark span{color:#b7ff4a}
    .ss-word{font:900 12px/1 ui-monospace,Consolas,monospace;letter-spacing:.16em}
    """
