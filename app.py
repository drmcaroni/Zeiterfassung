import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
import time
from google.oauth2.service_account import Credentials

# === Google Sheets Setup ===
SHEET_NAME = "KUG_Buchungssystem"
SHEET_ZEITEN = "Zeiten"
SHEET_BUCHUNGEN = "Buchungen"
SHEET_FREI = "Freie_Zeiten"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
creds = Credentials.from_service_account_info(
    st.secrets["google_service_account"], scopes=scope
)
client = gspread.authorize(creds)

# Falls Sheet "Freie_Zeiten" nicht existiert → anlegen
try:
    sheet_frei = client.open(SHEET_NAME).worksheet(SHEET_FREI)
except gspread.exceptions.WorksheetNotFound:
    sheet_frei = client.open(SHEET_NAME).add_worksheet(title=SHEET_FREI, rows=1000, cols=3)
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])

# === Caching (verhindert API-Überlastung) ===
@st.cache_data(ttl=60)
def lade_sheet(sheet_name):
    """Lädt Daten aus einem Google Sheet (nach Name) und cached sie 60 Sekunden."""
    ws = client.open(SHEET_NAME).worksheet(sheet_name)
    return pd.DataFrame(ws.get_all_records())

# === Hilfsfunktionen ===
def parse_time(t):
    try:
        return datetime.strptime(t.strip().replace(" Uhr", ""), "%H:%M").time()
    except:
        return None

def freie_zeitfenster(gesamt_start, gesamt_ende, buchungen):
    freie = []
    start = gesamt_start
    for b_start, b_ende in sorted(buchungen):
        if b_start > start:
            freie.append((start, b_start))
        start = max(start, b_ende)
    if start < gesamt_ende:
        freie.append((start, gesamt_ende))
    return freie

def berechne_freie_zeiten():
    """Berechnet alle freien Zeitfenster für alle Projekte und schreibt sie neu in das Sheet 'Freie_Zeiten'."""
    df_verf = lade_sheet(SHEET_ZEITEN)
    df_buch = lade_sheet(SHEET_BUCHUNGEN)

    freie_eintraege = []

    for _, z in df_verf.iterrows():
        proj = z["Projekt"]
        dat = z["Datum"]
        zeitraum = z["Zeitraum"]
        if not isinstance(zeitraum, str) or "-" not in zeitraum:
            continue
        start, ende = [parse_time(x) for x in zeitraum.split("-")]
        if not start or not ende:
            continue

        df_b = df_buch[(df_buch["Projekt"] == proj) & (df_buch["Datum"] == dat)]
        belegte = []
        for _, b in df_b.iterrows():
            try:
                b_start, b_ende = [parse_time(x) for x in b["Zeitraum"].split("-")]
                if b_start and b_ende:
                    belegte.append((b_start, b_ende))
            except:
                pass

        freie_slots = freie_zeitfenster(start, ende, belegte)
        for f_start, f_ende in freie_slots:
            diff_h = (datetime.combine(datetime.today(), f_ende) -
                      datetime.combine(datetime.today(), f_start)).total_seconds() / 3600
            if diff_h >= 1:
                freie_eintraege.append([proj, dat, f"{f_start.strftime('%H:%M')} - {f_ende.strftime('%H:%M')}"])

    # Sheet leeren und neu befüllen
    sheet_frei = client.open(SHEET_NAME).worksheet(SHEET_FREI)
    sheet_frei.clear()
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])
    if freie_eintraege:
        sheet_frei.update("A2", freie_eintraege)

# === Hauptprogramm ===
st.title("🎵 KUG Registerproben – Buchungssystem (GS Version)")

# Sheets laden
df_verf = lade_sheet(SHEET_ZEITEN)
df_buch = lade_sheet(SHEET_BUCHUNGEN)

