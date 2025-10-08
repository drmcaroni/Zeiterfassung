import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time
import gspread
from google.oauth2.service_account import Credentials

# === KONFIGURATION ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"
SHEET_NAME = "buchungen"  # Name deiner Google Sheets Datei
WORKSHEET_NAME = "Buchungen"  # Name des Tabellenblatts

# === Google Sheets Setup ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["google_service_account"], scopes=scope)
client = gspread.authorize(creds)

# Versuche, das Tabellenblatt "Buchungen" zu öffnen – oder erstelle es
try:
    sheet = client.open(SHEET_NAME).worksheet(WORKSHEET_NAME)
except gspread.exceptions.WorksheetNotFound:
    sh = client.open(SHEET_NAME)
    sheet = sh.add_worksheet(title=WORKSHEET_NAME, rows="1000", cols="5")
    sheet.append_row(["Projekt", "Datum", "Zeitraum", "Instrument", "Name"])

# === Buchungen laden ===
buchungen_data = sheet.get_all_records()
df_buch = pd.DataFrame(buchungen_data)
if df_buch.empty:
    df_buch = pd.DataFrame(columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"])

# === Verfügbare Zeiten laden ===
try:
    df_verf = pd.read_excel(DATEI_VERFUEGBAR)
    df_verf["Datum"] = pd.to_datetime(df_verf["Datum"], dayfirst=True, errors="coerce").dt.date
except Exception as e:
    st.error(f"Fehler beim Laden von {DATEI_VERFUEGBAR}: {e}")
    st.stop()

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

# === UI ===
st.title("🎵 KUG Registerproben – Buchungssystem 2025/26")

# Projektauswahl
if df_verf.empty:
    st.warning("Die Datei 'verfuegbare_zeiten.xlsx' ist leer oder nicht geladen.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

# Freie Tage berechnen
freie_tage = []
for _, row in df_proj.iterrows():
    datum = row["Datum"]
    zeitraum = str(row["Zeitraum"])
    if pd.isna(datum) or "-" not in zeitraum:
        continue
    try:
        z_start, z_ende = [parse_time(x) for x in zeitraum.split("-")]
        if z_start is None or z_ende is None:
            continue
    except:
        continue

    df_tag = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum.strftime("%d.%m.%Y"))]
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
        diff_h = (datetime.combine(datetime.today(), fs[1]) - datetime.combine(datetime.today(), fs[0])).total_seconds() / 3600
        if diff_h >= 3:
            freie_tage.append({"Datum": datum, "Start": fs[0], "Ende": fs[1], "Projekt": projekt})

if not freie_tage:
    st.warning("Keine freien Zeitfenster für dieses Projekt.")
    st.stop()

df_frei = pd.DataFrame(freie_tage)

# Datumsauswahl
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

# Gesamter Zeitraum anzeigen (nur Info)
slot_info = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].iloc[0]
st.info(f"Verfügbarer Tageszeitraum: **{slot_info} Uhr**")

# Slot-Start/Ende aus dem Infofeld holen
slot_start_time, slot_end_time = [parse_time(x) for x in slot_info.split("-")]

# Erzeuge alle 3h-Blöcke innerhalb des Tageszeitraums (nur freie)
zeiten = pd.date_range("00:00", "23:45", freq="15min").strftime("%H:%M").tolist()
verfuegbare_zeitfenster = []

# Alle Buchungen dieses Tages für Abgleich
df_tag = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum_auswahl.strftime("%d.%m.%Y"))]
gebuchte = []
for z in df_tag["Zeitraum"].dropna().astype(str):
    try:
        b_start, b_ende = [parse_time(x) for x in z.split("-")]
        if b_start and b_ende:
            gebuchte.append((b_start, b_ende))
    except:
        pass

freie_slots = freie_zeitfenster(slot_start_time, slot_end_time, gebuchte)
for fs in freie_slots:
    start, ende = fs
    while (datetime.combine(datetime.today(), start) + pd.Timedelta(hours=3)).time() <= ende:
        ende_block = (datetime.combine(datetime.today(), start) + pd.Timedelta(hours=3)).time()
        verfuegbare_zeitfenster.append(f"{start.strftime('%H:%M')} - {ende_block.strftime('%H:%M')}")
        start = (datetime.combine(datetime.today(), start) + pd.Timedelta(minutes=15)).time()

if not verfuegbare_zeitfenster:
    st.warning("Keine freien 3-Stunden-Blöcke verfügbar.")
    st.stop()

zeitfenster_auswahl = st.selectbox("Verfügbare Startzeiten (3 Stunden):", verfuegbare_zeitfenster)
zeit_start, zeit_ende = [s.strip() for s in zeitfenster_auswahl.split(" - ")]

# Eingabe Felder
instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

# === Buchung speichern ===
if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.error("Bitte alle Pflichtfelder ausfüllen.")
    else:
        zeitraum = f"{zeit_start} - {zeit_ende}"
        neue_buchung = [projekt, datum_auswahl.strftime("%d.%m.%Y"), zeitraum, instrument.strip(), name.strip()]
        sheet.append_row(neue_buchung)
        st.success(f"Buchung für **{projekt}** am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitraum}) gespeichert!")

# === Übersicht anzeigen ===
st.subheader("📅 Aktuelle Buchungen (Projekt)")
if not df_buch.empty:
    df_show = df_buch.copy()
    if "Datum" in df_show.columns:
        df_show["Datum"] = pd.to_datetime(df_show["Datum"], dayfirst=True, errors="coerce").dt.strftime("%d.%m.%Y")
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]).reset_index(drop=True))
else:
    st.write("Keine Buchungen vorhanden.")
