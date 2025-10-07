import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time

# === Dateien ===
DATEI_VERFUEGBAR = "verfuegbare_zeiten.xlsx"
DATEI_BUCHUNGEN = "buchungen.xlsx"

# === Session-State-Initialisierung (nur Default-Werte für Inputs) ===
if "instrument_field" not in st.session_state:
    st.session_state["instrument_field"] = ""
if "name_field" not in st.session_state:
    st.session_state["name_field"] = ""

# === Sicherstellen, dass Buchungsdatei existiert ===
if not os.path.exists(DATEI_BUCHUNGEN):
    pd.DataFrame(columns=["Projekt", "Datum", "Zeitraum", "Instrument", "Name"]).to_excel(DATEI_BUCHUNGEN, index=False)

# === Verfügbare Zeiten laden ===
try:
    df_verf = pd.read_excel(DATEI_VERFUEGBAR)
    df_verf["Datum"] = pd.to_datetime(df_verf["Datum"], dayfirst=True, errors="coerce").dt.date
except Exception as e:
    st.error(f"Fehler beim Laden von {DATEI_VERFUEGBAR}: {e}")
    st.stop()

# === Buchungen laden ===
df_buch = pd.read_excel(DATEI_BUCHUNGEN)
if "Datum" in df_buch.columns:
    df_buch["Datum"] = pd.to_datetime(df_buch["Datum"], dayfirst=True, errors="coerce").dt.date

# === Hilfsfunktionen ===
def normalize_dash(s: str) -> str:
    """Ersetzt verschiedene Gedankenstriche durch einfachen Bindestrich."""
    return s.replace("–", "-").replace("—", "-")

def parse_time(t):
    """Konvertiert 'HH:MM' oder 'HH:MM Uhr' zu time-Objekt, sonst None"""
    if t is None:
        return None
    try:
        return datetime.strptime(t.strip().replace(" Uhr", ""), "%H:%M").time()
    except:
        return None

def split_time_range(s: str):
    """Teilt 'HH:MM - HH:MM' (auch mit verschiedenen Strichen) in zwei strings."""
    if pd.isna(s):
        return None, None
    s2 = normalize_dash(str(s))
    parts = s2.split("-")
    if len(parts) < 2:
        return None, None
    return parts[0].strip(), parts[1].strip()

def freie_zeitfenster(gesamt_start, gesamt_ende, buchungen):
    """Berechnet freie Teilzeiträume innerhalb eines Gesamtzeitraums (buchungen = Liste von (time, time))."""
    freie = []
    start = gesamt_start
    # sicherstellen, dass buchungen sortiert sind
    buchungen_sorted = sorted(buchungen, key=lambda x: x[0])
    for b_start, b_ende in buchungen_sorted:
        if b_start > start:
            freie.append((start, b_start))
        start = max(start, b_ende)
    if start < gesamt_ende:
        freie.append((start, gesamt_ende))
    return freie

def format_date_for_excel(x):
    """Gibt Datum als 'TT.MM.JJJJ' zurück (oder unverändert, falls nicht parsebar)."""
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
    st.warning("Die Datei 'verfuegbare_zeiten.xlsx' ist leer oder konnte nicht geladen werden.")
    st.stop()

projekt = st.selectbox("Projekt auswählen:", sorted(df_verf["Projekt"].dropna().unique()))
df_proj = df_verf[df_verf["Projekt"] == projekt].copy()

if df_proj.empty:
    st.warning("Keine verfügbaren Zeiten für dieses Projekt.")
    st.stop()

# --- Datumsauswahl ---
datum_auswahl = st.selectbox(
    "Datum auswählen:",
    sorted(df_proj["Datum"].unique()),
    format_func=lambda d: d.strftime("%d.%m.%Y")
)

# Gesamtzeitraum (Anzeige)
row = df_proj[df_proj["Datum"] == datum_auswahl].iloc[0]
zeitraum_text = str(row["Zeitraum"])
teil0, teil1 = split_time_range(zeitraum_text)
slot_start_time = parse_time(teil0)
slot_end_time = parse_time(teil1)
if slot_start_time is None or slot_end_time is None:
    st.error("Ungültiges Zeitformat in 'verfuegbare_zeiten.xlsx' für dieses Datum.")
    st.stop()

st.info(f"**Gesamter Zeitraum an diesem Tag:** {slot_start_time.strftime('%H:%M')} – {slot_end_time.strftime('%H:%M')} Uhr")

# --- Berechne freie Intervalle (unter Berücksichtigung bereits gebuchter Zeiten) ---
df_tag = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum_auswahl)]
buchungen = []
for z in df_tag["Zeitraum"].dropna().astype(str):
    p0, p1 = split_time_range(z)
    b_start = parse_time(p0)
    b_end = parse_time(p1)
    if b_start and b_end:
        buchungen.append((b_start, b_end))

