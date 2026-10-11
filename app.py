"""
AI CareerGap — app.py
Flask web application that compares a student's skills against a target role
and generates a personalised learning plan using Google Gemini.
"""

import json
import os
import re

from markupsafe import Markup, escape
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()  # reads .env if present

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")


# ---------------------------------------------------------------------------
# Markdown → plain-text Jinja filter  (auto-escaping safe)
# ---------------------------------------------------------------------------

def _strip_md_inline(text: str) -> str:
    """Remove bold/italic markers and backtick code spans from a line."""
    # Bold+italic  ***…*** / ___…___
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)
    text = re.sub(r"_{3}(.+?)_{3}", r"\1", text)
    # Bold  **…** / __…__
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)
    text = re.sub(r"_{2}(.+?)_{2}", r"\1", text)
    # Italic  *…* / _…_  (only when surrounded by word chars or spaces)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)(?<!_)_(?!_)", r"\1", text)
    # Inline code  `…`
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text


@app.template_filter("md_to_plain")
def md_to_plain(raw: str) -> Markup:
    """
    Convert Gemini Markdown output to clean HTML paragraphs and headings
    without using |safe on unsanitised AI text.

    Rules applied (in order per line):
      - Heading lines (###, ##, #) → <h4>/<h3>/<h3>
      - Numbered list items (1. …) → plain paragraph with the number preserved
      - Bullet list items (- … / * …) → plain paragraph with a bullet prefix
      - Blank lines → paragraph break
      - Everything is HTML-escaped before wrapping in tags
    """
    if not raw:
        return Markup("")

    lines = raw.splitlines()
    html_parts: list[str] = []
    pending: list[str] = []  # accumulate consecutive plain lines into a <p>

    def flush_pending():
        if pending:
            content = escape(" ".join(pending))
            html_parts.append(f"<p>{content}</p>")
            pending.clear()

    for line in lines:
        stripped = line.strip()

        # --- Blank line → paragraph break ---
        if not stripped:
            flush_pending()
            continue

        # --- Heading lines ---
        h_match = re.match(r"^(#{1,3})\s+(.*)", stripped)
        if h_match:
            flush_pending()
            level = len(h_match.group(1))
            tag = "h4" if level >= 3 else "h3"
            heading_text = escape(_strip_md_inline(h_match.group(2)))
            html_parts.append(f"<{tag} class='ai-heading'>{heading_text}</{tag}>")
            continue

        # --- Numbered list items  "1. text" ---
        num_match = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if num_match:
            flush_pending()
            item_text = escape(_strip_md_inline(num_match.group(2)))
            html_parts.append(
                f"<p class='ai-list-item'>"
                f"<span class='ai-num'>{escape(num_match.group(1))}.</span> {item_text}</p>"
            )
            continue

        # --- Bullet list items  "- text"  or  "* text" ---
        bullet_match = re.match(r"^[-*]\s+(.*)", stripped)
        if bullet_match:
            flush_pending()
            item_text = escape(_strip_md_inline(bullet_match.group(1)))
            html_parts.append(f"<p class='ai-list-item'><span class='ai-bullet'>•</span> {item_text}</p>")
            continue

        # --- Horizontal rule ---
        if re.match(r"^[-*_]{3,}$", stripped):
            flush_pending()
            html_parts.append("<hr class='ai-rule'>")
            continue

        # --- Plain text line — accumulate for paragraph merging ---
        pending.append(_strip_md_inline(stripped))

    flush_pending()
    return Markup("\n".join(html_parts))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()

# Load built-in career data
with open("career_data.json", "r", encoding="utf-8") as _f:
    CAREER_DATA = json.load(_f)

SUPPORTED_ROLES = list(CAREER_DATA.keys())

# ---------------------------------------------------------------------------
# Gemini helper
# ---------------------------------------------------------------------------

def _get_gemini_client():
    """Return a google-genai client if the API key is set, otherwise None."""
    if not GEMINI_API_KEY:
        return None
    try:
        from google import genai  # noqa: PLC0415
        client = genai.Client(api_key=GEMINI_API_KEY)
        return client
    except Exception:
        return None


