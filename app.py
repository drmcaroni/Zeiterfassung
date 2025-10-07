import streamlit as st
import pandas as pd
import os
from datetime import datetime, time

# === Dateien ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"
DATEI_BUCHUNGEN = "buchungen.xlsx"

# === Sicherstellen, dass Buchungsdatei existiert ===
if not os.path.exists(DATEI_BUCHUNGEN):
    pd.DataFrame(columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]).to_excel(DATEI_BUCHUNGEN, index=False)

# === Verfügbare Zeiten laden ===
try:
    df_verf = pd.read_excel(DATEI_VERFUEGBAR)
    df_verf["Datum"] = pd.to_datetime(df_verf["Datum"]).dt.date
except Exception as e:
    st.error(f"Fehler beim Laden von {DATEI_VERFUEGBAR}: {e}")
    st.stop()

# === Buchungen laden ===
df_buch = pd.read_excel(DATEI_BUCHUNGEN)
if "Datum" in df_buch.columns:
    df_buch["Datum"] = pd.to_datetime(df_buch["Datum"], errors="coerce").dt.date

# === Hilfsfunktionen ===
def parse_time(t):
    """Wandelt Text wie '10:00 Uhr' in ein time-Objekt um"""
    try:
        return datetime.strptime(t.strip().replace(" Uhr", ""), "%H:%M").time()
    except:
        return None

def freie_zeitfenster(gesamt_start, gesamt_ende, buchungen):
    """Berechnet freie Teilzeiträume innerhalb eines Gesamtzeitraums"""
    freie = []
    start = gesamt_start
    for b_start, b_ende in sorted(buchungen):
        if b_start > start:
            freie.append((start, b_start))
        start = max(start, b_ende)
    if start < gesamt_ende:
        freie.append((start, gesamt_ende))
    return freie

# === Titel ===
st.title("🎵 KUG Registerproben Buchungssystem Studienjahr 2025/26")

# === Projektauswahl ===
projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

freie_tage = []

for _, row in df_proj.iterrows():
    datum = row["Datum"]
    zeitraum = row["Zeitraum"]

    try:
        z_start, z_ende = [parse_time(x) for x in zeitraum.split("-")]
    except:
        continue

    df_tag = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum)]
    buchungen = []
    for z in df_tag["Zeitraum"]:
        try:
            b_start, b_ende = [parse_time(x) for x in z.split("-")]
            if b_start and b_ende:
                buchungen.append((b_start, b_ende))
        except:
            pass

    freie_slots = freie_zeitfenster(z_start, z_ende, buchungen)

    for fs in freie_slots:
        diff = (datetime.combine(datetime.today(), fs[1]) - datetime.combine(datetime.today(), fs[0])).seconds / 3600
        if diff >= 3:  # nur Zeitfenster mit mindestens 3 Stunden
            freie_tage.append({
                "Datum": datum,
                "Start": fs[0],
                "Ende": fs[1],
                "Projekt": projekt
            })

if not freie_tage:
    st.warning("Keine freien Zeitfenster für dieses Projekt.")
    st.stop()

df_frei = pd.DataFrame(freie_tage)

# === Datumsauswahl ===
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

slots = df_frei[df_frei["Datum"] == datum_auswahl]

# === Auswahl des freien Tageszeitraums ===
slot = st.selectbox(
    "Verfügbares Zeitfenster:",
    slots.apply(lambda x: f"{x['Start'].strftime('%H:%M')} - {x['Ende'].strftime('%H:%M')}", axis=1)
)

# === 15-Minuten-Slots generieren ===
zeiten = pd.date_range("00:00", "23:45", freq="15min").strftime("%H:%M").tolist()
zeitfenster_start, zeitfenster_ende = [datetime.strptime(x, "%H:%M").time() for x in slot.split(" - ")]

# Berechne gültige 3-Stunden-Zeitfenster
verfuegbare_zeitfenster = []
for z in zeiten:
    t_start = datetime.strptime(z, "%H:%M").time()
    t_ende = (datetime.strptime(z, "%H:%M") + pd.Timedelta(hours=3)).time()
    if zeitfenster_start <= t_start < zeitfenster_ende and t_ende <= zeitfenster_ende:
        verfuegbare_zeitfenster.append(f"{z} - {t_ende.strftime('%H:%M')}")

# === Auswahl Startzeit / Endzeit ===
if verfuegbare_zeitfenster:
    zeitfenster_auswahl = st.selectbox("Startzeit (3 Stunden)", verfuegbare_zeitfenster)
    zeit_start, zeit_ende = zeitfenster_auswahl.split(" - ")
else:
    st.warning("Keine verfügbaren Zeitfenster mit einer Dauer von 3 Stunden.")
    st.stop()

# === Session State vorbereiten ===
if "instrument" not in st.session_state:
    st.session_state.instrument = ""
if "name" not in st.session_state:
    st.session_state.name = ""

# === Eingabefelder ===
instrument = st.text_input("Instrument *", value=st.session_state.instrument, key="instrument_field")
name = st.text_input("Name *", value=st.session_state.name, key="name_field")

# === Buchung speichern ===
if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.error("Bitte alle Pflichtfelder ausfüllen.")
    else:
        zeitraum = f"{zeit_start} - {zeit_ende}"

        neue_buchung = pd.DataFrame([{
            "Projekt": projekt,
            "Datum": datum_auswahl.strftime("%d.%m.%Y"),
            "Zeitraum": zeitraum,
            "Instrument": instrument.strip(),
            "Name": name.strip()
        }])

        # Speichern
        df_buch = pd.concat([df_buch, neue_buchung], ignore_index=True)
        df_buch.to_excel(DATEI_BUCHUNGEN, index=False)

        st.success(f"Buchung für **{projekt}** am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitraum}) gespeichert!")


# === Übersicht ===
st.subheader("📅 Aktuelle Buchungen")
st.dataframe(
    df_buch[df_buch["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"])
)