freie_slots = freie_zeitfenster(slot_start_time, slot_end_time, buchungen)

# --- Aus freien Slots alle gültigen 3-Stunden-Startzeiten erzeugen ---
DURATION_HOURS = 3
dauer_td = pd.Timedelta(hours=DURATION_HOURS)

# Hilfsdatum für Datumsarithmetik (heute reicht)
today = datetime.today().date()

candidate_starts = []
for fs_start, fs_end in freie_slots:
    # Start-DT & End-DT
    start_dt = datetime.combine(today, fs_start)
    end_dt = datetime.combine(today, fs_end)
    # Erlaubte Startzeitpunkte sind solche, für die start_dt + dauer_td <= end_dt
    cur = start_dt
    while cur + dauer_td <= end_dt + pd.Timedelta(seconds=0):  # <= erlaubt exakte Passungen
        # Formatieren als "HH:MM - HH:MM"
        s = cur.time().strftime("%H:%M")
        e = (cur + dauer_td).time().strftime("%H:%M")
        candidate_starts.append(f"{s} - {e}")
        cur = cur + pd.Timedelta(minutes=15)

# Entfernen von Duplikaten und sortieren
candidate_starts = sorted(list(dict.fromkeys(candidate_starts)))

if not candidate_starts:
    st.warning("Keine freien 3-Stunden-Startzeiten verfügbar (an diesem Datum).")
    st.stop()

# --- Auswahl der Startzeit durch den Benutzer ---
zeitfenster_auswahl = st.selectbox("Freie Startzeiten (3 Stunden):", candidate_starts)
zeit_start, zeit_ende = [s.strip() for s in zeitfenster_auswahl.split(" - ")]

# --- Eingabefelder ---
instrument = st.text_input("Instrument *", value=st.session_state["instrument_field"], key="instrument_field")
name = st.text_input("Name *", value=st.session_state["name_field"], key="name_field")

# --- Buchung speichern ---
if st.button("💾 Buchung speichern"):
    if not instrument.strip() or not name.strip():
        st.error("Bitte alle Pflichtfelder ausfüllen.")
    else:
        zeitraum_neu = f"{zeit_start} - {zeit_ende}"
        neue_buchung = pd.DataFrame([{
            "Projekt": projekt,
            "Datum": datum_auswahl,
            "Zeitraum": zeitraum_neu,
            "Instrument": instrument.strip(),
            "Name": name.strip()
        }])

        # Vor dem Speichern prüfen wir optional auf direkte Überschneidung
        # (Schutz gegen Race-Conditions / Doppelbuchung)
        # Erneut vorhandene Buchungen für Datum laden
        df_tag_current = df_buch[(df_buch["Projekt"] == projekt) & (df_buch["Datum"] == datum_auswahl)]
        conflict = False
        new_start = parse_time(zeit_start)
        new_end = parse_time(zeit_ende)
        if new_start is None or new_end is None:
            st.error("Interner Fehler beim Parsen der gewählten Zeit.")
        else:
            for z in df_tag_current["Zeitraum"].dropna().astype(str):
                p0, p1 = split_time_range(z)
                b_start = parse_time(p0)
                b_end = parse_time(p1)
                if b_start and b_end:
                    # Überschneidung: new_start < b_end and new_end > b_start
                    if (datetime.combine(today, new_start) < datetime.combine(today, b_end)) and \
                       (datetime.combine(today, new_end) > datetime.combine(today, b_start)):
                        conflict = True
                        break
            if conflict:
                st.error("Die gewählte Zeit überlappt inzwischen mit einer vorhandenen Buchung. Bitte neu wählen.")
            else:
                # Kein Konflikt — speichern
                df_buch = pd.concat([df_buch, neue_buchung], ignore_index=True)

                # Datum vor dem Schreiben formatieren
                df_save = df_buch.copy()
                if "Datum" in df_save.columns:
                    df_save["Datum"] = df_save["Datum"].apply(format_date_for_excel)

                df_save.to_excel(DATEI_BUCHUNGEN, index=False)
                st.success(f"Buchung für **{projekt}** am {datum_auswahl.strftime('%d.%m.%Y')} ({zeitraum_neu}) gespeichert!")

# --- Übersicht (Buchungen anzeigen) ---
st.subheader("📅 Aktuelle Buchungen")
if not df_buch.empty:
    df_show = df_buch.copy()
    if "Datum" in df_show.columns:
        df_show["Datum"] = df_show["Datum"].apply(
            lambda x: x.strftime("%d.%m.%Y") if isinstance(x, (datetime, date)) else x
        )
    st.dataframe(df_show[df_show["Projekt"] == projekt].sort_values(by=["Datum", "Zeitraum"]).reset_index(drop=True))
else:
    st.write("Keine Buchungen vorhanden.")
