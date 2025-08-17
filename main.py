import os
import uuid
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Configure Gemini API
if not os.environ.get("GEMINI_API_KEY"):
    st.error("Please set your GEMINI_API_KEY environment variable in .env")
    st.stop()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Streamlit Page Config
st.set_page_config(
    page_title="Gemini Researcher Agent",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🔹 Always initialize session state FIRST
defaults = {
    "conversation_id": str(uuid.uuid4().hex[:16]),
    "collected_facts": [],
    "research_done": False,
    "report_result": None,
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# Title
st.title("📰 Gemini Researcher Agent")
st.subheader("Powered by Google Gemini")
st.markdown("""
This app demonstrates the power of **Gemini AI** by creating a multi-agent system 
that researches topics and generates comprehensive reports.
""")

# ---------- Data Models ----------
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


# ---------- Utility: Gemini Wrapper ----------
class GeminiAgent:
    def __init__(self, name, instructions, model="gemini-2.5-flash"):
        self.name = name
        self.instructions = instructions
        self.model_name = model
        self.client = genai.GenerativeModel(model)

    def run(self, prompt: str):
        """Generate content using Gemini."""
        full_prompt = f"{self.instructions}\n\nUser query:\n{prompt}"
        response = self.client.generate_content(full_prompt)
        return response.text if response and response.text else "No response."


# ---------- Custom Tool for Saving Facts ----------
def save_important_fact(fact: str, source: str = None) -> str:
    """Save an important fact during research."""
    st.session_state.collected_facts.append({
        "fact": fact,
        "source": source or "Not specified",
        "timestamp": datetime.now().strftime("%H:%M:%S")
    })
    return f"Fact saved: {fact}"


# ---------- Define Agents ----------
research_agent = GeminiAgent(
    name="Research Agent",
    instructions="You are a research assistant. Search the web mentally and summarize findings in 2-3 paragraphs under 300 words. Focus only on core facts, skip fluff.",
    model="gemini-2.5-flash"
)

editor_agent = GeminiAgent(
    name="Editor Agent",
    instructions="You are a senior researcher. Write a comprehensive research report (1000+ words, markdown format, 5-10 pages). Include an outline, detailed content, and sources.",
    model="gemini-2.5-flash"
)

triage_agent = GeminiAgent(
    name="Triage Agent",
    instructions="""You are the coordinator. Given a topic:
1. Create a research plan with:
   - topic: clear statement
   - search_queries: 3-5 search queries
   - focus_areas: 3-5 key aspects
Return structured JSON with {topic, search_queries, focus_areas}.
""",
    model="gemini-2.5-flash"
)

# ---------- Sidebar Input ----------
with st.sidebar:
    st.header("Research Topic")
    user_topic = st.text_input("Enter a topic to research:")
    start_button = st.button("Start Research", type="primary", disabled=not user_topic)

    st.divider()
    st.subheader("Example Topics")
    example_topics = [
        "What are the best businesses for young generation in India to start and earn?",
        "Best affordable shops in Agra for a 10 lakh budget?",
        "Best off-the-beaten-path destinations in India for first-time solo travelers?"
    ]
    for topic in example_topics:
        if st.button(topic):
            user_topic = topic
            start_button = True

# Tabs
tab1, tab2 = st.tabs(["Research Process", "Report"])


# ---------- Main Research Workflow ----------
def run_research(topic):
    st.session_state.collected_facts = []
    st.session_state.research_done = False
    st.session_state.report_result = None

    with tab1:
        message_container = st.container()

    # Step 1: Triage Agent → Research Plan
    with message_container:
        st.write("🔍 **Triage Agent**: Planning research approach...")

    triage_output = triage_agent.run(f"Research this topic thoroughly: {topic}")
    try:
        plan_data = eval(triage_output) if triage_output.strip().startswith("{") else {
            "topic": topic,
            "search_queries": [topic],
            "focus_areas": ["General overview"]
        }
        research_plan = ResearchPlan(**plan_data)
    except Exception:
        research_plan = ResearchPlan(
            topic=topic,
            search_queries=[topic],
            focus_areas=["General overview"]
        )

    with message_container:
        st.write("📋 **Research Plan**:")
        st.json(research_plan.dict())

    # Step 2: Research Agent
    with message_container:
        st.write("📚 **Research Agent**: Collecting facts...")
    research_notes = research_agent.run(
        f"Topic: {research_plan.topic}\nQueries: {research_plan.search_queries}\nFocus Areas: {research_plan.focus_areas}"
    )
    save_important_fact(research_notes, "Gemini Research")

    with message_container:
        for fact in st.session_state.collected_facts:
            st.info(f"**Fact**: {fact['fact']}\n\n**Source**: {fact['source']}")

    # Step 3: Editor Agent → Report
    with message_container:
        st.write("📝 **Editor Agent**: Creating research report...")
    report_text = editor_agent.run(f"Topic: {topic}\nResearch Notes:\n{research_notes}")

    st.session_state.report_result = report_text
    st.session_state.research_done = True

    with message_container:
        st.write("✅ **Research Complete! Report Generated.**")
        st.markdown(report_text[:500] + "...\n\n*See Report tab for full content.*")


# ---------- Run Research ----------
if start_button:
    with st.spinner(f"Researching: {user_topic}"):
        try:
            run_research(user_topic)
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.session_state.report_result = f"# Research on {user_topic}\n\nError: {str(e)}"
            st.session_state.research_done = True

# ---------- Show Report ----------
with tab2:
    if st.session_state.get("research_done") and st.session_state.get("report_result"):
        report_content = st.session_state.report_result
        st.title(user_topic.title())
        st.markdown(report_content)

        st.download_button(
            label="Download Report",
            data=report_content,
            file_name=f"{user_topic.replace(' ', '_')}.md",
            mime="text/markdown"
        )
