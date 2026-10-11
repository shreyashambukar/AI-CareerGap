# AI CareerGap

**AI CareerGap** helps students identify the gap between their current skills and a target tech role, then gives them a personalised learning plan — supporting [UN SDG 8: Decent Work and Economic Growth](https://sdgs.un.org/goals/goal8).

---

## Features

- **Skill gap analysis** for Data Analyst, Data Scientist, AI Engineer, ML Engineer, and Web Developer — or paste any job description
- **Personalised learning plan** tailored to your weekly availability
- **Skill practice challenges** — one hands-on exercise per missing skill
- **Portfolio project idea** — one project to demonstrate your gaps
- **Interactive roadmap tracker** — check off tasks, add notes, persisted in browser localStorage
- **AI career mentor chat** — powered by Google Gemini (falls back gracefully without an API key)
- **Print / Save as PDF** — clean print stylesheet hides UI chrome

---

## Quick Start (Windows PowerShell)

### 1. Create and activate a virtual environment
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies
```powershell
pip install -r requirements.txt
```

### 3. Add your Gemini API key
```powershell
Copy-Item .env.example .env
notepad .env
```
Replace `your_gemini_api_key_here` with your actual key from [Google AI Studio](https://aistudio.google.com/app/apikey).  
**Never share or commit `.env`.**

### 4. Run the app
```powershell
flask run
```
Open `http://127.0.0.1:5000` in your browser.

---

## Project Structure

```
ai-careergap/
├── app.py                  # Flask application — routes and Gemini logic
├── career_data.json        # Built-in skill lists for supported roles
├── requirements.txt        # Python dependencies
├── .env.example            # Template for environment variables
├── .gitignore              # Excludes .env and .venv from git
├── README.md               # This file
├── templates/
│   ├── base.html           # Shared layout, nav, and footer
│   ├── index.html          # Home page
│   ├── assess.html         # Assessment form
│   └── results.html        # Results, roadmap, chat, and print view
└── static/
    ├── style.css           # All app styling
    └── roadmap.js          # localStorage roadmap tracker
```

---

## Manual Test Checklist

1. [ ] Open `http://127.0.0.1:5000` — home page explains SDG 8 and has a **Start** button
2. [ ] Click **Start**, fill the form (try "Data Analyst", add a few skills, set hours per week)
3. [ ] Submit — results page shows match %, matched skills, missing skills
4. [ ] Scroll to **Learning Plan** — steps match your missing skills and weekly hours
5. [ ] Scroll to **Practice Challenges** — one exercise per gap
6. [ ] Scroll to **Portfolio Project Idea**
7. [ ] Scroll to **Roadmap Tracker** — check a task, add a note, refresh the page — progress persists
8. [ ] Scroll to **AI Mentor Chat** — ask a career question, check the response
9. [ ] Click **Print / Save as PDF** — browser print preview shows only the report content
10. [ ] Test without a Gemini key (empty `GEMINI_API_KEY` in `.env`) — app still works with a friendly message

---

## UN SDG 8 Connection

> "Promote sustained, inclusive and sustainable economic growth, full and productive employment and decent work for all."

AI CareerGap directly supports this goal by reducing the information gap that prevents students — especially those without career advisors or industry connections — from understanding what skills employers actually want and how to acquire them efficiently.

---

## License

MIT
