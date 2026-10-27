"""Weekly Genius App report: python3 -I tools/weekly_report.py
Reads both kids' state from Supabase and prints a plain-text summary of the last 7 days."""
import json, urllib.request, datetime, collections

URL = "https://dtcsjhxfnjxnfeyfeeaj.supabase.co/rest/v1/child_state?child_id=eq.{}&select=state"
KEY = "sb_publishable_-Nct9kceaJsPAlZ8jhStGw_EujErrUK"
KIDS = {"gio": ("Gio", ["text_complexity", "informational", "inference", "theme"]),
        "valentino": ("Valentino", ["inference", "evidence", "figurative", "setting", "plot_events", "point_of_view", "cause_effect",
                                   "info_explicit", "info_structure", "fact_opinion", "text_types"])}
# Typical silent reading speed is ~150-200 words/min at these ages; well over that means skimming.
FAST_WPM = {"gio": 380, "valentino": 300}
now = datetime.datetime.now()
week_ago = now - datetime.timedelta(days=7)


def pct(c, t):
    return f"{round(100 * c / t)}% ({c}/{t})" if t else "n/a"


for cid, (name, focus) in KIDS.items():
    req = urllib.request.Request(URL.format(cid), headers={"apikey": KEY, "Authorization": "Bearer " + KEY})
    st = json.load(urllib.request.urlopen(req))[0]["state"]
    hist = st.get("sessionHistory", [])
    week = [h for h in hist if datetime.datetime.strptime(h["date"], "%a %b %d %Y") >= week_ago.replace(hour=0, minute=0)]
    v2 = [h for h in week if h.get("v") == 2]
    days = collections.Counter(h["date"] for h in week)
    print(f"=== {name} ===")
    print(f"Reading level {st.get('readingLevel')} (cap {st.get('readingCap')}) | Math level {st.get('mathLevel')}")
    print(f"Sessions this week: {len(week)} on {len(days)} days | day streak {st.get('consecutiveStreak')}")
    if not v2:
        print("No sessions under the new scoring yet (old sessions allow retries, so accuracy isn't meaningful).")
        print("Scores:", ", ".join(f"{h['score']}/{h['total']}" for h in week) or "none")
    else:
        s = lambda k: sum(h.get(k, 0) for h in v2)
        print(f"Reading first-try: {pct(s('rC'), s('rT'))} | Focus/stretch: {pct(s('fC'), s('fT'))} | Math: {pct(s('mC'), s('mT'))}")
        sk = collections.defaultdict(lambda: [0, 0])
        for h in v2:
            for q in h.get("questions", []):
                for k in {q.get("skill"), q.get("also")} - {None, "math"}:
                    sk[k][1] += 1
                    sk[k][0] += q.get("correct", False)
        for k, (c, t) in sorted(sk.items(), key=lambda x: x[1][0] / x[1][1]):
            print(f"  {k}{' (focus)' if k in focus else ''}: {pct(c, t)}")
        ups = sum(1 for h in v2 if h.get("readingLevelUp"))
        downs = sum(1 for h in v2 if h.get("readingLevelDown"))
        print(f"Reading level changes this week: +{ups} / -{downs}")
        # Effort: story reading speed, rushed answers, hint use
        timed = [h for h in v2 if h.get("storySeconds") and h.get("storyWords")]
        if timed:
            wpm = [round(h["storyWords"] / (h["storySeconds"] / 60)) for h in timed]
            print(f"Story reading speed (words/min): {', '.join(map(str, wpm))}")
            fast = [f"{h['date']} ({w} wpm)" for h, w in zip(timed, wpm) if w > FAST_WPM[cid]]
            if fast:
                print(f"FLAG: story likely skimmed on: {', '.join(fast)}")
        qs = [q for h in v2 for q in h.get("questions", []) if q.get("secs") is not None]
        if qs:
            rushed = [q for q in qs if not q.get("correct") and ((q["type"] != "math" and q["secs"] < 6) or (q["type"] == "math" and q["secs"] < 10))]
            print(f"Answers missed in under ~5 seconds: {len(rushed)} of {len(qs)} questions")
            if len(rushed) >= 3:
                print("FLAG: several quick wrong answers -> possible rushing/guessing")
        # Answer-choice checks (sessions saved after Oct 24 keep the choices and true tap timing)
        mc = [q for h in v2 if h.get("timing") == 2 for q in h.get("questions", []) if q.get("choices") and q.get("correctChoice")]
        if mc:
            def longest(q):
                lens = [len(c) for c in q["choices"]]
                return lens.index(max(lens)) == "ABCD".index(q["correctChoice"])
            lr = sum(longest(q) for q in mc)
            print(f"Correct answer was the longest choice: {pct(lr, len(mc))} (about 25% expected if lengths give nothing away)")
            if len(mc) >= 8 and lr / len(mc) > 0.45:
                print("FLAG: correct answers are often the longest choice -> guessable without reading")
            letters = collections.Counter(q["correctChoice"] for q in mc)
            print("Correct-letter spread:", dict(sorted(letters.items())))
            fast = [q for q in mc if q.get("firstSecs") is not None and q["firstSecs"] < 5 and q.get("correct")]
            print(f"Right on first tap in under 5 seconds: {len(fast)} of {len(mc)}")
            away = sum(q.get("awaySecs", 0) for q in mc)
            if away:
                print(f"Time the app was in the background during questions: {away}s")
        ebq = [q for h in v2 for q in h.get("questions", []) if q.get("eb")]
        if ebq:
            print(f"Earn-back questions added: {len(ebq)} | right on first try: {pct(sum(q.get('correct', False) for q in ebq), len(ebq))}")
        resumed = [h["date"] for h in v2 if h.get("resumed")]
        if resumed:
            print(f"Sessions resumed after a refresh: {', '.join(resumed)}")
        mq = [q for h in v2 for q in h.get("questions", []) if q["type"] == "math"]
        if mq:
            print(f"Math: {sum(q['correct'] and not q.get('hintsUsed') for q in mq)}/{len(mq)} without hints, gave up (showed answer) on {sum(not q['correct'] for q in mq)}")
        if any(h.get("readingAtCap") for h in v2):
            print("FLAG: reading is at its cap and qualified to go higher -> parent decision needed")
        low = [h["date"] for h in v2 if h.get("rT") and h["rC"] / h["rT"] < 0.6]
        if low:
            print(f"FLAG: sessions under 60% reading: {', '.join(low)}")
    print()
