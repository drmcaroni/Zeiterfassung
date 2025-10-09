import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import gspread
from google.oauth2.service_account import Credentials

# === Google Sheets Setup ===
SHEET_NAME = "KUG_Buchungssystem"
SHEET_ZEITEN = "Zeiten"
SHEET_BUCHUNGEN = "Buchungen"

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

# === Daten laden ===
df_verf = pd.DataFrame(sheet_zeiten.get_all_records())
df_buch = pd.DataFrame(sheet_buchungen.get_all_records())

# Sicherstellen, dass die Buchungstabelle die korrekten Spalten hat
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

def format_date_for_excel(x):
    if isinstance(x, (datetime, date)):
        return x.strftime("%d.%m.%Y")
    try:
        parsed = pd.to_datetime(x, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return x
        return parsed.strftime("%d.%m.%Y")
    except:
        return x

# === UI ===
st.title("🎵 KUG Registerproben – Buchungssystem (GS Version)")

if df_verf.empty:
    st.warning("Keine verfügbaren Zeiten gefunden.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

# Datenformatierung
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

    df_tag = df_buch[(df_buch["Projekt"] == projekt) & (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum)]
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

datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

# Zeige den gesamten verfügbaren Zeitraum (zur Info)
zeit_info = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values[0]
st.info(f"**Gesamtzeitraum an diesem Tag:** {zeit_info}")

# Berechne alle noch verfügbaren Startzeiten innerhalb dieses Gesamtzeitraums (3 Stunden-Blöcke)
slot_row = df_proj[df_proj["Datum"] == datum_auswahl].iloc[0]
slot_start_time, slot_end_time = [parse_time(x) for x in str(slot_row["Zeitraum"]).split(" - ")]

df_tag = df_buch[(df_buch["Projekt"] == projekt) & (pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date == datum_auswahl)]
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

if st.button("💾 Buchung speichern"):
    if not projekt or not datum_auswahl or not zeitfenster_auswahl:
        st.warning("Bitte fülle alle Felder aus.")
    else:
        # Buchung in Google Sheet schreiben
        new_row = [projekt, datum_auswahl.strftime('%d.%m.%Y'), zeitfenster_auswahl, instrument, name]
        sheet_buchungen.append_row(new_row)
        
        st.success(f"Buchung für {projekt} am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitfenster_auswahl}) gespeichert!")
        st.rerun()  # 🔁 Seite neu laden, damit Übersicht aktualisiert wird


# === Übersicht anzeigen ===
st.subheader("📅 Aktuelle Buchungen (Projekt)")
if not df_buch.empty:
    df_show = df_buch.copy()
    df_show["Datum"] = pd.to_datetime(df_show["Datum"], dayfirst=True, errors="coerce").dt.strftime("%d.%m.%Y")
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]).reset_index(drop=True))
else:
    st.write("Keine Buchungen vorhanden.")
