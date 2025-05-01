from mistralai.client import MistralClient
from scraper import JashanmalScraper
import json
import time
from mistralai.exceptions import MistralException
from mistralai.models.chat_completion import ChatMessage

def analyze_reviews_batch(reviews_batch, model, client, retry_count=0):
    max_retries = 3
    try:
        time.sleep(1)  # Small delay between batches
        
        # Format all reviews in the batch
        reviews_text = "\n---\n".join([
            f"Review {i+1}:\nTitle: {review.get('title', '')}\nText: {review.get('text', '')}"
            for i, review in enumerate(reviews_batch)
        ])
        
        prompt = f'''
You are a professional Product Review Analyst AI. Analyze each review and provide a summary and tags.
For each review, provide:
1. A brief summary (1-2 sentences)
2. Two tags:
   a. Sentiment: POSITIVE or NEGATIVE
   b. Category: One of these categories:
      - SATISFACTION (emotional responses, overall satisfaction)
      - DELIVERY (shipping, packaging, timing)
      - AUTHENTICATION (product authenticity, matching description)
      - QUALITY (build quality, durability, materials)

Format your response exactly like this for each review:
REVIEW 1:
SUMMARY: [Your 1-2 sentence summary]
SENTIMENT: [POSITIVE or NEGATIVE]
CATEGORY: [SATISFACTION/DELIVERY/AUTHENTICATION/QUALITY]

REVIEW 2:
... and so on for each review.

Here are the reviews to analyze:

{reviews_text}
'''
        chat_response = client.chat(
            model=model,
            messages=[
                ChatMessage(role="user", content=prompt)
            ]
        )
        response = chat_response.choices[0].message.content
        
        # Parse the batch response
        analyses = []
        current_analysis = {}
        current_review_num = None
        
        for line in response.strip().split('\n'):
            line = line.strip()
            if line.startswith('REVIEW '):
                if current_analysis and current_review_num is not None:
                    analyses.append(current_analysis)
                current_analysis = {}
                try:
                    current_review_num = int(line.split()[1].strip(':')) - 1
                except:
                    current_review_num = len(analyses)
            elif line.startswith('SUMMARY:'):
                current_analysis['summary'] = line[8:].strip()
            elif line.startswith('SENTIMENT:'):
                current_analysis['sentiment'] = line[10:].strip()
            elif line.startswith('CATEGORY:'):
                current_analysis['category'] = line[9:].strip()
        
        if current_analysis:
            analyses.append(current_analysis)
            
        return analyses
        
    except MistralException as e:
        if "rate limit" in str(e).lower() and retry_count < max_retries:
            time.sleep(5 * (retry_count + 1))
            return analyze_reviews_batch(reviews_batch, model, client, retry_count + 1)
        raise e

def analyze_reviews_with_genai(reviews, model, client):
    # Process reviews in batches of 5
    BATCH_SIZE = 5
    all_analyses = []
    
    for i in range(0, len(reviews), BATCH_SIZE):
        batch = reviews[i:i + BATCH_SIZE]
        try:
            batch_analyses = analyze_reviews_batch(batch, model, client)
            all_analyses.extend(batch_analyses)
        except Exception as e:
            print(f"Error analyzing batch {i//BATCH_SIZE + 1}: {str(e)}")
            # Add fallback analysis for failed batch
            all_analyses.extend([{
                'summary': 'Analysis failed due to API limits',
                'sentiment': 'NEUTRAL',
                'category': 'SATISFACTION'
            } for _ in batch])
    
    # Attach analyses to reviews
    for review, analysis in zip(reviews, all_analyses):
        review['analysis'] = analysis
    
    # Save progress
    with open('review_analysis_progress.json', 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    
    # Do the overall analysis with a summary of the analyzed reviews
    try:
        # Count sentiments and categories for a quick summary
        sentiments = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
        categories = {'SATISFACTION': 0, 'DELIVERY': 0, 'AUTHENTICATION': 0, 'QUALITY': 0}
        
        for review in reviews:
            analysis = review.get('analysis', {})
            sentiments[analysis.get('sentiment', 'NEUTRAL')] += 1
            categories[analysis.get('category', 'SATISFACTION')] += 1
        
        total = len(reviews)
        positive_percent = (sentiments['POSITIVE'] / total) * 100 if total > 0 else 0
        
        analysis_text = f'''
Confidence Score: {positive_percent:.0f}% positive reviews

Checklist:
- Product Quality: {"Good" if categories['QUALITY'] > 0 and sentiments['POSITIVE'] > sentiments['NEGATIVE'] else "Unclear" if categories['QUALITY'] == 0 else "Mixed"}
- Delivery Experience: {"Good" if categories['DELIVERY'] > 0 and sentiments['POSITIVE'] > sentiments['NEGATIVE'] else "Unclear" if categories['DELIVERY'] == 0 else "Mixed"}
- Authenticity: {"Verified" if categories['AUTHENTICATION'] > 0 and sentiments['POSITIVE'] > sentiments['NEGATIVE'] else "Unclear" if categories['AUTHENTICATION'] == 0 else "Mixed"}
- Customer Satisfaction: {"High" if sentiments['POSITIVE'] > sentiments['NEGATIVE'] else "Unclear" if categories['SATISFACTION'] == 0 else "Mixed"}

Note: Analysis based on {total} reviews.
'''
        return analysis_text, sentiments
    except Exception as e:
        print(f"Error in overall analysis: {str(e)}")
        return "Analysis incomplete due to errors. Please check individual review analyses.", {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}