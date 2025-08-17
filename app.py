import os
import re
import json
import uuid
import time
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError
import google.generativeai as genai

# =========================
# Environment & API Setup
# =========================
load_dotenv()

if not os.environ.get("GEMINI_API_KEY"):
    st.set_page_config(page_title="Gemini Researcher Agent", page_icon="📰")
    st.error("Please set your GEMINI_API_KEY environment variable in .env")
    st.stop()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# =========================
# Streamlit Page Config
# =========================
st.set_page_config(
    page_title="Gemini Researcher Agent",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================
# Session State (init first)
# =========================
defaults = {
    "conversation_id": str(uuid.uuid4().hex[:16]),
    "collected_facts": [],
    "research_done": False,
    "report_result": None,
    "critique_result": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =========================
# Header
# =========================
st.title("📰 Gemini Researcher Agent")
st.subheader("Powered by Google Gemini (Multi-Agent)")
st.markdown(
    """
This app demonstrates a **multi-agent architecture** using **Google Gemini**:

- 🔧 **Triage Agent**: Creates a research plan  
- 🔎 **Research Agent**: Gathers concise findings  
- ✍️ **Editor Agent**: Writes a long, structured report  
- 🧪 **Critic Agent**: Reviews the report and suggests improvements
"""
)

# =========================
# Data Models
# =========================
class ResearchPlan(BaseModel):
    topic: str
    search_queries: list[str]
    focus_areas: list[str]

class ResearchReport(BaseModel):
    title: str
    outline: list[str]
    report: str
    sources: list[str]
    word_count: int

# =========================
# Helpers
# =========================
def extract_json(text: str) -> str | None:
    """
    Try to extract a JSON object from a freeform LLM response.
    Handles code fences and extra text.
    """
    if not text:
        return None
    # Try code-fence first
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        return fence.group(1)
    # Try first {...} block
    brace = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if brace:
        return brace.group(1)
    return None

def safe_json_parse(plan_text: str, fallback: dict) -> dict:
    payload = extract_json(plan_text) or plan_text
    try:
        return json.loads(payload)
    except Exception:
        return fallback

# =========================
# Gemini Agent Wrapper
# =========================
class GeminiAgent:
    def __init__(self, name: str, instructions: str, model: str = "gemini-2.5-flash"):
        self.name = name
        self.instructions = instructions
        self.model_name = model
        self.client = genai.GenerativeModel(self.model_name)

    def run(self, prompt: str) -> str:
        """Generate content using Gemini; minimal retry on transient errors."""
        full_prompt = f"{self.instructions}\n\nUser query / task:\n{prompt}"
        for attempt in range(3):
            try:
                resp = self.client.generate_content(full_prompt)
                text = getattr(resp, "text", None)
                return text if text else "No response."
            except Exception as e:
                # naive backoff for rate limits/transient failures
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return f"⚠️ Error from {self.name}: {e}"

# =========================
# Agents
# =========================
triage_agent = GeminiAgent(
    name="Triage Agent",
    instructions=(
        "You are the coordinator. Given a topic, produce a research plan as pure JSON only.\n"
        "Keys: topic (string), search_queries (3-5 items), focus_areas (3-5 items).\n"
        "Do not add commentary outside JSON."
    ),
    model="gemini-2.5-flash",
)

research_agent = GeminiAgent(
    name="Research Agent",
    instructions=(
        "You are a research assistant. Summarize findings in 2-3 short paragraphs, "
        "under 300 words. Focus on crisp facts, key points, and useful takeaways. "
        "No fluff. Include bulleted lists if helpful."
    ),
    model="gemini-2.5-flash",
)

editor_agent = GeminiAgent(
    name="Editor Agent",
    instructions=(
        "You are a senior researcher. Using the notes, write a comprehensive markdown report "
        "(>= 1000 words, target ~5-10 pages). Include:\n"
        "- A clear title\n- An outline of sections\n- Well-structured headings\n"
        "- Evidence-backed points\n- A 'Sources' section at the end"
    ),
    model="gemini-2.5-flash",
)

critic_agent = GeminiAgent(
    name="Critic Agent",
    instructions=(
        "You are a critical reviewer. Review the provided report for clarity, structure, depth, "
        "coverage, and factual balance. Suggest improvements and highlight missing points "
        "in <= 400 words. Return feedback in markdown with bullet points."
    ),
    model="gemini-2.5-flash",
)

# =========================
# Sidebar Inputs
# =========================
with st.sidebar:
    st.header("Research Topic")
    user_topic = st.text_input("Enter a topic to research:")
    start_button = st.button("Start Research", type="primary", disabled=not user_topic)

    st.divider()
    st.subheader("Examples")
    ex_topics = [
        "What are the best businesses for young generation in India to start and earn?",
        "Best affordable shops in Agra for a 10 lakh budget?",
        "Best off-the-beaten-path destinations in India for first-time solo travelers?",
    ]
    for t in ex_topics:
        if st.button(t):
            user_topic = t
            start_button = True

    st.divider()
    if st.button("🗑️ Clear Session"):
        for k in list(st.session_state.keys()):
            if k in defaults:
                st.session_state[k] = defaults[k]
        st.success("Session cleared.")

# =========================
# Tabs
# =========================
tab_process, tab_report = st.tabs(["Research Process", "Report"])

# =========================
# Workflow
# =========================
def run_research(topic: str):
    st.session_state.collected_facts = []
    st.session_state.research_done = False
    st.session_state.report_result = None
    st.session_state.critique_result = None

    with tab_process:
        box = st.container()

    # 1) Triage -> Research Plan
    with tab_process:
        box.write("🔧 **Triage Agent**: Creating research plan...")
    triage_raw = triage_agent.run(f"Topic: {topic}\nReturn JSON only.")
    fallback_plan = {"topic": topic, "search_queries": [topic], "focus_areas": ["General overview"]}
    plan_dict = safe_json_parse(triage_raw, fallback=fallback_plan)

    try:
        plan = ResearchPlan(**plan_dict)
    except ValidationError:
        plan = ResearchPlan(**fallback_plan)

    with tab_process:
        st.write("📋 **Research Plan**")
        st.json(plan.dict())

    # 2) Research Agent -> Notes
    with tab_process:
        box.write("🔎 **Research Agent**: Gathering concise findings...")
    notes_prompt = (
        f"Topic: {plan.topic}\n"
        f"Search Queries: {plan.search_queries}\n"
        f"Focus Areas: {plan.focus_areas}\n"
        "Provide concise findings."
    )
    research_notes = research_agent.run(notes_prompt)

    # Store as a single 'fact' entry; you can split later if you want finer granularity
    st.session_state.collected_facts.append({
        "fact": research_notes,
        "source": "Gemini (summarized findings)",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    })

    with tab_process:
        st.write("📚 **Collected Findings**")
        for i, f in enumerate(st.session_state.collected_facts, 1):
            st.info(f"**{i}.** {f['fact']}\n\n**Source:** {f['source']}  \n*{f['timestamp']}*")

    # 3) Editor Agent -> Long Report
    with tab_process:
        box.write("✍️ **Editor Agent**: Drafting the comprehensive report...")
    editor_prompt = (
        f"Topic: {plan.topic}\n\nResearch Notes:\n{research_notes}\n\n"
        "Write the full report now."
    )
    report_text = editor_agent.run(editor_prompt)
    st.session_state.report_result = report_text

    # 4) Critic Agent -> Review
    with tab_process:
        box.write("🧪 **Critic Agent**: Reviewing the report for improvements...")
    critique_text = critic_agent.run(report_text)
    st.session_state.critique_result = critique_text

    st.session_state.research_done = True

    with tab_process:
        st.success("✅ Research complete! Draft & review ready.")
        st.markdown(report_text[:600] + "\n\n*…Open the **Report** tab for the full document and critique.*")

# Trigger
if start_button and user_topic:
    with st.spinner(f"Working on: {user_topic}"):
        run_research(user_topic)

# =========================
# Report Tab Rendering
# =========================
with tab_report:
    if st.session_state.get("research_done") and st.session_state.get("report_result"):
        title_text = (user_topic or "Report").title()
        st.title(title_text)

        # Full report
        st.markdown(st.session_state["report_result"])

        # Critic review
        if st.session_state.get("critique_result"):
            st.subheader("🧪 Critic Agent Review")
            st.markdown(st.session_state["critique_result"])

        # Downloads
        st.download_button(
            label="⬇️ Download Report (.md)",
            data=st.session_state["report_result"],
            file_name=f"{title_text.replace(' ', '_')}.md",
            mime="text/markdown",
        )
        if st.session_state.get("critique_result"):
            st.download_button(
                label="⬇️ Download Critique (.md)",
                data=st.session_state["critique_result"],
                file_name=f"{title_text.replace(' ', '_')}_Critique.md",
                mime="text/markdown",
            )
    else:
        st.info("Run research from the **Research Process** tab to see the full report and critique here.")
