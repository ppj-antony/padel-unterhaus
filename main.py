import io
from functools import cmp_to_key
import pandas as pd
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

SPIELPLAN_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQK2uRw7bU4eF205lHo6qBNuomR9ZSNyHM78erlzNocqQJwmnvCpyVhEOYX67vpRwhFxmen3cUZIegK/pub?gid=860070356&single=true&output=csv"
TEAMS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQK2uRw7bU4eF205lHo6qBNuomR9ZSNyHM78erlzNocqQJwmnvCpyVhEOYX67vpRwhFxmen3cUZIegK/pub?gid=0&single=true&output=csv"


def lade_daten():
    try:
        # 1. Spielplan laden & Spaltennamen säubern
        res_spielplan = requests.get(SPIELPLAN_CSV_URL)
        df_spielplan = pd.read_csv(io.StringIO(res_spielplan.text))
        df_spielplan.columns = df_spielplan.columns.str.strip()

        tabelle = {}
        spiele = []
        direkte_duelle = {}

        for _, row in df_spielplan.iterrows():
            runde = str(row.get("Runde", "")).strip()
            t1 = str(row.get("Team_1", "")).strip()
            t2 = str(row.get("Team_2", "")).strip()
            datum = str(row.get("Datum", "")).strip()
            spielort = str(row.get("Spielort", "")).strip()

            # ABGESAGT-Checkbox & GRUND flexibel auslesen
            abgesagt_raw = row.get(
                "ABGESAGT", row.get("Abgesagt", row.get("abgesagt", ""))
            )
            abgesagt_val = str(abgesagt_raw).strip().upper()
            ist_abgesagt = abgesagt_val in ["TRUE", "WAHR", "1"]

            grund_raw = row.get(
                "GRUND", row.get("Grund", row.get("grund", ""))
            )
            grund_text = (
                str(grund_raw).strip() if not pd.isna(grund_raw) else ""
            )

            s1_val = row.get("Punkte_Team1")
            s2_val = row.get("Punkte_Team2")

            # Satz-Einzelergebnisse auslesen
            t1_s1, t2_s1 = row.get("T1_S1"), row.get("T2_S1")
            t1_s2, t2_s2 = row.get("T1_S2"), row.get("T2_S2")
            t1_s3, t2_s3 = row.get("T1_S3"), row.get("T2_S3")

            ist_gespielt = False
            if not ist_abgesagt and not pd.isna(s1_val) and not pd.isna(s2_val):
                s1_str = str(s1_val).strip()
                s2_str = str(s2_val).strip()
                if s1_str != "" and s2_str != "":
                    try:
                        s1, s2 = int(float(s1_str)), int(float(s2_str))
                        ist_gespielt = True
                    except ValueError:
                        ist_gespielt = False

            if ist_abgesagt:
                # Text für den Bereich unter der Linie festlegen
                untere_zeile = (
                    f"Grund: {grund_text}" if grund_text else "Abgesagt"
                )

                spiele.append(
                    {
                        "runde": runde,
                        "team1": t1,
                        "team2": t2,
                        "datum": datum,
                        "spielort": spielort,
                        "gespielt": False,
                        "abgesagt": True,
                        "ergebnis": "Abgesagt",
                        "satz_details": untere_zeile,
                    }
                )

            elif ist_gespielt:
                # Punktevergabe (3/2/1/0 Regel)
                if s1 == 3 and s2 == 0:
                    p1, p2 = 3, 0
                elif s1 == 2 and s2 == 1:
                    p1, p2 = 2, 1
                elif s1 == 1 and s2 == 2:
                    p1, p2 = 1, 2
                elif s1 == 0 and s2 == 3:
                    p1, p2 = 0, 3
                else:
                    p1, p2 = 0, 0

                # Direktes Duell merken
                if p1 > p2:
                    direkte_duelle[frozenset([t1, t2])] = t1
                elif p2 > p1:
                    direkte_duelle[frozenset([t1, t2])] = t2

                # Tabelle aktualisieren
                for t, p, gew, ver in [(t1, p1, s1, s2), (t2, p2, s2, s1)]:
                    if t not in tabelle:
                        tabelle[t] = {
                            "spiele": 0,
                            "punkte": 0,
                            "saetze_gew": 0,
                            "saetze_ver": 0,
                        }
                    tabelle[t]["spiele"] += 1
                    tabelle[t]["punkte"] += p
                    tabelle[t]["saetze_gew"] += gew
                    tabelle[t]["saetze_ver"] += ver

                # Satzdetails formatieren
                satzergebnisse = []
                for g1, g2 in [(t1_s1, t2_s1), (t1_s2, t2_s2), (t1_s3, t2_s3)]:
                    if not pd.isna(g1) and not pd.isna(g2):
                        try:
                            satzergebnisse.append(
                                f"{int(float(g1))}:{int(float(g2))}"
                            )
                        except ValueError:
                            pass

                satz_details = (
                    f"Sätze: {', '.join(satzergebnisse)}"
                    if satzergebnisse
                    else ""
                )

                spiele.append(
                    {
                        "runde": runde,
                        "team1": t1,
                        "team2": t2,
                        "datum": datum,
                        "spielort": spielort,
                        "gespielt": True,
                        "abgesagt": False,
                        "ergebnis": f"{s1}:{s2}",
                        "satz_details": satz_details,
                    }
                )
            else:
                spiele.append(
                    {
                        "runde": runde,
                        "team1": t1,
                        "team2": t2,
                        "datum": datum,
                        "spielort": spielort,
                        "gespielt": False,
                        "abgesagt": False,
                        "ergebnis": "VS",
                        "satz_details": "",
                    }
                )

        # Tabelleneinträge aufbereiten
        rangliste = []
        for team, stats in tabelle.items():
            rangliste.append(
                {
                    "team": team,
                    "spiele": stats["spiele"],
                    "punkte": stats["punkte"],
                    "sätze": f"{stats['saetze_gew']}:{stats['saetze_ver']}",
                    "diff": stats["saetze_gew"] - stats["saetze_ver"],
                }
            )

        # Sortierung: 1. Punkte -> 2. Direkter Vergleich -> 3. Satzdifferenz
        def vergleiche_teams(a, b):
            if a["punkte"] != b["punkte"]:
                return b["punkte"] - a["punkte"]

            duell_key = frozenset([a["team"], b["team"]])
            if duell_key in direkte_duelle:
                sieger = direkte_duelle[duell_key]
                if sieger == a["team"]:
                    return -1
                elif sieger == b["team"]:
                    return 1

            return b["diff"] - a["diff"]

        rangliste.sort(key=cmp_to_key(vergleiche_teams))

        for idx, item in enumerate(rangliste, 1):
            item["platz"] = idx

        # 2. Teams laden
        res_teams = requests.get(TEAMS_CSV_URL)
        df_teams = pd.read_csv(io.StringIO(res_teams.text))
        df_teams.columns = df_teams.columns.str.strip()

        teams_liste = []
        for _, row in df_teams.iterrows():
            teams_liste.append(
                {
                    "teamname": str(row.get("Teamname", "")).strip(),
                    "spieler1": str(row.get("Spieler 1", "")).strip(),
                    "spieler2": str(row.get("Spieler 2", "")).strip(),
                    "heimcourt": str(row.get("Heimcourt", "")).strip(),
                }
            )

        return rangliste, spiele, teams_liste

    except Exception as e:
        print("Fehler beim Laden der Daten:", e)
        return [], [], []


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    tabelle, spiele, teams = lade_daten()

    return templates.TemplateResponse(
        "index.html",
        {
            "tabelle": tabelle,
            "spiele": spiele,
            "teams": teams,
        },
        request=request,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
