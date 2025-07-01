import streamlit as st
import requests
import pandas as pd
import gspread
from openai import OpenAI
from google.oauth2.service_account import Credentials

# === 🔐 Load from secrets ===
GOOGLE_API_KEY = st.secrets["google"]["api_key"]
GOOGLE_CX = st.secrets["google"]["search_engine_id"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
GOOGLE_SHEET_NAME = st.secrets["google"]["sheet_name"]
GCP_SERVICE_ACCOUNT = st.secrets["gcp_service_account"]

# === 🤖 OpenAI Client ===
client = OpenAI(api_key=OPENAI_API_KEY)

# === Trusted Medical Sources ===
TRUSTED_SITES = [
    "site:nhs.uk", "site:nih.gov", "site:mayoclinic.org", "site:who.int",
    "site:cdc.gov", "site:clevelandclinic.org", "site:health.harvard.edu",
    "site:pubmed.ncbi.nlm.nih.gov", "site:webmd.com", "site:medlineplus.gov"
]

# === Google Search Function ===
def get_medical_snippets(query, num_results=5):
    domain_query = " OR ".join(TRUSTED_SITES)
    full_query = f"{query} ({domain_query})"
    params = {"key": GOOGLE_API_KEY, "cx": GOOGLE_CX, "q": full_query, "num": num_results}
    try:
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params)
        response.raise_for_status()
        items = response.json().get("items", [])
        items.sort(key=lambda x: 0 if "nhs.uk" in x.get("link", "") else 1)
        return [(item["title"], item["link"], item["snippet"]) for item in items]
    except Exception:
        return []

# === ChatGPT Answering Function ===
def answer_medical_question(question):
    snippets = get_medical_snippets(question)
    if not snippets:
        return "Sorry, no reliable sources available now.", []
    context = "\n".join(f"- **{title}**: {snippet}" for title, link, snippet in snippets)
    sources = [(title, link) for title, link, snippet in snippets]
    prompt = f"""
Answer clearly using snippets below.
Mention both common and serious conditions if symptoms provided.
End with: "Talk to a doctor to be sure."

Snippets:
{context}

Question: {question}

Answer:
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        answer = response.choices[0].message.content.strip()
        return answer + "\n\n**Disclaimer:** Always consult your healthcare provider.", sources
    except Exception as e:
        return f"OpenAI API Error: {e}", []

# === Expanded Proactive Risk Advisories ===
RISK_SNIPPETS = {
    "antibiotics": "Misuse of antibiotics can cause antibiotic resistance.",
    "vaccines": "Vaccines do not cause autism; extensive research confirms safety.",
    "ibuprofen": "Long-term/high-dose ibuprofen may harm kidneys or cause stomach bleeding.",
    "detox": "Your body naturally detoxifies; external detox methods may be harmful.",
    "fatigue": "Persistent fatigue might indicate underlying health issues.",
    "vision loss": "Sudden vision loss is a medical emergency—seek immediate help.",
    "headache": "Sudden severe headache could signal stroke or aneurysm—seek immediate care.",
    "chest pain": "Chest pain may indicate a heart attack—seek immediate medical help.",
    "rash": "Rashes with fever or breathing issues may be serious—seek urgent care."
}

def get_risk_snippets(query):
    return [snippet for keyword, snippet in RISK_SNIPPETS.items() if keyword in query.lower()]

# === Severity Indicators ===
SEVERITY_KEYWORDS = {
    "🔴 Immediate": ["chest pain", "vision loss", "stroke", "aneurysm", "sudden severe headache"],
    "🟠 Urgent": ["high fever", "severe pain", "persistent vomiting", "unusual rash", "dizziness"],
    "🟢 Routine": []
}

def classify_severity(query):
    q_lower = query.lower()
    for severity, keywords in SEVERITY_KEYWORDS.items():
        if any(keyword in q_lower for keyword in keywords):
            return severity
    return "🟢 Routine"

# === Streamlit UI ===
st.set_page_config(page_title="AI Medical Assistant", page_icon="🩺", layout="centered")
st.title("🩺 AI-Powered Medical Assistant")

user_age = st.sidebar.text_input("Your Age (optional)")
user_gender = st.sidebar.selectbox("Your Gender (optional)", ["Prefer not to say", "Male", "Female", "Other"])

tab1, tab2 = st.tabs(["🧠 Ask Question", "📜 History"])

if "history" not in st.session_state:
    st.session_state.history = []

with tab1:
    question = st.text_input("Enter your medical question:")
    if st.button("Get Answer") and question:
        demographics = f"For a {user_age}-year-old {user_gender.lower()}, " if user_age or user_gender != "Prefer not to say" else ""
        full_query = demographics + question
        with st.spinner("Generating response..."):
            answer, sources = answer_medical_question(full_query)
            risk_advisories = get_risk_snippets(question)
            severity = classify_severity(question)

        st.markdown(f"### 🚨 Severity Level: {severity}")
        st.markdown("### ✅ Answer")
        st.write(answer)

        if risk_advisories:
            st.markdown("### ⚠️ Proactive Health Advisory")
            for advisory in risk_advisories:
                st.warning(advisory)

        if sources:
            st.markdown("### 📚 Sources")
            for title, link in sources:
                st.markdown(f"- [{title}]({link})")

        st.session_state.history.append({
            "Question": question, "Answer": answer, "Sources": sources, "Severity": severity
        })

with tab2:
    st.markdown("### 📜 Session History")
    if not st.session_state.history:
        st.info("No questions asked yet.")
    else:
        for i, entry in enumerate(reversed(st.session_state.history), 1):
            st.markdown(f"**Q{i}: {entry['Question']}** ({entry['Severity']})")
            st.write(entry['Answer'])
            st.markdown("---")

# === Feedback Form (restored) ===
st.markdown("---")
st.markdown("### 💬 Leave Feedback")

creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=[
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
])
gc = gspread.authorize(creds)
feedback_sheet = gc.open(GOOGLE_SHEET_NAME).sheet1

with st.form("feedback_form"):
    st.markdown("*(Optional)* Rate your experience and provide feedback.")
    rating = st.radio("Rate your experience:", ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"], index=4, horizontal=True)
    comments = st.text_area("Your Feedback")
    if st.form_submit_button("Submit Feedback"):
        feedback_sheet.append_row([rating, comments])
        st.success("✅ Thank you for your feedback!")

# === Footer ===
st.markdown("---")
st.caption("Developed by Doaa Al-Turkey")
