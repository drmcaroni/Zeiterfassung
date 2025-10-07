import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time

# === Dateien ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"
DATEI_BUCHUNGEN = "buchungen.xlsx"

# === Helper: sichere Initialisierung von session_state keys vor Widgets ===
if "clear_after_submit" not in st.session_state:
    st.session_state["clear_after_submit"] = False

# Wenn ein Submit gerade stattgefunden hat, Felder VOR der Widget-Erzeugung zurücksetzen
# (so vermeiden wir die Streamlit-Fehlermeldung "cannot be modified after the widget ... instantiated")
if st.session_state.get("clear_after_submit", False):
    st.session_state["instrument_field"] = ""
    st.session_state["name_field"] = ""
    st.session_state["clear_after_submit"] = False

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

def freie_zeitfenster(gesamt_start, gesamt_ende, buchungen):
    """Berechnet freie Teilzeiträume innerhalb eines Gesamtzeitraums (buchungen = Liste von (time, time))."""
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
    """Gibt Datum als 'TT.MM.JJJJ' zurück (oder unverändert, falls None)."""
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
st.title("🎵 KUG Registerproben – Buchungssystem 2025/26")

# Projektauswahl
if df_verf.empty:
    st.warning("Die Datei 'verfuegbare_zeiten.xlsx' ist leer oder nicht geladen.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

# Sammle freie Zeitfenster (mindestens 3 Stunden in diesem Beispiel)
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

    # vorhandene Buchungen am Tag
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
        # Dauer in Stunden
        diff_h = (datetime.combine(datetime.today(), fs[1]) - datetime.combine(datetime.today(), fs[0])).total_seconds() / 3600
        if diff_h >= 3:  # Grenze: mind. 3 Stunden (wie gewünscht)
            freie_tage.append({"Datum": datum, "Start": fs[0], "Ende": fs[1], "Projekt": projekt})

if not freie_tage:
    st.warning("Keine freien Zeitfenster für dieses Projekt.")
    st.stop()

df_frei = pd.DataFrame(freie_tage)

# Datumsauswahl (Anzeigeformat TT.MM.JJJJ)
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_frei["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

slots = df_frei[df_frei["Datum"] == datum_auswahl]

# Auswahl des Tageszeitfensters
slot = st.selectbox(
    "Verfügbares Zeitfenster:",
    slots.apply(lambda x: f"{x['Start'].strftime('%H:%M')} - {x['Ende'].strftime('%H:%M')}", axis=1)
)

# --- 15-Minuten-Startzeiten generieren ---
zeiten = pd.date_range("00:00", "23:45", freq="15min").strftime("%H:%M").tolist()

# Zeitfenstergrenzen aus Auswahl
slot_start_time, slot_end_time = [datetime.strptime(x, "%H:%M").time() for x in slot.split(" - ")]

# --- Verfügbare 3-Stunden-Zeitfenster innerhalb des Tageszeitfensters ---
verfuegbare_zeitfenster = []
for z in zeiten:
    t_start_dt = datetime.strptime(z, "%H:%M")
    t_start = t_start_dt.time()
    t_ende_dt = t_start_dt + pd.Timedelta(hours=3)
    t_ende = t_ende_dt.time()

    # Bedingungen: Start >= Beginn des Tagesfensters UND Ende <= Ende des Tagesfensters
    if (slot_start_time <= t_start) and (t_ende_dt.time() <= slot_end_time):
        # Prüfen, ob das Ende noch am selben Tag liegt
        if t_ende_dt.date() == t_start_dt.date():
            verfuegbare_zeitfenster.append(f"{t_start.strftime('%H:%M')} - {t_ende.strftime('%H:%M')}")

# Sicherstellen, dass nur Zeiten innerhalb des Slots bleiben
verfuegbare_zeitfenster = [
    z for z in verfuegbare_zeitfenster
    if datetime.strptime(z.split(" - ")[1], "%H:%M").time() <= slot_end_time
]


# Session State initialisieren (vor Widgets, das haben wir oben gemacht für clear flag)
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
        zeitraum = f"{zeit_start} - {zeit_ende}"
        # Neue Buchung intern mit Datum als date-Objekt
        neue_buchung = pd.DataFrame([{
            "Projekt": projekt,
            "Datum": datum_auswahl,            # date-Objekt intern behalten
            "Zeitraum": zeitraum,
            "Instrument": instrument.strip(),
            "Name": name.strip()
        }])

        df_buch = pd.concat([df_buch, neue_buchung], ignore_index=True)

        # Bevor wir speichern: Datumsspalte in dd.mm.yyyy Strings konvertieren für Excel
        df_to_save = df_buch.copy()
        if "Datum" in df_to_save.columns:
            df_to_save["Datum"] = df_to_save["Datum"].apply(format_date_for_excel)

        # Schreiben
        df_to_save.to_excel(DATEI_BUCHUNGEN, index=False)

        st.success(f"Buchung für **{projekt}** am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitraum}) gespeichert!")


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
