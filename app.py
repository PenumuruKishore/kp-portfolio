import streamlit as st

st.set_page_config(page_title="Kishore's AI Project Portfolio", layout="centered")

st.title("👨‍💻 Kishore Penumuru – AI Project Portfolio")
st.markdown("Welcome! Explore some of my recent projects in healthcare and finance using Generative AI.")

st.divider()

# Project 1: Medical AI Notes
st.subheader("🩺 Medical AI Notes")
st.markdown("""
**Summary:** Converts doctor-patient audio conversations into structured medical notes.  
- Uses AssemblyAI for transcription  
- Summarizes with Groq's LLaMA 3 model  
- Built with Streamlit  
""")
st.markdown("[🔗 Launch App](https://mednote-ai.streamlit.app/)")

st.divider()

# Project 2: Financial Planner
st.subheader("📈 Financial Planner for Indian Senior Citizens")
st.markdown("""
**Summary:** Interactive tool that helps Indian retirees and senior citizens plan monthly income using post-retirement investments.  
- Uses visual inputs and scenario modeling  
- Built with Streamlit  
""")
st.markdown("[🔗 Launch App](https://lnkd.in/gsi3ukkk)")

st.divider()

st.markdown("📫 [LinkedIn](https://www.linkedin.com/in/kishorepenumuru) | [GitHub](https://github.com/PenumuruKishore)")
