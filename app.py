import streamlit as st
import pandas as pd
from datetime import datetime, date, time, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ==============================
# Google Sheets Setup
# ==============================
SHEET_NAME = "KUG_Buchungssystem"
SHEET_ZEITEN = "Zeiten"
SHEET_BUCHUNGEN = "Buchungen"
SHEET_FREI = "Freie_Zeiten"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_info(
    st.secrets["google_service_account"], scopes=scope
)
client = gspread.authorize(creds)

sheet_zeiten = client.open(SHEET_NAME).worksheet(SHEET_ZEITEN)
sheet_buchungen = client.open(SHEET_NAME).worksheet(SHEET_BUCHUNGEN)

try:
    sheet_frei = client.open(SHEET_NAME).worksheet(SHEET_FREI)
except gspread.WorksheetNotFound:
    sheet_frei = client.open(SHEET_NAME).add_worksheet(
        title=SHEET_FREI, rows=1000, cols=3
    )
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])

# ==============================
# Daten laden
# ==============================
df_zeiten = pd.DataFrame(sheet_zeiten.get_all_records())
df_buch = pd.DataFrame(sheet_buchungen.get_all_records())

if df_buch.empty:
    df_buch = pd.DataFrame(
        columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]
    )

# ==============================
# Helper
# ==============================
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


def lade_buchungen(projekt, datum):
    df = df_buch[
        (df_buch["Projekt"] == projekt)
        & (
            pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date
            == datum
        )
    ]
    buchungen = []
    for z in df["Zeitraum"].dropna().astype(str):
        try:
            s, e = [parse_time(x) for x in z.split("-")]
            if s and e:
                buchungen.append((s, e))
        except:
            pass
    return buchungen


def berechne_freie_zeiten_und_schreibe_sheet():
    eintraege = []

    for _, r in df_zeiten.iterrows():
        projekt = r["Projekt"]
        datum = pd.to_datetime(r["Datum"], dayfirst=True, errors="coerce").date()
        if pd.isna(datum):
            continue

        try:
            start, ende = [parse_time(x) for x in r["Zeitraum"].split("-")]
        except:
            continue

        buchungen = lade_buchungen(projekt, datum)
        freie = freie_zeitfenster(start, ende, buchungen)

        for fs, fe in freie:
            diff_h = (
                datetime.combine(datum, fe) - datetime.combine(datum, fs)
            ).total_seconds() / 3600
            if diff_h >= 1:
                eintraege.append(
                    [
                        projekt,
                        datum.strftime("%d.%m.%Y"),
                        f"{fs.strftime('%H:%M')} - {fe.strftime('%H:%M')}",
                    ]
                )

    sheet_frei.clear()
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])
    if eintraege:
        sheet_frei.update("A2", eintraege)


# ==============================
# UI
# ==============================
st.title("🎵 KUG Registerproben – Buchungssystem")

projekt = st.selectbox(
    "Projekt auswählen:", sorted(df_zeiten["Projekt"].dropna().unique())
)

df_proj = df_zeiten[df_zeiten["Projekt"] == projekt].copy()
df_proj["Datum"] = pd.to_datetime(df_proj["Datum"], dayfirst=True, errors="coerce").dt.date

freie_tage = []

for _, r in df_proj.iterrows():
    datum = r["Datum"]
    if pd.isna(datum):
        continue

    start, ende = [parse_time(x) for x in r["Zeitraum"].split("-")]
    buchungen = lade_buchungen(projekt, datum)
    freie = freie_zeitfenster(start, ende, buchungen)

    for fs, fe in freie:
        if (
            datetime.combine(datum, fe) - datetime.combine(datum, fs)
        ).total_seconds() >= 3 * 3600:
            freie_tage.append(datum)

if not freie_tage:
    st.warning("Keine freien Termine für dieses Projekt.")
    st.stop()

datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(set(freie_tage)),
    format_func=lambda d: d.strftime("%d.%m.%Y"),
)

zeit_info = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values[0]
st.info(f"**Gesamtzeitraum:** {zeit_info}")

# ==============================
# Slot-Berechnung (KORREKT)
# ==============================
start_tag, ende_tag = [
    parse_time(x)
    for x in df_proj[df_proj["Datum"] == datum_auswahl]
    .iloc[0]["Zeitraum"]
    .split("-")
]

buchungen = lade_buchungen(projekt, datum_auswahl)
freie = freie_zeitfenster(start_tag, ende_tag, buchungen)

verfuegbare_zeitfenster = []

for fs, fe in freie:
    start_dt = datetime.combine(datum_auswahl, fs)
    end_dt = datetime.combine(datum_auswahl, fe)

    while start_dt + timedelta(hours=3) <= end_dt:
        ende_dt = start_dt + timedelta(hours=3)
        verfuegbare_zeitfenster.append(
            f"{start_dt.strftime('%H:%M')} - {ende_dt.strftime('%H:%M')}"
        )
        start_dt += timedelta(minutes=15)

if not verfuegbare_zeitfenster:
    st.warning("Keine 3-Stunden-Slots verfügbar.")
    st.stop()

zeitfenster = st.selectbox("Verfügbare 3-Stunden-Slots:", verfuegbare_zeitfenster)

instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.warning("Bitte alle Pflichtfelder ausfüllen.")
    else:
        sheet_buchungen.append_row(
            [
                projekt,
                datum_auswahl.strftime("%d.%m.%Y"),
                zeitfenster,
                instrument,
                name,
            ]
        )

        berechne_freie_zeiten_und_schreibe_sheet()
        st.success("Buchung gespeichert.")
        st.rerun()

# ==============================
# Übersicht
# ==============================
st.subheader("📅 Aktuelle Buchungen")
if not df_buch.empty:
    df_show = df_buch.copy()
    df_show["Datum"] = pd.to_datetime(
        df_show["Datum"], dayfirst=True, errors="coerce"
    ).dt.strftime("%d.%m.%Y")
    st.dataframe(
        df_show[df_show["Projekt"] == projekt]
        .sort_values(["Datum", "Zeitraum"])
        .reset_index(drop=True)
    )
else:
    st.write("Noch keine Buchungen vorhanden.")