def gemini_generate(prompt: str) -> tuple[str, bool]:
    """
    Send *prompt* to Gemini and return (text, success).
    On any failure returns a friendly message and success=False.
    """
    client = _get_gemini_client()
    if client is None:
        return (
            "AI features are unavailable — no Gemini API key is configured. "
            "See .env.example for setup instructions.",
            False,
        )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip(), True
    except Exception as exc:
        return (
            f"Gemini is temporarily unavailable ({type(exc).__name__}). "
            "Your results below are still accurate — only the AI-generated text is missing.",
            False,
        )


# ---------------------------------------------------------------------------
# Skill analysis helpers
# ---------------------------------------------------------------------------

def normalise(skill: str) -> str:
    """Lowercase and strip a skill string for comparison."""
    return skill.strip().lower()


def parse_skills_input(raw: str) -> list[str]:
    """
    Split the user's skill input on commas, newlines, or semicolons.
    Returns a de-duplicated list of stripped, non-empty strings.
    """
    parts = re.split(r"[,\n;]+", raw)
    seen = set()
    result = []
    for p in parts:
        p = p.strip()
        if p and normalise(p) not in seen:
            seen.add(normalise(p))
            result.append(p)
    return result


def analyse_skills(
    user_skills: list[str],
    required: list[str],
    preferred: list[str],
) -> dict:
    """
    Compare user_skills against required and preferred lists.
    Returns a dict with matched, missing_required, missing_preferred,
    match_percentage, and user_skills.
    """
    user_norm = {normalise(s) for s in user_skills}

    matched = [s for s in required if normalise(s) in user_norm]
    matched += [s for s in preferred if normalise(s) in user_norm]
    # de-duplicate while preserving order
    seen = set()
    matched_unique = []
    for s in matched:
        if normalise(s) not in seen:
            seen.add(normalise(s))
            matched_unique.append(s)

    missing_required = [s for s in required if normalise(s) not in user_norm]
    missing_preferred = [s for s in preferred if normalise(s) not in user_norm]

    total_required = len(required)
    pct = round(len([s for s in required if normalise(s) in user_norm]) / total_required * 100) if total_required else 0

    return {
        "matched": matched_unique,
        "missing_required": missing_required,
        "missing_preferred": missing_preferred,
        "match_percentage": pct,
        "user_skills": user_skills,
    }


def extract_skills_from_jd(jd_text: str) -> tuple[list[str], list[str], bool]:
    """
    Ask Gemini to extract required and preferred skills from a job description.
    Falls back to a simple keyword scan if Gemini is unavailable.
    Returns (required, preferred, ai_used).
    """
    prompt = f"""You are a job description parser.
Read the following job description and extract two lists:
1. Required skills (must-have technical skills clearly stated as required or essential)
2. Preferred skills (nice-to-have, bonus, or preferred skills)

Return your answer as valid JSON in exactly this format:
{{"required": ["skill1", "skill2"], "preferred": ["skill3", "skill4"]}}

Only include concrete skills (technologies, tools, languages, frameworks, methods).
Do not include soft skills, years of experience, or degree requirements.

Job description:
---
{jd_text[:4000]}
---"""

    text, success = gemini_generate(prompt)
    if success:
        try:
            # Extract the JSON block from the response
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return data.get("required", []), data.get("preferred", []), True
        except (json.JSONDecodeError, KeyError):
            pass

    # Fallback: look for known skills from all career data
    all_known = set()
    for role_data in CAREER_DATA.values():
        all_known.update(normalise(s) for s in role_data["required"])
        all_known.update(normalise(s) for s in role_data["preferred"])

    jd_lower = jd_text.lower()
    found = [s for s in all_known if s in jd_lower]
    # Return all found as "required" (we can't distinguish without AI)
    return sorted(found), [], False


# ---------------------------------------------------------------------------
# Learning plan / content helpers  (local fallback versions)
# ---------------------------------------------------------------------------

