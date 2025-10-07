import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time
import os

# === Dateien ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"

# === Google Sheets Setup ===
SHEET_NAME = "buchungen"  # Name deines Google Sheets (nicht der Datei-URL!)
SHEET_URL = "https://docs.google.com/spreadsheets/d/DEINE_SHEET_ID/edit"  # hier anpassen

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

creds = Credentials.from_service_account_info(
    st.secrets["google_service_account"], scopes=SCOPES
)
client = gspread.authorize(creds)

# Öffne oder erstelle Google Sheet
try:
    sh = client.open_by_url(SHEET_URL)
except Exception as e:
    st.error(f"Fehler beim Öffnen des Google Sheets: {e}")
    st.stop()

try:
    ws = sh.worksheet("Buchungen")
except gspread.exceptions.WorksheetNotFound:
    ws = sh.add_worksheet(title="Buchungen", rows="1000", cols="5")
    ws.append_row(["Projekt", "Datum", "Zeitraum", "Instrument", "Name"])

# === Verfügbare Zeiten laden (weiterhin lokal aus Excel) ===
try:
    df_verf = pd.read_excel(DATEI_VERFUEGBAR)
    df_verf["Datum"] = pd.to_datetime(df_verf["Datum"], dayfirst=True, errors="coerce").dt.date
except Exception as e:
    st.error(f"Fehler beim Laden von {DATEI_VERFUEGBAR}: {e}")
    st.stop()

# === Buchungen aus Google Sheet laden ===
buchungen_data = ws.get_all_records()
df_buch = pd.DataFrame(buchungen_data)

if not df_buch.empty and "Datum" in df_buch.columns:
    df_buch["Datum"] = pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date

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

def format_date_for_display(x):
    if isinstance(x, (datetime, date)):
        return x.strftime("%d.%m.%Y")
    return x

# === UI ===
st.title("🎵 KUG Registerproben – Buchungssystem 2025/26")

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

freie_tage = []
for _, row in df_proj.iterrows():
    datum = row["Datum"]
    zeitraum = str(row["Zeitraum"])
    if pd.isna(datum) or "-" not in zeitraum:
        continue

    z_start, z_ende = [parse_time(x) for x in zeitraum.split("-")]

    df_tag = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum)]
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
datum_auswahl = st.selectbox("Datum auswählen:", sorted(df_frei["Datum"].unique()), format_func=lambda d: d.strftime("%d.%m.%Y"))

slots = df_frei[df_frei["Datum"] == datum_auswahl]
slot_start_time = slots.iloc[0]["Start"]
slot_end_time = slots.iloc[0]["Ende"]

# --- Startzeiten berechnen ---
zeiten = pd.date_range("00:00", "23:45", freq="15min").strftime("%H:%M").tolist()

verfuegbare_zeitfenster = []
for z in zeiten:
    t_start = datetime.strptime(z, "%H:%M").time()
    t_ende = (datetime.strptime(z, "%H:%M") + pd.Timedelta(hours=3)).time()
    if (slot_start_time <= t_start) and (t_ende <= slot_end_time):
        # Prüfen, ob dieser Block bereits gebucht ist
        gebucht = any(
            parse_time(b_start) <= t_start < parse_time(b_ende)
            for b_start, b_ende in [
                (z.split(" - ")[0], z.split(" - ")[1]) for z in df_buch[df_buch["Datum"] == datum_auswahl]["Zeitraum"].dropna()
            ]
        )
        if not gebucht:
            verfuegbare_zeitfenster.append(f"{z} - {t_ende.strftime('%H:%M')}")

zeitfenster_auswahl = st.selectbox("Startzeit (3 Stunden):", verfuegbare_zeitfenster)
zeit_start, zeit_ende = [s.strip() for s in zeitfenster_auswahl.split(" - ")]

instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.error("Bitte alle Pflichtfelder ausfüllen.")
    else:
        neue_zeile = [projekt, datum_auswahl.strftime("%d.%m.%Y"), f"{zeit_start} - {zeit_ende}", instrument.strip(), name.strip()]
        ws.append_row(neue_zeile)
        st.success(f"Buchung für {projekt} am {datum_auswahl.strftime('%d.%m.%Y')} ({zeit_start} - {zeit_ende}) gespeichert!")

# === Übersicht ===
st.subheader("📅 Aktuelle Buchungen")
if not df_buch.empty:
    df_show = df_buch.copy()
    df_show["Datum"] = df_show["Datum"].apply(format_date_for_display)
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]))
else:
    st.info("Keine Buchungen vorhanden.")
