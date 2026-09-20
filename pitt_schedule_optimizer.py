"""
Pitt Schedule Optimizer
Run: python3 pitt_schedule_optimizer.py
- Left: fill in the courses table + type your preferences -> Optimize -> weekly color-block calendar
- Right: saved schedules (sort by score/time), export .ics to import into Google Calendar
"""
from itertools import product
from datetime import datetime, timedelta
import re, json, math


def t(hhmm):
    """'9:30' -> minutes since midnight."""
    h, m = str(hhmm).strip().split(":")
    return int(h) * 60 + int(m)

def _hm(mins):
    return f"{mins//60:02d}:{mins%60:02d}"

class Course:
    """One section of a course."""
    def __init__(self, course, section, days, start, end, building, instructor=""):
        self.course = course
        self.section = section
        self.days = set(days)
        self.start = start
        self.end = end
        self.building = building
        self.instructor = instructor

def course_to_dict(c):
    return {"course": c.course, "section": c.section, "days": sorted(c.days),
            "start": c.start, "end": c.end, "building": c.building, "instructor": c.instructor}

def dict_to_course(d):
    return Course(d["course"], d["section"], "".join(d["days"]),
                  d["start"], d["end"], d["building"], d.get("instructor", ""))

# lat, lon for Pitt buildings; straight-line walking time via Haversine.
BUILDING_COORDS = {
    "Cathedral":    (40.4442, -79.9531),
    "Posvar":       (40.4416, -79.9538),
    "Lawrence":     (40.4424, -79.9553),
    "Benedum":      (40.4438, -79.9585),
    "Sennott":      (40.4415, -79.9563),
    "Hillman":      (40.4432, -79.9535),
    "Clapp":        (40.4461, -79.9531),
    "Langley":      (40.4468, -79.9538),
    "Crawford":     (40.4468, -79.9538),
    "Chevron":      (40.4458, -79.9576),
    "Eberly":       (40.4459, -79.9584),
    "Alumni":       (40.4456, -79.9539),
    "Allen":        (40.4446, -79.9583),
    "Thackeray":    (40.4443, -79.9573),
    "Frick":        (40.4417, -79.9513),
    "Bellefield":   (40.4454, -79.9509),
    "Barco":        (40.4419, -79.9557),
    "Salk":         (40.4427, -79.9629),
    "Info Sciences":(40.4458, -79.9510),
    "WPU":          (40.4430, -79.9522),
    "Sutherland":   (40.4465, -79.9605),
}
WALK_SPEED_KMH = 4.8
PADDING_MIN = 4
DEFAULT_MIN = 10

def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

def walk(a, b):
    """Walking minutes: straight-line Haversine distance / walking speed + padding."""
    if a == b:
        return 0
    if a not in BUILDING_COORDS or b not in BUILDING_COORDS:
        return DEFAULT_MIN
    lat1, lon1 = BUILDING_COORDS[a]
    lat2, lon2 = BUILDING_COORDS[b]
    dist_km = _haversine_km(lat1, lon1, lat2, lon2)
    return round(dist_km / WALK_SPEED_KMH * 60 + PADDING_MIN)

def conflict(a, b):
    """Same weekday and overlapping time -> conflict."""
    return bool(a.days & b.days) and a.start < b.end and b.start < a.end

def score(schedule, prefs):
    """Lower is better. Weighted penalties: walking, early classes, long gaps."""
    walk_total = early_pen = gap_pen = 0
    by_day = {}
    for s in schedule:
        for d in s.days:
            by_day.setdefault(d, []).append(s)
    for d, classes in by_day.items():
        classes.sort(key=lambda x: x.start)
        for c in classes:
            if c.start < 9 * 60:
                early_pen += 1
        for prev, nxt in zip(classes, classes[1:]):
            walk_total += walk(prev.building, nxt.building)
            gap = nxt.start - prev.end
            if gap > prefs["gap_threshold"]:
                gap_pen += 1
    return (prefs["walk_weight"] * walk_total
            + prefs["early_weight"] * early_pen
            + prefs["gap_weight"] * gap_pen)

