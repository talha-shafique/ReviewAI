import os
import json
import streamlit as st
from mistralai.client import MistralClient
from dotenv import load_dotenv
import time
import statistics
import re
import pandas as pd
from scraper import JashanmalScraper
from genai_analysis import analyze_reviews_with_genai
import urllib3
import ssl
import certifi
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create a custom SSL context
ssl_context = ssl.create_default_context(cafile=certifi.where())
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Load environment variables from .env file if present
load_dotenv()

st.set_page_config(
    page_title="ReviewAI",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Add some spacing
st.markdown("""
    <style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    /* Increase text size */
    .stMarkdown {
        font-size: 1.4rem !important;
    }
    .stMarkdown p {
        font-size: 1.25rem !important;
    }
    .stMarkdown h1 {
        font-size: 3rem !important;
    }
    .stMarkdown h2 {
        font-size: 2.5rem !important;
    }
    .stMarkdown h3 {
        font-size: 2rem !important;
    }
    .stMarkdown h4 {
        font-size: 1.8rem !important;
    }
    /* Make review text and summaries larger */
    .stExpander {
        font-size: 1.4rem !important;
    }
    .stExpanderHeader {
        font-size: 1.25rem !important;
    }
    .stExpander .stMarkdown {
        font-size: 1.4rem !important;
    }
    .stExpanderContent {
        font-size: 1.25rem !important;
    }
    .stExpanderContent .stMarkdown p {
        font-size: 1.25rem !important;
    }
    /* Make input fields and buttons larger */
    .stTextInput > div > div > input {
        font-size: 1.4rem !important;
    }
    .stButton > button {
        font-size: 1.4rem !important;
        padding: 0.5rem 1rem;
    }
    /* Increase spacing between elements */
    .element-container {
        margin-bottom: 1.5rem;
    }
    /* Center align the title and icon */
    .title-container {
        text-align: center;
        margin-bottom: 2rem;
    }
    .title-container img {
        margin-bottom: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

# Display centered icon and title
st.markdown("""
    <div class="title-container">
        <img width="100" height="100" src="https://img.icons8.com/external-tal-revivo-green-tal-revivo/100/external-laptop-connected-with-a-brain-isolated-on-a-white-background-artificial-green-tal-revivo.png" alt="ReviewAI Logo"/>
        <h1>ReviewAI</h1>
    </div>
""", unsafe_allow_html=True)

# Get API key from environment variable or .env file
api_key = os.environ.get("MISTRAL_API_KEY")
if not api_key:
    st.error("Please set the MISTRAL_API_KEY environment variable in your system or in a .env file.")
    st.stop()

model = "mistral-large-latest"
client = MistralClient(api_key=api_key)

# Initialize scraper with SSL context
scraper = JashanmalScraper(verify_ssl=False)

# --- Helper to parse markdown table to DataFrame ---
def parse_markdown_table(md_table):
    lines = [line.strip() for line in md_table.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith('|') and line.endswith('|')]
    if len(table_lines) < 2:
        return None
    header = [h.strip() for h in table_lines[0].strip('|').split('|')]
    rows = []
    for line in table_lines[2:]:
        row = [c.strip() for c in line.strip('|').split('|')]
        if len(row) == len(header):
            rows.append(row)
    if not rows:
        return None
    return pd.DataFrame(rows, columns=header)

# --- UI ---
url = st.text_input("Product Reviews URL", "")

if 'scraped_reviews' not in st.session_state:
    st.session_state['scraped_reviews'] = None
if 'genai_output' not in st.session_state:
    st.session_state['genai_output'] = None
if 'gallery_items' not in st.session_state:
    st.session_state['gallery_items'] = None
if 'verdict' not in st.session_state:
    st.session_state['verdict'] = None
if 'summary' not in st.session_state:
    st.session_state['summary'] = None

if st.button("Analyze Product Reviews"):
    if not url.strip():
        st.warning("Please enter a valid product reviews URL.")
        st.stop()
    step = st.empty()
    progress = st.progress(0, text="Starting Reading...")
    status = st.empty()
    
    step.info("Step 1: Reading reviews...")
    spinner = st.empty()
    with spinner:
        st.spinner("Reading reviews from the product page...")
        try:
            reviews = scraper.scrape_reviews(url)
            st.session_state['scraped_reviews'] = reviews
            
            # Save reviews to review.json, overwriting any existing file
            with open('review.json', 'w', encoding='utf-8') as f:
                json.dump(reviews, f, ensure_ascii=False, indent=2)
                
            progress.progress(1.0, text="Reading complete!")
            status.success(f"Read {len(reviews)} reviews in total.")
            step.success("Step 1: Reviews read successfully!")

            # Clear the spinner
            spinner.empty()

            # Check if no reviews were found after showing completion
            if not reviews:
                st.markdown("""
                <div style='background-color:#e9ecef;padding:20px;border-radius:10px;color:#000000;margin:20px 0;'>
                    <h2 style='margin-bottom:0.2em;color:#000000 !important;'>⚠️ No Reviews Available</h2>
                    <p style='margin:0;color:#000000;'>No reviews were found for this product. We cannot provide a recommendation at this time.</p>
                </div>
                """, unsafe_allow_html=True)
                st.stop()
        except Exception as e:
            st.error(f"Error reading reviews: {str(e)}")
            st.stop()

    # --- GenAI analysis ---
    step.info("Step 2: Analyzing reviews with GenAI...")
    progress2 = st.progress(0, text="Starting GenAI analysis...")
    
    try:
        total_reviews = len(reviews)
        for i in range(total_reviews):
            progress2.progress((i+1)/total_reviews, text=f"Analyzing review {i+1} of {total_reviews}")
            time.sleep(0.1)  # Small delay to show progress
            
        with st.spinner("Analyzing reviews with Mistral GenAI..."):
            genai_output, sentiments = analyze_reviews_with_genai(reviews, model, client)
            
            # Check if analysis was incomplete due to rate limits
            if "Analysis incomplete due to API rate limits" in genai_output:
                st.warning("⚠️ Analysis was incomplete due to API rate limits. Some reviews may not be fully analyzed.")
                
                # Try to load progress from temporary file
                try:
                    with open('review_analysis_progress.json', 'r', encoding='utf-8') as f:
                        reviews = json.load(f)
                        st.info("✓ Loaded partially analyzed reviews from progress file.")
                except:
                    st.error("Could not load progress file. Please try again later.")
                    st.stop()
            
        progress2.progress(1.0, text="GenAI analysis complete!")
        step.success("Step 2: Analysis complete!")
        st.session_state['genai_output'] = genai_output
        st.session_state['sentiments'] = sentiments
        
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        st.warning("Please try again with fewer reviews or wait a few minutes before retrying.")
        st.stop()

    # --- Parse GenAI output ---
    output_lines = genai_output.splitlines()
    confidence = ''
    checklist = {}
    details = {}
    images_analysis = ''
    verdict = ''
    verdict_reason = ''
    section = None
    for line in output_lines:
        line = line.strip()
        if line.lower().startswith('confidence score:'):
            confidence = line.split(':',1)[-1].strip()
            section = None
        elif line.lower().startswith('checklist:'):
            section = 'checklist'
        elif line.lower().startswith('expandable details:'):
            section = 'details'
        elif line.lower().startswith('customer images analysis:'):
            section = 'images'
        elif line.lower().startswith('final verdict:'):
            section = 'verdict'
        elif section == 'checklist' and line.startswith('-') and ':' in line:
            k, v = line[1:].split(':',1)
            checklist[k.strip()] = v.strip()
        elif section == 'details' and line.startswith('-') and ':' in line:
            k, v = line[1:].split(':',1)
            details[k.strip()] = v.strip()
        elif section == 'images' and line:
            images_analysis += line + '\n'
        elif section == 'verdict' and not verdict:
            verdict = line
        elif section == 'verdict' and verdict and not verdict_reason and line:
            verdict_reason = line
    st.session_state['verdict'] = verdict
    st.session_state['confidence'] = confidence
    st.session_state['checklist'] = checklist
    st.session_state['details'] = details
    st.session_state['images_analysis'] = images_analysis
    st.session_state['verdict_reason'] = verdict_reason

# --- Show results if already in session state ---
if st.session_state.get('scraped_reviews') and st.session_state.get('genai_output'):
    reviews = st.session_state['scraped_reviews']
    genai_output = st.session_state['genai_output']
    sentiments = st.session_state['sentiments']
    checklist = st.session_state.get('checklist', {})
    details = st.session_state.get('details', {})
    confidence = st.session_state.get('confidence', '')
    images_analysis = st.session_state.get('images_analysis', '')
    verdict = st.session_state.get('verdict', None)
    verdict_reason = st.session_state.get('verdict_reason', '')
    summary = st.session_state.get('summary', None)

    # Check if no reviews were found
    if not reviews:
        st.markdown("""
        <div style='background-color:#e9ecef;padding:20px;border-radius:10px;color:#000000;margin:20px 0;'>
            <h2 style='margin-bottom:0.2em;color:#000000 !important;'>⚠️ No Reviews Available</h2>
            <p style='margin:0;color:#000000;'>No reviews were found for this product. We cannot provide a recommendation at this time.</p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # --- Average Star Rating at Top ---
    ratings = []
    for r in reviews:
        if r['rating']:
            try:
                val = int(r['rating'])
                ratings.append(val)
            except:
                pass
    if ratings:
        avg_rating = round(statistics.mean(ratings), 2)
        st.markdown(f"<h2 style='color:gold;margin-bottom:0.5em;'>⭐ {avg_rating} / 5</h2>", unsafe_allow_html=True)
    else:
        st.markdown("No ratings found.")

    # --- Confidence and Verdict ---
    # Calculate confidence based on percentage of positive reviews
    total_reviews = len(reviews)
    positive_reviews = sum(1 for r in reviews if r.get('analysis', {}).get('sentiment') == 'POSITIVE')
    conf_val = (positive_reviews / total_reviews * 100) if total_reviews > 0 else 0
    
    # Decide verdict color and text based on positive reviews percentage
    verdict_color = '#d4edda'
    verdict_icon = '✅'
    verdict_text = verdict
    if conf_val > 70:
        verdict_color = '#d4edda'
        verdict_icon = '✅'
        verdict_text = 'Recommended to Buy'
    elif conf_val > 60:
        verdict_color = '#fff3cd'
        verdict_icon = '⚠️'
        verdict_text = 'Buy with Caution'
    else:
        verdict_color = '#f8d7da'
        verdict_icon = '❌'
        verdict_text = 'Not Recommended'
    
    if confidence:
        st.markdown(f"**Confidence:** {confidence}")
    if verdict_text:
        st.markdown(f"<div style='background-color:{verdict_color};padding:20px;border-radius:10px;color:#000000;'><h2 style='margin-bottom:0.2em;color:#000000 !important;'>{verdict_icon} {verdict_text}</h2><p style='margin:0;color:#000000;'>{verdict_reason}</p></div>", unsafe_allow_html=True)

    # --- Key Factors Checklist with Expandable Real Reviews ---
    status_color = {'good': '🟢', 'high': '🟢', 'verified': '🟢',
                   'minor issues': '🟡', 'average': '🟡', 'mixed': '🟡', 'unclear': '🟡',
                   'bad': '🔴', 'low': '🔴', 'fake': '🔴', 'insufficient data': '⚪'}
    # Define robust keyword sets for each factor with positive and negative keywords
    factor_keywords_map = {
        'Product Quality': {
            'positive': ['good quality', 'excellent quality', 'impressive quality', 'high quality', 'premium quality', 'superior quality', 'durable', 'sturdy', 'solid', 'well made', 'premium', 'excellent', 'perfect', 'strong', 'rigid', 'lightweight', 'comfortable', 'soft', 'smooth', 'well constructed', 'top notch', 'first class'],
            'negative': ['poor quality', 'bad quality', 'low quality', 'cheap quality', 'inferior quality', 'cheap', 'flimsy', 'broke', 'damaged', 'defective', 'weak', 'thin', 'uncomfortable', 'rough', 'scratched', 'torn', 'loose', 'poorly made', 'falling apart', 'not durable']
        },
        'Delivery Experience': {
            'positive': ['fast delivery', 'quick shipping', 'well packed', 'protected', 'on time', 'early', 'secure packaging', 'careful packaging', 'tracked', 'professional delivery'],
            'negative': ['late', 'delayed', 'damaged package', 'poor packaging', 'lost', 'wrong address', 'missing', 'slow shipping', 'no tracking', 'unprofessional']
        },
        'Authenticity': {
            'positive': ['genuine', 'authentic', 'original', 'real', 'legitimate', 'official', 'verified', 'branded', 'authorized', 'genuine product'],
            'negative': ['fake', 'counterfeit', 'replica', 'knockoff', 'copy', 'imitation', 'suspicious', 'not original', 'unauthentic', 'questionable']
        },
        'Customer Satisfaction': {
            'positive': ['satisfied', 'happy', 'pleased', 'delighted', 'amazed', 'excellent', 'fantastic', 'wonderful', 'love', 'perfect', 'impressed', 'recommend', 'worth'],
            'negative': ['disappointed', 'frustrated', 'angry', 'upset', 'terrible', 'poor', 'bad', 'hate', 'regret', 'annoyed', 'dissatisfied', 'waste', 'not worth']
        }
    }

    if checklist:
        st.markdown("### Key Factors Checklist")
        for k, v in checklist.items():
            color = status_color.get(v.lower(), '⚪')
            with st.expander(f"{color} {k}: {v}"):
                if v.lower() == 'insufficient data':
                    st.info("Insufficient data to judge this factor from the reviews.")
                
                # Filter reviews for this category
                category_map = {
                    'Product Quality': 'QUALITY',
                    'Delivery Experience': 'DELIVERY',
                    'Authenticity': 'AUTHENTICATION',
                    'Customer Satisfaction': 'SATISFACTION'
                }
                
                # Filter reviews for this category
                category_reviews = [r for r in reviews if r.get('analysis', {}).get('category') == category_map.get(k)]
                
                if category_reviews:
                    st.markdown("<p style='font-size: 1.25rem; font-weight: bold; margin-bottom: 0.5em; text-decoration: underline;'>Customer Reviews:</p>", unsafe_allow_html=True)
                    for review in category_reviews:
                        analysis = review.get('analysis', {})
                        sentiment = analysis.get('sentiment', '')
                        summary = analysis.get('summary', '')

                        # Display original review as a paragraph in bold italics, aligned with summary
                        review_text = f"{review.get('title', '')}: {review.get('text', '')}"
                        st.markdown(f"<p style='font-style: italic; font-weight: bold; margin-bottom: 0.5em; margin-left: 1.8em;'>{review_text}</p>", unsafe_allow_html=True)

                        # Display sentiment indicator and summary on same line
                        sentiment_icon = '🟢' if sentiment == 'POSITIVE' else '🔴'
                        st.markdown(f"{sentiment_icon} {summary}")
                        st.markdown("---")
                else:
                    st.info("No specific reviews found for this category.")

    # --- Customer Images ---
    st.markdown("### 📸 Product Images From Real Buyers")
    if any(review.get('images') for review in reviews):
        st.info("👀 Check out real product images below shared by customers to get a better idea of what you'll receive!")
        with st.expander("### 📷 View Real Product Images"):
            for review in reviews:
                if review.get('images'):
                    cols = st.columns(min(4, len(review['images'])))
                    for i, img_url in enumerate(review['images']):
                        with cols[i % len(cols)]:
                            st.image(img_url)
    else:
        st.info("No real images shared by the customers for this product .")
    
    # --- Final Words ---
    st.markdown("### 📝 Final Words")
    
    # Create recommendation and summary based on confidence and ratings
    if conf_val is not None and ratings:
        avg_rating = round(statistics.mean(ratings), 2)
        
        # Calculate positive reviews percentage from the reviews' analysis
        positive_reviews = sum(1 for r in reviews if r.get('analysis', {}).get('sentiment') == 'POSITIVE')
        positive_percent = (positive_reviews / len(reviews)) * 100 if reviews else 0
        
        if conf_val > 70:
            final_icon = "✅"
            recommendation = "Recommended to Buy"
        elif conf_val > 60:
            final_icon = "⚠️"
            recommendation = "Buy with Caution"
        else:
            final_icon = "❌"
            recommendation = "Not Recommended"
            
        summary = f"""Based on our analysis of **{len(reviews)}** customer reviews and an average rating of ⭐ **{avg_rating}/5**, 
        with **{positive_percent:.0f}%** positive feedback, here's my verdict:

{verdict_reason}

Final Recommendation: {final_icon} <span style='text-decoration: underline;'>{recommendation}</span>"""        
        st.markdown(summary, unsafe_allow_html=True)
        