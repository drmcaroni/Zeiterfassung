import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
import gspread
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

# === Google Sheets öffnen ===
sheet_zeiten = client.open(SHEET_NAME).worksheet(SHEET_ZEITEN)
sheet_buchungen = client.open(SHEET_NAME).worksheet(SHEET_BUCHUNGEN)

# Falls Freie_Zeiten nicht existiert, anlegen
try:
    sheet_frei = client.open(SHEET_NAME).worksheet(SHEET_FREI)
except gspread.WorksheetNotFound:
    sheet_frei = client.open(SHEET_NAME).add_worksheet(title=SHEET_FREI, rows=100, cols=3)
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])

# === Daten laden ===
df_verf = pd.DataFrame(sheet_zeiten.get_all_records())
df_buch = pd.DataFrame(sheet_buchungen.get_all_records())

required_cols = ["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]
for col in required_cols:
    if col not in df_buch.columns:
        df_buch[col] = None

# === Helper ===
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
st.title("🎵 KUG Registerproben – Buchungssystem (GS Version)")

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
    z_start, z_ende = [parse_time(x) for x in zeitraum.split("-")]
    if not z_start or not z_ende:
        continue

    df_tag = df_buch[
        (df_buch["Projekt"] == projekt)
        & (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum)
    ]

    buchungen = []
    for z in df_tag["Zeitraum"].dropna().astype(str):
        b_start, b_ende = [parse_time(x) for x in z.split("-")]
        if b_start and b_ende:
            buchungen.append((b_start, b_ende))

    freie_slots = freie_zeitfenster(z_start, z_ende, buchungen)
    for fs in freie_slots:
        diff_h = (
            datetime.combine(datetime.today(), fs[1])
            - datetime.combine(datetime.today(), fs[0])
        ).total_seconds() / 3600
        if diff_h >= 3:
            freie_tage.append({"Datum": datum, "Projekt": projekt})

if not freie_tage:
    st.warning("Keine freien Zeitfenster für dieses Projekt.")
    st.stop()

df_frei = pd.DataFrame(freie_tage).drop_duplicates()

datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

zeit_info = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values[0]
st.info(f"**Gesamtzeitraum an diesem Tag:** {zeit_info}")

# === FIX: korrekte Berechnung der 3-Stunden-Slots ===
slot_row = df_proj[df_proj["Datum"] == datum_auswahl].iloc[0]
slot_start_time, slot_end_time = [parse_time(x) for x in slot_row["Zeitraum"].split("-")]

df_tag = df_buch[
    (df_buch["Projekt"] == projekt)
    & (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum_auswahl)
]

buchungen = []
for z in df_tag["Zeitraum"].dropna().astype(str):
    b_start, b_ende = [parse_time(x) for x in z.split("-")]
    if b_start and b_ende:
        buchungen.append((b_start, b_ende))

freie_slots = freie_zeitfenster(slot_start_time, slot_end_time, buchungen)
verfuegbare_zeitfenster = []

basis_datum = datetime.combine(datetime.today().date(), time(0, 0))
gesamt_ende_dt = datetime.combine(basis_datum.date(), slot_end_time)

for fs in freie_slots:
    start_dt = datetime.combine(basis_datum.date(), fs[0])
    slot_ende_dt = datetime.combine(basis_datum.date(), fs[1])

    while True:
        ende_dt = start_dt + timedelta(hours=3)
        if ende_dt > slot_ende_dt or ende_dt > gesamt_ende_dt:
            break

        verfuegbare_zeitfenster.append(
            f"{start_dt.strftime('%H:%M')} - {ende_dt.strftime('%H:%M')}"
        )
        start_dt += timedelta(minutes=15)

if not verfuegbare_zeitfenster:
    st.warning("Keine 3-Stunden-Zeitfenster verfügbar.")
    st.stop()

zeitfenster_auswahl = st.selectbox("Verfügbare 3-Stunden-Blöcke:", verfuegbare_zeitfenster)

instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.warning("Bitte alle Pflichtfelder ausfüllen.")
    else:
        sheet_buchungen.append_row([
            projekt,
            datum_auswahl.strftime('%d.%m.%Y'),
            zeitfenster_auswahl,
            instrument,
            name
        ])
        st.success("Buchung gespeichert!")
        st.rerun()
