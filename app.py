import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time

# === Dateien ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"
DATEI_BUCHUNGEN = "buchungen.xlsx"

# === Sicherstellen, dass Buchungsdatei existiert ===
if not os.path.exists(DATEI_BUCHUNGEN):
    pd.DataFrame(columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]).to_excel(DATEI_BUCHUNGEN, index=False)

# === Verfügbare Zeiten laden ===
try:
    df_verf = pd.read_excel(DATEI_VERFUEGBAR)
    # Datum in df_verf als date-Objekte
    df_verf["Datum"] = pd.to_datetime(df_verf["Datum"], dayfirst=True, errors="coerce").dt.date
except Exception as e:
    st.error(f"Fehler beim Laden von {DATEI_VERFUEGBAR}: {e}")
    st.stop()

# === Buchungen laden ===
df_buch = pd.read_excel(DATEI_BUCHUNGEN)
if "Datum" in df_buch.columns:
    # Versuche, Datum als date zu parsen; falls nicht parsebar -> NaT
    df_buch["Datum"] = pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date

# === Hilfsfunktionen ===
def parse_time(t):
    """Konvertiert 'HH:MM' oder 'HH:MM Uhr' zu time-Objekt, sonst None"""
    try:
        return datetime.strptime(t.strip().replace(" Uhr", ""), "%H:%M").time()
    except:
        return None

# === UI ===
st.title("🎵 KUG Registerproben – Buchungssystem 2025/26")

# Projektauswahl
if df_verf.empty:
    st.warning("Die Datei 'verfuegbare_zeiten.xlsx' ist leer oder nicht geladen.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

# Datumsauswahl (Anzeigeformat TT.MM.JJJJ)
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_proj["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

# Verfügbarer Zeitraum für das ausgewählte Datum
zeitraum = df_proj[df_proj["Datum"] == datum_auswahl]["Zeitraum"].values
if len(zeitraum) > 0:
    st.write(f"Verfügbarer Zeitraum: **{zeitraum[0]}**")
else:
    st.warning("Kein Zeitraum für das ausgewählte Datum verfügbar.")
    st.stop()

# Generiere 15-Minuten-Slots (Startzeiten), rechne Endzeit = Start + 3h
zeiten = pd.date_range("00:00", "23:45", freq="15min").strftime("%H:%M").tolist()
z_start, z_ende = [parse_time(x) for x in zeitraum[0].split("-")]

verfuegbare_zeitfenster = []
for z in zeiten:
    t_start = datetime.strptime(z, "%H:%M").time()
    t_ende = (datetime.strptime(z, "%H:%M") + pd.Timedelta(hours=3)).time()
    # Start innerhalb des gesamten Zeitraums und Ende innerhalb des gesamten Zeitraums
    if (z_start <= t_start) and (t_ende <= z_ende):
        verfuegbare_zeitfenster.append(f"{z} - {t_ende.strftime('%H:%M')}")

if not verfuegbare_zeitfenster:
    st.warning("Keine 3-Stunden-Startzeiten in diesem Zeitraum verfügbar.")
    st.stop()

zeitfenster_auswahl = st.selectbox("Startzeit (3 Stunden):", verfuegbare_zeitfenster)
zeit_start, zeit_ende = [s.strip() for s in zeitfenster_auswahl.split(" - ")]

# Session State initialisieren (vor Widgets)
if "instrument_field" not in st.session_state:
    st.session_state["instrument_field"] = ""
if "name_field" not in st.session_state:
    st.session_state["name_field"] = ""

# Widgets (mit Keys instrument_field / name_field)
instrument = st.text_input("Instrument *", value=st.session_state["instrument_field"], key="instrument_field")
name = st.text_input("Name *", value=st.session_state["name_field"], key="name_field")

# === Buchung speichern ===
if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.error("Bitte alle Pflichtfelder ausfüllen.")
    else:
        zeitraum_buchung = f"{zeit_start} - {zeit_ende}"
        neue_buchung = pd.DataFrame([{
            "Projekt": projekt,
            "Datum": datum_auswahl,            # date-Objekt intern behalten
            "Zeitraum": zeitraum_buchung,
            "Instrument": instrument.strip(),
            "Name": name.strip()
        }])

        df_buch = pd.concat([df_buch, neue_buchung], ignore_index=True)

        # Bevor wir speichern: Datumsspalte in dd.mm.yyyy Strings konvertieren für Excel
        df_to_save = df_buch.copy()
        if "Datum" in df_to_save.columns:
            df_to_save["Datum"] = df_to_save["Datum"].apply(lambda x: x.strftime("%d.%m.%Y") if isinstance(x, (datetime, date)) else x)

        # Schreiben
        df_to_save.to_excel(DATEI_BUCHUNGEN, index=False)

        st.success(f"Buchung für **{projekt}** am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitraum_buchung}) gespeichert!")

# === Übersicht anzeigen (lesbar) ===
st.subheader("📅 Aktuelle Buchungen (Projekt)")
if not df_buch.empty:
    # Für Anzeige: Datum als dd.mm.yyyy
    df_show = df_buch.copy()
    if "Datum" in df_show.columns:
        df_show["Datum"] = df_show["Datum"].apply(lambda x: x.strftime("%d.%m.%Y") if isinstance(x, (datetime, date)) else x)
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]).reset_index(drop=True))
else:
    st.write("Keine Buchungen vorhanden.")