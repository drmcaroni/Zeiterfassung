import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# Google Sheets Setup
SHEET_NAME = "KUG_Buchungssystem"
ZEITEN_SHEET = "Zeiten"
BUCHUNGEN_SHEET = "Buchungen"
FREI_SHEET = "Freie_Zeiten"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["google_service_account"], scopes=scope)
client = gspread.authorize(creds)

sheet_zeiten = client.open(SHEET_NAME).worksheet(ZEITEN_SHEET)
sheet_buchungen = client.open(SHEET_NAME).worksheet(BUCHUNGEN_SHEET)

# Falls Freie_Zeiten-Blatt nicht existiert, anlegen
try:
    sheet_frei = client.open(SHEET_NAME).worksheet(FREI_SHEET)
except gspread.WorksheetNotFound:
    sheet_frei = client.open(SHEET_NAME).add_worksheet(title=FREI_SHEET, rows=100, cols=3)
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])

# Daten einlesen
df_zeiten = pd.DataFrame(sheet_zeiten.get_all_records())
df_buchungen = pd.DataFrame(sheet_buchungen.get_all_records())

st.title("🎵 KUG Buchungssystem")

# Auswahl Projekt & Datum
projekt = st.selectbox("Projekt auswählen:", sorted(df_zeiten["Projekt"].unique()))
datum = st.date_input("Datum auswählen:", min_value=datetime.today())

df_tag = df_zeiten[(df_zeiten["Projekt"] == projekt) & (df_zeiten["Datum"] == datum.strftime("%d.%m.%Y"))]

if df_tag.empty:
    st.warning("Für dieses Datum ist kein Zeitraum hinterlegt.")
else:
    # Zeitfenster anzeigen
    gesamtzeitraum = df_tag.iloc[0]["Zeitraum"]
    st.info(f"**Gesamtzeitraum:** {gesamtzeitraum}")

    # Startzeitberechnung
    start, ende = [datetime.strptime(t.strip(), "%H:%M") for t in gesamtzeitraum.split("-")]
    zeiten = []
    while start + timedelta(hours=3) <= ende:
        zeiten.append(start.strftime("%H:%M"))
        start += timedelta(minutes=15)

    df_tag_buch = df_buchungen[(df_buchungen["Projekt"] == projekt) & (df_buchungen["Datum"] == datum.strftime("%d.%m.%Y"))]

    belegte = []
    for _, b in df_tag_buch.iterrows():
        b_start, b_ende = [datetime.strptime(t.strip(), "%H:%M") for t in b["Zeitraum"].split("-")]
        belegte.append((b_start, b_ende))

    freie_startzeiten = []
    for s in zeiten:
        s_dt = datetime.strptime(s, "%H:%M")
        e_dt = s_dt + timedelta(hours=3)
        if all(e_dt <= b[0] or s_dt >= b[1] for b in belegte):
            freie_startzeiten.append(s)

    if freie_startzeiten:
        startzeit = st.selectbox("Startzeit (3 Stunden Block):", freie_startzeiten)
        instrument = st.text_input("Instrument:")
        name = st.text_input("Name:")

        if st.button("Buchung speichern"):
            new_entry = [projekt, datum.strftime("%d.%m.%Y"), f"{startzeit} - {(datetime.strptime(startzeit, '%H:%M') + timedelta(hours=3)).strftime('%H:%M')}", instrument, name]
            sheet_buchungen.append_row(new_entry)

            st.success(f"Buchung für {projekt} am {datum.strftime('%d.%m.%Y')} gespeichert ✅")

            # Freie Zeiten neu berechnen
            df_buchungen = pd.DataFrame(sheet_buchungen.get_all_records())
            df_zeiten = pd.DataFrame(sheet_zeiten.get_all_records())

            freie_zeiten = []

            for _, z in df_zeiten.iterrows():
                proj = z["Projekt"]
                dat = z["Datum"]
                zeitraum = z["Zeitraum"]
                start, ende = [datetime.strptime(t.strip(), "%H:%M") for t in zeitraum.split("-")]

                buchungen = df_buchungen[(df_buchungen["Projekt"] == proj) & (df_buchungen["Datum"] == dat)]
                belegte = []
                for _, b in buchungen.iterrows():
                    b_start, b_ende = [datetime.strptime(t.strip(), "%H:%M") for t in b["Zeitraum"].split("-")]
                    belegte.append((b_start, b_ende))
                belegte.sort()

                freie = []
                akt_start = start
                for b_start, b_ende in belegte:
                    if b_start - akt_start >= timedelta(hours=1):
                        freie.append((akt_start, b_start))
                    akt_start = max(akt_start, b_ende)
                if ende - akt_start >= timedelta(hours=1):
                    freie.append((akt_start, ende))

                for f_start, f_ende in freie:
                    freie_zeiten.append([proj, dat, f"{f_start.strftime('%H:%M')} - {f_ende.strftime('%H:%M')}"])

            # Freie_Zeiten aktualisieren
            sheet_frei.clear()
            sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])
            if freie_zeiten:
                sheet_frei.update("A2", freie_zeiten)

            st.rerun()

# Aktuelle Buchungen anzeigen
st.subheader("Aktuelle Buchungen")
df_buchungen_anzeige = df_buchungen[(df_buchungen["Projekt"] == projekt) & (df_buchungen["Datum"] == datum.strftime("%d.%m.%Y"))]
if not df_buchungen_anzeige.empty:
    st.table(df_buchungen_anzeige[["Zeitraum", "Instrument", "Name"]])
else:
    st.write("Keine Buchungen für diesen Tag.")