def parse_rows(rows):
    """Table rows -> {course: [Course objects]}."""
    registry = {}
    for row in rows:
        if not row or not str(row[0]).strip():
            continue
        course = str(row[0]).strip()
        section = str(row[1]).strip()
        days = str(row[2]).strip()
        try:
            start, end = t(row[3]), t(row[4])
        except Exception:
            continue
        location = str(row[5]).strip()
        instructor = str(row[6]).strip() if len(row) > 6 else ""
        registry.setdefault(course, []).append(
            Course(course, section, days, start, end, location, instructor))
    return registry

def optimize(course_names, prefs, registry):
    """Enumerate all non-conflicting section combos, score, sort ascending."""
    results = []
    for combo in product(*[registry[c] for c in course_names]):
        pairs = [(combo[i], combo[j]) for i in range(len(combo)) for j in range(i+1, len(combo))]
        if not any(conflict(a, b) for a, b in pairs):
            results.append((score(combo, prefs), combo))
    results.sort(key=lambda x: x[0])
    return results

#Nemotron integration
def parse_courses(text, registry):
    """Let Nemotron pick which courses the user wants, only from known courses."""
    known = list(registry.keys())
    try:
        from nemotron import ask
        system = ("You extract the courses a student wants. Return ONLY a JSON array, "
                  "choosing ONLY from: " + ", ".join(known) + ". Skip others. JSON only.")
        _, raw = ask(text, system=system, enable_thinking=False)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            wanted = json.loads(m.group(0))
            return [c for c in wanted if c in registry]
    except Exception as e:
        print("Nemotron course parse failed:", e)
    return known

def parse_preferences(text):
    """Let Nemotron turn plain-English preferences into weight JSON; fall back to defaults."""
    try:
        from nemotron import ask
        system = ("Convert scheduling preferences into ONLY a JSON object. Keys: "
                  "walk_weight (default 1.0), early_weight (default 10.0, raise if hate 8ams), "
                  "gap_weight (default 2.0), gap_threshold (minutes, default 90). JSON only.")
        _, raw = ask(text, system=system, enable_thinking=False)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        print("Nemotron prefs parse failed, using defaults:", e)
    return {"walk_weight": 1.0, "early_weight": 10.0, "gap_weight": 2.0, "gap_threshold": 90}

def explain(combo, sc):
    """Legacy single-schedule explanation."""
    try:
        from nemotron import ask
        desc = "\n".join(
            f"{c.course} {c.section} {sorted(c.days)} {_hm(c.start)}-{_hm(c.end)} @ {c.building}"
            for c in combo)
        system = "You are a friendly college schedule assistant. In 2 short sentences, explain why this ranked schedule is good."
        _, text = ask(f"Schedule (lower score = better, score={sc:.1f}):\n{desc}", system=system)
        return text
    except Exception as e:
        print("Nemotron explain failed:", e)
        return "(Nemotron busy — here is the ranked schedule.)"

def score_breakdown(combo, prefs):
    """Same logic as score(), but return the three penalty components."""
    by_day = {}
    for s in combo:
        for d in s.days:
            by_day.setdefault(d, []).append(s)
    walk_total = early_pen = gap_pen = 0
    for d, classes in by_day.items():
        classes.sort(key=lambda x: x.start)
        for c in classes:
            if c.start < 9 * 60:
                early_pen += 1
        for prev, nxt in zip(classes, classes[1:]):
            walk_total += walk(prev.building, nxt.building)
            gap = nxt.start - prev.end
            if gap > prefs["gap_threshold"]:
                gap_pen += 1
    return {"walk_minutes": walk_total, "early_classes": early_pen, "long_gaps": gap_pen}

def describe_combo(combo):
    return "\n".join(
        f"{c.course} {c.section} {sorted(c.days)} {_hm(c.start)}-{_hm(c.end)} @ {c.building}"
        for c in combo)