_RESOURCE_HINTS = {
    "python": ["Search: 'Python for beginners freeCodeCamp', 'Automate the Boring Stuff with Python'"],
    "sql": ["Search: 'SQL tutorial W3Schools', 'SQLZoo interactive exercises'"],
    "machine learning": ["Search: 'Andrew Ng Machine Learning Coursera', 'fast.ai practical deep learning'"],
    "deep learning": ["Search: 'fast.ai deep learning for coders', '3Blue1Brown neural networks YouTube'"],
    "javascript": ["Search: 'JavaScript30 Wes Bos', 'freeCodeCamp JavaScript algorithms'"],
    "react": ["Search: 'React official tutorial reactjs.org', 'Scrimba React course'"],
    "html": ["Search: 'HTML & CSS freeCodeCamp', 'MDN Web Docs HTML basics'"],
    "css": ["Search: 'CSS Tricks flexbox guide', 'Kevin Powell CSS YouTube channel'"],
    "git": ["Search: 'Git & GitHub crash course freeCodeCamp', 'Learn Git Branching interactive'"],
    "docker": ["Search: 'Docker getting started docs.docker.com', 'TechWorld with Nana Docker tutorial YouTube'"],
    "tensorflow": ["Search: 'TensorFlow official tutorials tensorflow.org', 'Keras getting started guide'"],
    "pytorch": ["Search: 'PyTorch official 60-minute blitz', 'PyTorch tutorials pytorch.org'"],
    "data visualization": ["Search: 'Matplotlib official tutorials', 'Seaborn gallery seaborn.pydata.org'"],
    "tableau": ["Search: 'Tableau Public free training videos', 'Tableau 101 tutorial'"],
    "power bi": ["Search: 'Microsoft Power BI guided learning docs.microsoft.com', 'Guy in a Cube YouTube channel'"],
    "statistics": ["Search: 'Khan Academy statistics & probability', 'StatQuest with Josh Starmer YouTube'"],
    "excel": ["Search: 'Excel Easy tutorial excel-easy.com', 'ExcelJet tips and tricks'"],
    "pandas": ["Search: 'Pandas getting started pydata.org', '10 minutes to Pandas tutorial'"],
    "numpy": ["Search: 'NumPy official quickstart numpy.org', 'CS231n Python NumPy tutorial'"],
    "scikit-learn": ["Search: 'Scikit-learn official user guide scikit-learn.org'"],
    "apis": ["Search: 'REST API crash course Traversy Media YouTube', 'Postman learning centre'"],
    "model deployment": ["Search: 'Flask ML model deployment tutorial', 'FastAPI ML deployment guide'"],
    "node.js": ["Search: 'Node.js official getting started nodejs.org', 'The Odin Project Node.js path'"],
}

