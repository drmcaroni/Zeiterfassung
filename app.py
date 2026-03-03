import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# ==============================
# KONFIGURATION
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

# ==============================
# SHEETS LADEN
# ==============================

def get_sheet(name):
    try:
        return client.open(SHEET_NAME).worksheet(name)
    except gspread.WorksheetNotFound:
        ws = client.open(SHEET_NAME).add_worksheet(
            title=name, rows=1000, cols=5
        )
        return ws


sheet_zeiten = get_sheet(SHEET_ZEITEN)
sheet_buchungen = get_sheet(SHEET_BUCHUNGEN)
sheet_frei = get_sheet(SHEET_FREI)

# Header sicherstellen
sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])


# ==============================
# HILFSFUNKTIONEN
# ==============================

def lade_zeiten():
    return pd.DataFrame(sheet_zeiten.get_all_records())


def lade_buchungen():
    df = pd.DataFrame(sheet_buchungen.get_all_records())
    if df.empty:
        df = pd.DataFrame(
            columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]
        )
    return df


def parse_time(t):
    try:
        return datetime.strptime(t.strip().replace(" Uhr", ""), "%H:%M").time()
    except:
        return None


def freie_zeitfenster(start, ende, buchungen):
    freie = []
    aktueller_start = start

    for b_start, b_ende in sorted(buchungen):
        if b_start > aktueller_start:
            freie.append((aktueller_start, b_start))
        aktueller_start = max(aktueller_start, b_ende)

    if aktueller_start < ende:
        freie.append((aktueller_start, ende))

    return freie


def lade_buchungen_fuer_tag(df_buch, projekt, datum):
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


# ==============================
# FREIE ZEITEN NEU BERECHNEN
# ==============================

def berechne_freie_zeiten():

    df_zeiten = lade_zeiten()
    df_buch = lade_buchungen()

    eintraege = []

    for _, r in df_zeiten.iterrows():

        projekt = r["Projekt"]

        datum = pd.to_datetime(
            r["Datum"], dayfirst=True, errors="coerce"
        )

        if pd.isna(datum):
            continue

        datum = datum.date()

        try:
            start, ende = [
                parse_time(x)
                for x in str(r["Zeitraum"]).split("-")
            ]
        except:
            continue

        buchungen = lade_buchungen_fuer_tag(df_buch, projekt, datum)
        freie = freie_zeitfenster(start, ende, buchungen)

        for fs, fe in freie:
            diff = (
                datetime.combine(datum, fe)
                - datetime.combine(datum, fs)
            ).total_seconds() / 3600

            if diff >= 1:
                eintraege.append([
                    projekt,
                    datum.strftime("%d.%m.%Y"),
                    f"{fs.strftime('%H:%M')} - {fe.strftime('%H:%M')}",
                ])

    sheet_frei.clear()
    sheet_frei.update("A1:C1", [["Projekt", "Datum", "Zeitraum"]])

    if eintraege:
        sheet_frei.update("A2", eintraege)


# ==============================
# UI
# ==============================

st.title("🎵 KUG Registerproben – Buchungssystem")

df_zeiten = lade_zeiten()
df_buch = lade_buchungen()

projekte = sorted(df_zeiten["Projekt"].dropna().unique())
projekt = st.selectbox("Projekt auswählen:", projekte)

# Manuelle Neuberechnung
if st.button("🔄 Freie Zeiten neu berechnen"):
    berechne_freie_zeiten()
    st.success("Freie Zeiten wurden neu berechnet.")
    st.rerun()

df_proj = df_zeiten[df_zeiten["Projekt"] == projekt].copy()
df_proj["Datum"] = pd.to_datetime(
    df_proj["Datum"], dayfirst=True, errors="coerce"
).dt.date

if df_proj.empty:
    st.warning("Keine Termine vorhanden.")
    st.stop()

datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_proj["Datum"].dropna().unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y"),
)

gesamt_zeitraum = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values[0]
st.info(f"Gesamtzeitraum: {gesamt_zeitraum}")

start_tag, ende_tag = [
    parse_time(x) for x in gesamt_zeitraum.split("-")
]

buchungen = lade_buchungen_fuer_tag(df_buch, projekt, datum_auswahl)
freie = freie_zeitfenster(start_tag, ende_tag, buchungen)

verfuegbare_slots = []

for fs, fe in freie:
    start_dt = datetime.combine(datum_auswahl, fs)
    end_dt = datetime.combine(datum_auswahl, fe)

    while start_dt + timedelta(hours=3) <= end_dt:
        ende_dt = start_dt + timedelta(hours=3)
        verfuegbare_slots.append(
            f"{start_dt.strftime('%H:%M')} - {ende_dt.strftime('%H:%M')}"
        )
        start_dt += timedelta(minutes=15)

if not verfuegbare_slots:
    st.warning("Keine 3-Stunden-Slots verfügbar.")
    st.stop()

zeitfenster = st.selectbox("Verfügbare 3-Stunden-Slots:", verfuegbare_slots)

instrument = st.text_input("Instrument *")
name = st.text_input("Name *")

if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.warning("Bitte alle Pflichtfelder ausfüllen.")
    else:
        sheet_buchungen.append_row([
            projekt,
            datum_auswahl.strftime("%d.%m.%Y"),
            zeitfenster,
            instrument,
            name,
        ])

        berechne_freie_zeiten()

        st.success("Buchung gespeichert.")
        st.rerun()

# ==============================
# BUCHUNGSÜBERSICHT
# ==============================

st.subheader("📅 Aktuelle Buchungen")

df_show = df_buch.copy()

if not df_show.empty:
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
