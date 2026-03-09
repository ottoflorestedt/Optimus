"""
Pytest-konfiguration: mockar Streamlit och tunga beroenden
så att app.py kan importeras utan att en riktig Streamlit-server körs.
"""
import sys
from unittest.mock import MagicMock

# ── Bygg en mock som liknar Streamlits beteende tillräckligt ──
mock_st = MagicMock()

# session_state = riktig dict så att default()-hjälparen fungerar
mock_st.session_state = {}

# sidebar.radio returnerar ett värde som inte matchar någon sida →
# ingen if/elif-gren för sidinnehåll körs, vilket undviker att
# widget-returvärden (MagicMock) skrivs in i session_state och
# sedan jämförs med heltal eller strängar.
# session_state["nav_sida"] sätts till "Indata" av default() (se app.py)
# och används bara i SIDOR.index() – det fungerar utan att sidan renderas.
mock_st.sidebar.radio.return_value = "__mock__"

# st.columns(spec) måste returnera rätt antal kolumner för att
# tuple-uppackning ska fungera (t.ex. c1, c2, c3 = st.columns([5,4,1]))
def _columns(spec):
    n = spec if isinstance(spec, int) else len(spec)
    return [MagicMock() for _ in range(n)]

mock_st.columns.side_effect = _columns

# Registrera alla mocks INNAN app.py importeras
sys.modules["streamlit"]             = mock_st
sys.modules["pandas"]                = MagicMock()
sys.modules["plotly"]                = MagicMock()
sys.modules["plotly.express"]        = MagicMock()
sys.modules["plotly.graph_objects"]  = MagicMock()