def explain_comparison(results, prefs, n=3):
    """Compare top N schedules with real numbers and let Nemotron explain."""
    top = results[:n]
    if not top:
        return "No valid, conflict-free schedule was found with these courses."
    best_score, worst_score = results[0][0], results[-1][0]
    blocks = []
    for i, (sc, combo) in enumerate(top, 1):
        bd = score_breakdown(combo, prefs)
        blocks.append(
            f"Option {i} — score {sc:.0f}\n{describe_combo(combo)}\n"
            f"  -> {bd['early_classes']} class(es) before 9am, "
            f"{bd['walk_minutes']} total walking minutes, "
            f"{bd['long_gaps']} gap(s) longer than {prefs['gap_threshold']} min")
    breakdown_text = "\n\n".join(blocks)
    try:
        from nemotron import ask
        if len(top) == 1:
            system = (
                "You are explaining a single class schedule's score to a student. Lower score = better; "
                "0 means no penalties at all. Explain in 3-4 sentences what the score represents and "
                "specifically why it's good or bad, citing the real class times and buildings given.")
        else:
            system = (
                "You are judging a ranked list of class schedules for a student. Lower score = better. "
                "The score is a weighted sum of three penalties: early classes before 9am, minutes spent "
                f"walking between buildings, and gaps longer than the student's threshold. Across all "
                f"{len(results)} valid schedules considered, the best score found was {best_score:.0f} and "
                f"the worst was {worst_score:.0f}. In 4-5 sentences: (1) explain in plain terms what a score "
                "number actually represents, (2) say specifically why Option 1 beats the others, and "
                "(3) name one concrete tradeoff the student gives up by choosing Option 1 over Option 2 or 3 "
                "if there is one. Be specific with real times and buildings from the data.")
        _, text = ask(breakdown_text, system=system)
        return text
    except Exception as e:
        print("Nemotron comparison failed:", e)
        return "(Nemotron busy — raw comparison:)\n\n" + breakdown_text

#Weekly calendar HTML
DAY_LABELS = ["M", "T", "W", "R", "F"]
COLORS = ["#bfe3b8", "#bcd6f2", "#f6d9b8", "#dcc2f0", "#f7ecb0", "#bde8dd", "#f2c2d2"]

def course_color(code):
    return COLORS[sum(ord(c) for c in code) % len(COLORS)]