_PRACTICE_CHALLENGES = {
    "python": "Write a script that reads a CSV file and prints the top 5 rows sorted by a chosen column.",
    "sql": "Create a SQLite database with a 'students' table and write queries to filter, sort, and join data.",
    "machine learning": "Train a decision tree classifier on the Iris dataset using scikit-learn and evaluate accuracy.",
    "deep learning": "Build a simple neural network in PyTorch or Keras to classify handwritten digits (MNIST).",
    "javascript": "Build a to-do list in plain JavaScript — add, complete, and delete tasks without a framework.",
    "react": "Create a weather card component in React that accepts city name as a prop and displays mock data.",
    "html": "Mark up a résumé in semantic HTML using header, main, section, ul, and footer elements.",
    "css": "Recreate a simple blog post card layout using CSS flexbox or grid, including a hover effect.",
    "git": "Initialise a repo, make three commits with meaningful messages, create a branch, and merge it.",
    "docker": "Write a Dockerfile for a 'Hello World' Flask app, build the image, and run it in a container.",
    "tensorflow": "Train a simple image classifier on the CIFAR-10 dataset using the Keras Sequential API.",
    "pytorch": "Implement linear regression from scratch in PyTorch using autograd and a training loop.",
    "data visualization": "Create three charts (bar, line, scatter) from a sample dataset using Matplotlib.",
    "tableau": "Connect Tableau Public to a CSV file and build a dashboard with at least two chart types.",
    "power bi": "Import a sample Excel file into Power BI Desktop and create a sales summary dashboard.",
    "statistics": "Calculate mean, median, standard deviation, and a correlation coefficient on a dataset in Python.",
    "excel": "Build a pivot table from a sales dataset and create a bar chart showing monthly revenue.",
    "pandas": "Load a CSV with missing values, fill or drop them, and produce a summary statistics table.",
    "numpy": "Create two 3×3 matrices and perform addition, multiplication, transpose, and eigenvalue decomposition.",
    "scikit-learn": "Apply k-means clustering to the Iris dataset and visualise the clusters with a scatter plot.",
    "apis": "Use the requests library to fetch data from a free public API (e.g. Open-Meteo weather) and print results.",
    "model deployment": "Wrap a trained scikit-learn model in a Flask endpoint that accepts JSON input and returns a prediction.",
    "node.js": "Build a small Express.js server with two routes: one returning JSON data and one serving an HTML page.",
    "r": "Load a dataset in R, produce a summary with summary(), and plot a histogram with ggplot2.",
    "typescript": "Convert a small JavaScript utility function to TypeScript with proper type annotations.",
    "spark": "Use PySpark to load a CSV, filter rows, and compute aggregate statistics.",
    "feature engineering": "Create three new features from a date column (day of week, month, is_weekend) in a Pandas DataFrame.",
    "a/b testing": "Simulate an A/B test in Python: generate two groups, run a t-test, and interpret the p-value.",
    "cloud platforms": "Deploy a Flask 'Hello World' app to a free tier of a cloud provider (e.g. Render or Fly.io).",
    "responsive design": "Build a two-column layout that collapses to single-column on mobile using only CSS media queries.",
    "testing": "Write three unit tests for a Python function using pytest — one for normal input, one for edge case, one for error.",
    "accessibility": "Audit a web page with the Axe browser extension and fix at least three accessibility issues.",
    "vector databases": "Use the chromadb library to store and query five text documents by semantic similarity.",
    "langchain": "Build a simple LangChain chain that takes a question, retrieves context from a text file, and answers it.",
    "prompt engineering": "Write five different prompts for the same task (summarise an article) and compare the outputs.",
    "mlops": "Set up a simple MLflow experiment to log parameters, metrics, and a trained model artefact.",
    "large language models": "Use the Hugging Face transformers library to run a text summarisation pipeline on a news article.",
    "kubernetes": "Write a Kubernetes Deployment YAML for a containerised app and apply it to a local Minikube cluster.",
    "webpack": "Set up a minimal Webpack config that bundles two JavaScript modules and generates a source map.",
    "google analytics": "Add Google Analytics 4 tracking code to a static HTML page and verify an event fires in GA4 DebugView.",
    "business intelligence": "Design a star schema for a retail store: fact table for sales, dimensions for products, dates, and customers.",
    "communication skills": "Prepare a 3-minute presentation explaining a data analysis finding to a non-technical audience.",
    "data pipelines": "Build an ETL pipeline in Python: extract from CSV, transform (clean + enrich), load into SQLite.",
    "data cleaning": "Find and fix five types of data quality issues (nulls, duplicates, wrong types, outliers, inconsistent strings) in a messy CSV.",
    "nlp": "Use the NLTK or spaCy library to tokenise text, remove stop words, and identify named entities.",
    "natural language processing": "Use the NLTK or spaCy library to tokenise text, remove stop words, and identify named entities.",
    "fastapi": "Create a FastAPI app with two endpoints: one GET returning a list and one POST accepting JSON input.",
    "docker": "Write a Dockerfile for a Flask app, build the image, and run it mapping port 5000.",
}