if df_verf.empty:
    st.warning("Keine verfügbaren Zeiten gefunden.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()
df_proj["Datum"] = pd.to_datetime(df_proj["Datum"], dayfirst=True, errors="coerce").dt.date

freie_tage = []
for _, row in df_proj.iterrows():
    datum = row["Datum"]
    zeitraum = str(row["Zeitraum"])
    if pd.isna(datum) or "-" not in zeitraum:
        continue
    try:
        z_start, z_ende = [parse_time(x) for x in zeitraum.split("-")]
        if not z_start or not z_ende:
            continue
    except:
        continue

    df_tag = df_buch[(df_buch["Projekt"] == projekt) &
                     (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum)]
    buchungen = []
    for z in df_tag["Zeitraum"].dropna().astype(str):
        try:
            b_start, b_ende = [parse_time(x) for x in z.split("-")]
            if b_start and b_ende:
                buchungen.append((b_start, b_ende))
        except:
            pass

    freie_slots = freie_zeitfenster(z_start, z_ende, buchungen)
    for fs in freie_slots:
        diff_h = (datetime.combine(datetime.today(), fs[1]) -
                  datetime.combine(datetime.today(), fs[0])).total_seconds() / 3600
        if diff_h >= 3:
            freie_tage.append({"Datum": datum, "Start": fs[0], "Ende": fs[1], "Projekt": projekt})

if not freie_tage:
    st.warning("Keine freien Zeitfenster für dieses Projekt.")
    st.stop()

df_frei = pd.DataFrame(freie_tage)
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

zeit_info = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values[0]
st.info(f"**Gesamtzeitraum an diesem Tag:** {zeit_info}")

slot_row = df_proj[df_proj["Datum"] == datum_auswahl].iloc[0]
slot_start_time, slot_end_time = [parse_time(x) for x in str(slot_row["Zeitraum"]).split(" - ")]

df_tag = df_buch[(df_buch["Projekt"] == projekt) &
                 (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum_auswahl)]
buchungen = []
for z in df_tag["Zeitraum"].dropna().astype(str):
    try:
        b_start, b_ende = [parse_time(x) for x in z.split("-")]
        if b_start and b_ende:
            buchungen.append((b_start, b_ende))
    except:
        pass

freie_slots = freie_zeitfenster(slot_start_time, slot_end_time, buchungen)
verfuegbare_zeitfenster = []
for fs in freie_slots:
    start = fs[0]
    while True:
        ende = (datetime.combine(datetime.today(), start) + pd.Timedelta(hours=3)).time()
        if ende > fs[1]:
            break
        verfuegbare_zeitfenster.append(f"{start.strftime('%H:%M')} - {ende.strftime('%H:%M')}")
        start = (datetime.combine(datetime.today(), start) + pd.Timedelta(minutes=15)).time()

if not verfuegbare_zeitfenster:
    st.warning("Keine 3-Stunden-Zeitfenster verfügbar.")
    st.stop()

zeitfenster_auswahl = st.selectbox("Verfügbare 3-Stunden-Blöcke:", verfuegbare_zeitfenster)
instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

# === Buchung speichern ===
if st.button("💾 Buchung speichern"):
    if not projekt or not datum_auswahl or not zeitfenster_auswahl:
        st.warning("Bitte fülle alle Felder aus.")
    elif not instrument.strip():
        st.warning("Das Feld 'Instrument *' darf nicht leer sein.")
    elif not name.strip():
        st.warning("Das Feld 'Name *' darf nicht leer sein.")
    else:
        new_row = [projekt, datum_auswahl.strftime('%d.%m.%Y'), zeitfenster_auswahl, instrument, name]
        sheet_buchungen = client.open(SHEET_NAME).worksheet(SHEET_BUCHUNGEN)
        sheet_buchungen.append_row(new_row)
        time.sleep(1)

        # Nach Buchung alle freien Zeiten neu berechnen
        berechne_freie_zeiten()

        st.success(f"Buchung für {projekt} am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitfenster_auswahl}) gespeichert!")
        st.cache_data.clear()
        st.rerun()

# === Übersicht ===
st.subheader("📅 Aktuelle Buchungen (Projekt)")
if not df_buch.empty:
    df_show = df_buch.copy()
    df_show["Datum"] = pd.to_datetime(df_show["Datum"], dayfirst=True, errors="coerce").dt.strftime("%d.%m.%Y")
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]).reset_index(drop=True))
else:
    st.write("Keine Buchungen vorhanden.")