def render_calendar_html(combo, title=""):
    # Auto-fit the visible window to the actual class times (+/- padding).
    if combo:
        earliest = min(c.start for c in combo)
        latest = max(c.end for c in combo)
    else:
        earliest, latest = 8 * 60, 18 * 60
    START = max(0, (earliest // 60 - 1) * 60)
    END = min(24 * 60, (latest // 60 + 2) * 60)
    HOURS = (END - START) // 60
    by_day = {d: [] for d in DAY_LABELS}
    for c in combo:
        for d in c.days:
            if d in by_day:
                by_day[d].append(c)
    lines_html, labels_html = "", ""
    for h in range(HOURS + 1):
        top = h / HOURS * 100
        lines_html += f'<div class="hline" style="top:{top:.3f}%"></div>'
        if h < HOURS:
            hour24 = START // 60 + h
            period = "AM" if hour24 < 12 else "PM"
            hour12 = hour24 % 12 or 12
            labels_html += f'<div class="tlabel" style="top:{top:.3f}%">{hour12} {period}</div>'
    days_html = ""
    for i, d in enumerate(DAY_LABELS):
        blocks = ""
        for c in sorted(by_day[d], key=lambda x: x.start):
            top = (c.start - START) / (HOURS * 60) * 100
            height = (c.end - c.start) / (HOURS * 60) * 100
            blocks += (f'<div class="blk" style="top:{top:.2f}%;height:{max(height,3):.2f}%;'
                       f'background:{course_color(c.course)}">'
                       f'<b>{c.course}</b><br><small>{c.building} · {_hm(c.start)}-{_hm(c.end)}</small></div>')
        days_html += f'<div class="daycol" style="left:{i*20}%">{blocks}</div>'
    head = ''.join(f'<div class="dayh">{d}</div>' for d in DAY_LABELS)
    grid_height = max(HOURS * 55, 300)
    return f"""
    <div style="margin:8px 0"><b style="color:#111;font-size:15px">{title}</b></div>
    <div class="cal">
      <div class="calhead"><div></div>{head}</div>
      <div class="calbody">
        <div class="tickcol">{labels_html}</div>
        <div class="gridcol" style="height:{grid_height}px">{lines_html}{days_html}</div>
      </div>
    </div>
    <style>
      .cal {{background:#fff;border:1px solid #d0d0d0;border-radius:8px;overflow:hidden;font-size:13px;color:#111}}
      .calhead,.calbody {{display:flex}}
      .calhead > div {{width:20%;text-align:center;font-weight:bold;padding:6px 0;background:#f5f5f5;color:#111;border-left:1px solid #e6e6e6;font-size:14px}}
      .calhead > div:first-child {{width:6%;border-left:none}}
      .tickcol {{width:6%;position:relative;background:#fff}}
      .tlabel {{position:absolute;transform:translateY(-7px);font-size:11px;color:#888;text-align:right;padding-right:6px;white-space:nowrap}}
      .gridcol {{width:94%;position:relative;background:#fff}}
      .hline {{position:absolute;left:0;right:0;border-top:1px solid #eeeeee}}
      .daycol {{position:absolute;top:0;bottom:0;width:20%;border-left:1px solid #eeeeee}}
      .blk {{position:absolute;left:5px;right:5px;border-radius:6px;padding:5px 7px;overflow:hidden;color:#1a1a1a;box-shadow:0 1px 2px rgba(0,0,0,.1)}}
      .blk b {{font-size:15px}}
      .blk small {{font-size:11px}}
    </style>"""

#Local saves + ICS export
SAVE_FILE = "saved_schedules.json"

def load_saved():
    try:
        with open(SAVE_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def persist_save(combo, score, explanation):
    data = load_saved()
    data.append({
        "id": (max([d["id"] for d in data], default=0) + 1),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "score": score,
        "explanation": explanation,
        "courses": [course_to_dict(c) for c in combo],
    })
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=2)
    return data

def sort_saved(data, mode):
    if mode == "By save time (newest)":
        return sorted(data, key=lambda x: x["saved_at"], reverse=True)
    return sorted(data, key=lambda x: x["score"])

def build_ics(combo, path="pitt_schedule.ics"):
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=1)
    daymap = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PittSchedule//EN"]
    for c in combo:
        for d in c.days:
            if d not in daymap:
                continue
            start_date = monday + timedelta(days=daymap[d])
            ds = datetime.combine(start_date, datetime.min.time()).replace(hour=c.start//60, minute=c.start%60)
            de = datetime.combine(start_date, datetime.min.time()).replace(hour=c.end//60, minute=c.end%60)
            lines += ["BEGIN:VEVENT",
                      f"SUMMARY:{c.course} {c.section}",
                      f"LOCATION:{c.building}",
                      f"DTSTART:{ds.strftime('%Y%m%dT%H%M%S')}",
                      f"DTEND:{de.strftime('%Y%m%dT%H%M%S')}",
                      "RRULE:FREQ=WEEKLY;COUNT=15",
                      "END:VEVENT"]
    lines += ["END:VCALENDAR"]
    with open(path, "w") as f:
        f.write("\r\n".join(lines))
    return path

#Gradio UI
def make_choices(data):
    return [(f"score {d['score']:.0f} · {d['saved_at'][11:16]}", d["id"]) for d in data]

def launch_ui():
    import gradio as gr
    example_rows = [
        ["CMPINF 0401", "1000", "MWF", "13:00", "13:50", "Info Sciences", ""],
        ["MATH 0220", "2000", "MWF", "10:00", "10:50", "Posvar", ""],
        ["ENGCMP 0216", "1000", "MWF", "10:00", "10:50", "Cathedral", ""],
        ["ECON 0110", "1000", "MWF", "13:00", "13:50", "Lawrence", ""],
    ]
    SAVED = load_saved()                 # plain Python globals, not gr.State
    CURRENT = {"combo": None, "score": None, "explanation": ""}

    def do_optimize(rows, prefs_text):
        registry = parse_rows(rows)
        if not registry:
            return "<p>Add at least one course in the table first.</p>", ""
        names = parse_courses(prefs_text, registry) or list(registry.keys())
        prefs = parse_preferences(prefs_text)
        tops = optimize(names, prefs, registry)
        if not tops:
            return "<p>These courses all conflict — no valid schedule found.</p>", ""
        sc, combo = tops[0]
        expl = explain_comparison(tops, prefs, n=min(3, len(tops)))
        CURRENT["combo"] = [course_to_dict(c) for c in combo]
        CURRENT["score"] = sc
        CURRENT["explanation"] = expl
        return render_calendar_html(combo, f"Top pick · score {sc:.0f}"), expl

    def do_save():
        if not CURRENT["combo"]:
            return gr.update()
        nonlocal SAVED
        combo = [dict_to_course(d) for d in CURRENT["combo"]]
        SAVED = sort_saved(persist_save(combo, CURRENT["score"], CURRENT["explanation"]),
                           "By score (best first)")
        return gr.update(choices=make_choices(SAVED), value=SAVED[0]["id"])

    def show_saved(sid):
        if sid is None:
            return ""
        item = next((d for d in SAVED if d["id"] == sid), None)
        if not item:
            return ""
        combo = [dict_to_course(d) for d in item["courses"]]
        return render_calendar_html(combo, f"Saved · score {item['score']:.0f} · {item['saved_at'][11:16]}")

    def do_sort(mode):
        return gr.update(choices=make_choices(sort_saved(SAVED, mode)))

    def do_export(sid):
        if sid is None:
            return None
        item = next((d for d in SAVED if d["id"] == sid), None)
        if not item:
            return None
        combo = [dict_to_course(d) for d in item["courses"]]
        return build_ics(combo)

    def do_import(file):
        if file is None:
            return gr.update(), "No file selected."
        try:
            import pandas as pd
        except ImportError:
            return gr.update(), "Install pandas first: pip3 install pandas openpyxl"
        try:
            path = file.name if hasattr(file, "name") else file
            if str(path).lower().endswith((".xlsx", ".xls")):
                df = pd.read_excel(path, header=None)
            else:
                df = pd.read_csv(path, header=None)
            rows = df.values.tolist()
            if rows and str(rows[0][0]).strip().lower() == "course":
                rows = rows[1:]
            fixed_rows = []
            for r in rows:
                r = list(r)
                while len(r) < 7:
                    r.append("")
                fixed_rows.append([("" if pd.isna(x) else str(x)) for x in r[:7]])
            if not fixed_rows:
                return gr.update(), "File read but no course rows found."
            return gr.update(value=fixed_rows), f"Imported {len(fixed_rows)} row(s)."
        except Exception as e:
            return gr.update(), f"Import failed: {e}"

    theme = gr.themes.Base(primary_hue="blue", secondary_hue="yellow").set(
        button_primary_background_fill="#003594",
        button_primary_background_fill_hover="#FFB81C")
    with gr.Blocks(title="Pitt Schedule Optimizer", theme=theme) as demo:
        gr.Markdown("# 🐆 Pitt Schedule Optimizer")
        with gr.Row():
            with gr.Column(scale=2):
                with gr.Row():
                    file_in = gr.File(label="Import courses (.csv/.xlsx)", file_types=[".csv", ".xlsx", ".xls"])
                    btn_import = gr.Button("Load into table")
                import_status = gr.Markdown("")
                courses_in = gr.Dataframe(
                    headers=["course", "section", "days", "start", "end", "location", "instructor"],
                    datatype=["str"]*7, value=example_rows,
                    row_count=(1, "dynamic"), col_count=(7, "fixed"), type="array",
                    label="Enter your courses")
                prefs_in = gr.Textbox(lines=2,
                    value="No 8am, I hate walking between buildings.",
                    label="Your preferences (plain English)",
                    info="e.g. 'no 8ams, hate walking between buildings'")
                btn_opt = gr.Button("Optimize", variant="primary")
                cal_out = gr.HTML()
                expl_out = gr.Textbox(label="Why this schedule")
                btn_save = gr.Button("Save this schedule ⭐")
            with gr.Column(scale=1):
                gr.Markdown("### 📅 Saved schedules")
                sort_mode = gr.Radio(["By score (best first)", "By save time (newest)"],
                                     value="By score (best first)", label="Sort by")
                saved_list = gr.Radio(label="Pick a schedule")
                saved_cal = gr.HTML()
                btn_export = gr.Button("Export .ics → Google Calendar")
                file_out = gr.File(label="Download .ics")

        btn_opt.click(do_optimize, [courses_in, prefs_in], [cal_out, expl_out])
        btn_import.click(do_import, file_in, [courses_in, import_status])
        btn_save.click(do_save, None, saved_list)
        saved_list.change(show_saved, saved_list, saved_cal)
        sort_mode.change(do_sort, sort_mode, saved_list)
        btn_export.click(do_export, saved_list, file_out)

    demo.launch()

if __name__ == "__main__":
    launch_ui()