_DEFAULT_CHALLENGE = "Find a beginner tutorial for {skill} on YouTube or freeCodeCamp and complete the first project exercise."


def get_challenge(skill: str) -> str:
    return _PRACTICE_CHALLENGES.get(normalise(skill), _DEFAULT_CHALLENGE.format(skill=skill))


def get_resource_hint(skill: str) -> str:
    hints = _RESOURCE_HINTS.get(normalise(skill))
    if hints:
        return hints[0]
    return f"Search: '{skill} tutorial for beginners' on YouTube, freeCodeCamp, or Coursera"


def build_local_learning_plan(missing: list[str], hours_per_week: int) -> list[dict]:
    """
    Build a simple week-by-week learning plan without AI.
    Estimates roughly 5 hours per skill to get started.
    """
    if not missing:
        return []

    hours_per_skill = 5
    plan = []
    current_week = 1
    hours_used = 0

    for skill in missing:
        if hours_used + hours_per_skill > hours_per_week:
            current_week += 1
            hours_used = 0
        plan.append({
            "week": current_week,
            "skill": skill,
            "action": f"Learn the fundamentals of {skill}.",
            "resource": get_resource_hint(skill),
            "hours": hours_per_skill,
        })
        hours_used += hours_per_skill

    return plan


def build_local_portfolio_idea(role: str, missing: list[str]) -> str:
    top_gaps = missing[:3] if missing else ["your strongest skills"]
    gap_str = ", ".join(top_gaps)
    return (
        f"Build a '{role} Showcase' project that demonstrates {gap_str}. "
        "For example, find a publicly available dataset related to a topic you care about, "
        "apply the techniques you are learning, and publish your code on GitHub with a clear README "
        "explaining your process and findings. This gives recruiters concrete evidence of your skills."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Home page."""
    return render_template("index.html", supported_roles=SUPPORTED_ROLES)


@app.route("/assess")
def assess():
    """Assessment form."""
    return render_template("assess.html", supported_roles=SUPPORTED_ROLES)


@app.route("/analyse", methods=["POST"])
def analyse():
    """Process the assessment form and render results."""
    target_role = request.form.get("target_role", "").strip()
    skills_raw = request.form.get("current_skills", "").strip()
    job_description = request.form.get("job_description", "").strip()
    hours_str = request.form.get("hours_per_week", "10").strip()

    # Basic validation
    if not target_role or not skills_raw:
        return redirect(url_for("assess"))

    try:
        hours_per_week = max(1, min(int(hours_str), 80))
    except ValueError:
        hours_per_week = 10

    user_skills = parse_skills_input(skills_raw)

    # --- Determine required / preferred skills ---
    ai_used_for_jd = False
    analysis_source = ""

    if job_description:
        required, preferred, ai_used_for_jd = extract_skills_from_jd(job_description)
        analysis_source = "job description (AI-parsed)" if ai_used_for_jd else "job description (keyword scan)"
    elif target_role in CAREER_DATA:
        required = CAREER_DATA[target_role]["required"]
        preferred = CAREER_DATA[target_role]["preferred"]
        analysis_source = "built-in career profile"
    else:
        # Unknown role with no JD — do best-effort with an empty required list
        required = []
        preferred = []
        analysis_source = "no profile available"

    skill_data = analyse_skills(user_skills, required, preferred)
    gaps = skill_data["missing_required"]

    # --- Learning plan ---
    learning_plan_text = None
    ai_plan = False
    local_plan = []

    if gaps:
        gap_list = ", ".join(gaps)
        plan_prompt = f"""You are a helpful career coach for students.

A student wants to become a {target_role}.
Their missing required skills are: {gap_list}.
They have {hours_per_week} hours per week available to study.

Write a SHORT week-by-week learning plan that closes exactly these skill gaps.
Rules:
- Focus on ONE skill per week only.
- Give ONE concrete, achievable action for that week (e.g. "Complete the first two modules of …").
- Give ONE free resource as a search query (never invent a URL — search terms only).
- Each week entry must fit inside {hours_per_week} hours of study time.
- Cover every missing skill; merge closely related skills into one week if needed.
- Keep the tone encouraging and accessible to a beginner.

Format each week exactly like this (use plain text headings with the word "Week"):

Week 1 — [Skill Name]
Action: [one sentence describing what to do]
Resource: Search for "[search terms]"

Week 2 — [Skill Name]
Action: [one sentence]
Resource: Search for "[search terms]"

(continue for all skills)

Do not add any introduction or closing paragraph — output only the week entries."""

        learning_plan_text, ai_plan = gemini_generate(plan_prompt)
        if not ai_plan:
            local_plan = build_local_learning_plan(gaps, hours_per_week)

    # --- Practice challenges ---
    challenges = [{"skill": s, "challenge": get_challenge(s)} for s in gaps]

    # --- Portfolio idea ---
    portfolio_text = None
    ai_portfolio = False

    if gaps:
        portfolio_prompt = f"""You are a career coach helping a beginner student build a portfolio.
The student wants to become a {target_role}.
Their missing skills are: {', '.join(gaps[:5])}.

Suggest exactly ONE small, beginner-friendly portfolio project that:
- Can realistically be completed in 1–2 weeks of part-time work.
- Uses only free tools (e.g. Python, Google Colab, VS Code, GitHub).
- Uses a freely available public dataset (e.g. from Kaggle, data.gov, or UCI ML Repository).
- Practices at least two of the student's missing skills listed above.
- Is specific and concrete — not vague or overly ambitious.

Structure your answer with these exact plain-text headings (no Markdown bold or asterisks):

Project Name: [a short memorable name]

Purpose: [one sentence — what the project does and why it matters]

Steps:
1. [first concrete step]
2. [second concrete step]
3. [third concrete step]
4. [optional fourth step]
5. [optional fifth step]

Final Deliverable: [one sentence describing what the student publishes, e.g. a GitHub repo with a README and a chart]

Keep every step short and actionable. Do not suggest anything requiring paid tools, large teams, or more than two weeks of work."""

        portfolio_text, ai_portfolio = gemini_generate(portfolio_prompt)
        if not ai_portfolio:
            portfolio_text = build_local_portfolio_idea(target_role, gaps)

    # --- Role description ---
    role_description = ""
    if target_role in CAREER_DATA:
        role_description = CAREER_DATA[target_role].get("description", "")

    return render_template(
        "results.html",
        target_role=target_role,
        analysis_source=analysis_source,
        skill_data=skill_data,
        required=required,
        preferred=preferred,
        hours_per_week=hours_per_week,
        learning_plan_text=learning_plan_text,
        local_plan=local_plan,
        ai_plan=ai_plan,
        challenges=challenges,
        portfolio_text=portfolio_text,
        ai_portfolio=ai_portfolio,
        role_description=role_description,
        gaps=gaps,
        gemini_available=bool(GEMINI_API_KEY),
    )


@app.route("/chat", methods=["POST"])
def chat():
    """
    AI career mentor endpoint.
    Expects JSON: {role, gaps, message, roadmap_context}
    Returns JSON: {reply, success}
    """
    data = request.get_json(silent=True) or {}
    role = data.get("role", "unknown role")
    gaps = data.get("gaps", [])
    message = data.get("message", "").strip()
    roadmap_context = data.get("roadmap_context", "")

    if not message:
        return jsonify({"reply": "Please enter a question.", "success": False})

    gaps_str = ", ".join(gaps) if gaps else "none identified"
    roadmap_str = f"\n\nRoadmap progress:\n{roadmap_context}" if roadmap_context else ""

    prompt = f"""You are an encouraging AI career mentor helping a student who wants to become a {role}.
Their current skill gaps are: {gaps_str}.{roadmap_str}

The student asks: {message}

Give a helpful, practical, and encouraging reply in 3–5 sentences.
Focus on actionable advice. If you mention resources, give search queries, not URLs."""

    reply, success = gemini_generate(prompt)
    return jsonify({"reply": reply, "success": success})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
