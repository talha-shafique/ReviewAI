import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging
import json
from fake_useragent import UserAgent
import random
import requests
from bs4 import BeautifulSoup
import urllib3
import ssl
import certifi

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JashanmalScraper:
    def __init__(self, verify_ssl=False):
        self.base_url = "https://www.jashanmal.com"
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.verify = verify_ssl
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.user_agent = UserAgent()
        
    def _get_chrome_options(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument('--disable-notifications')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'user-agent={self.user_agent.random}')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        # Add these options for faster loading
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-software-rasterizer')
        options.add_argument('--disable-extensions')
        return options
        
    def scrape_reviews(self, url, max_reviews=None):
        driver = None
        try:
            options = self._get_chrome_options()
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)
            logger.info(f"Loading URL: {url}")
            
            driver.get(url)
            time.sleep(2)  # Reduced initial wait time
            
            # Wait for the review container
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '#stamped-main-widget'))
            )
            
            # Get total review count
            total_reviews = self._get_total_reviews(driver)
            if max_reviews is None:
                max_reviews = total_reviews
            
            logger.info(f"Found {total_reviews} total reviews. Will read up to {max_reviews}")
            
            all_reviews = []
            current_page = 1
            last_review_count = 0
            retry_count = 0
            
            while len(all_reviews) < max_reviews and retry_count < 3:
                try:
                    # Extract current page reviews
                    new_reviews = self._extract_reviews_from_page(driver)
                    
                    # Check if we got new reviews
                    if len(new_reviews) > 0:
                        all_reviews.extend(new_reviews)
                        logger.info(f"Read{len(all_reviews)} reviews from page {current_page}")
                        last_review_count = len(all_reviews)
                        retry_count = 0  # Reset retry counter on success
                        current_page += 1
                        
                        # Try to go to next page using JavaScript
                        if len(all_reviews) < max_reviews:
                            script = f"""
                            var nextPageBtn = document.querySelector('a[data-page="{current_page}"]');
                            if(nextPageBtn) {{
                                nextPageBtn.click();
                                return true;
                            }}
                            return false;
                            """
                            has_next = driver.execute_script(script)
                            if not has_next:
                                break
                            time.sleep(1)  # Short wait after click
                    else:
                        retry_count += 1
                        time.sleep(1)
                        
                except Exception as e:
                    logger.warning(f"Error on page {current_page}: {str(e)}")
                    retry_count += 1
                    if retry_count >= 3:
                        break
                    time.sleep(1)
            
            return all_reviews[:max_reviews]
            
        finally:
            if driver:
                driver.quit()
                
    def _get_total_reviews(self, driver):
        try:
            summary_text = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.stamped-summary-text'))
            ).text
            count_match = re.search(r'Based on (\d+) Reviews', summary_text)
            return int(count_match.group(1)) if count_match else 0
        except:
            return 0
            
    def _extract_reviews_from_page(self, driver):
        reviews = []
        try:
            # Wait for reviews to be present and get them all at once
            review_elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '.stamped-review'))
            )
            
            for element in review_elements:
                try:
                    # Extract review data including images using JavaScript
                    review_data = driver.execute_script("""
                        var el = arguments[0];
                        
                        // Extract images with better selectors
                        var images = [];
                        var imageLinks = el.querySelectorAll('.stamped-review-image a');
                        imageLinks.forEach(function(link) {
                            var href = link.getAttribute('href');
                            if (href) {
                                // Clean up the URL by removing query parameters and transforming to high resolution
                                href = href.split('?')[0];
                                href = href.replace('tr:h-180', 'tr:h-800');
                                if (!images.includes(href)) {
                                    images.push(href);
                                }
                            }
                            
                            // Also check the img tag within the link
                            var img = link.querySelector('img');
                            if (img) {
                                var src = img.getAttribute('src');
                                if (src) {
                                    src = src.split('?')[0];
                                    src = src.replace('tr:h-180', 'tr:h-800');
                                    if (!images.includes(src)) {
                                        images.push(src);
                                    }
                                }
                            }
                        });
                        
                        return {
                            reviewer: el.querySelector('.stamped-review-header-title')?.textContent?.trim() || '',
                            rating: el.querySelectorAll('.stamped-fa.stamped-fa-star:not(.stamped-fa-empty)').length,
                            title: el.querySelector('.stamped-review-header-title')?.textContent?.trim() || '',
                            text: el.querySelector('.stamped-review-content-body')?.textContent?.trim() || '',
                            date: el.querySelector('.created')?.textContent?.trim() || '',
                            verified: !!el.querySelector('.stamped-review-verified'),
                            images: images,
                            location: el.querySelector('.review-location')?.textContent?.trim() || ''
                        };
                    """, element)
                    
                    # Convert rating to string to match existing format
                    review_data['rating'] = str(review_data['rating'])
                    
                    # Check for duplicates using a more robust method
                    is_duplicate = False
                    for existing_review in reviews:
                        if (existing_review['text'] == review_data['text'] and 
                            existing_review['reviewer'] == review_data['reviewer'] and
                            existing_review['date'] == review_data['date']):
                            is_duplicate = True
                            break
                    
                    if review_data['text'] and not is_duplicate:
                        reviews.append(review_data)
                        
                except Exception as e:
                    logger.debug(f"Failed to extract review: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Failed to get review elements: {str(e)}")
            
        return reviews

    def get_product_image(self, driver):
        try:
            # Wait for and get the product image
            product_img = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '.stamped-product-image img, .product-image img, .product__media img'))
            )
            src = product_img.get_attribute('src')
            if src and 'data:image' not in src:  # Avoid base64 encoded images
                return src
            return None
        except:
            logger.warning("Could not find product image")
            return None

if __name__ == '__main__':
    scraper = JashanmalScraper()
    url = input('Enter Jashanmal product URL: ')
    max_reviews = input('Enter maximum number of reviews to scrape (or press Enter for all): ')
    max_reviews = int(max_reviews) if max_reviews.strip() else None
    
    reviews = scraper.scrape_reviews(url, max_reviews=max_reviews)
    
    output_file = 'review.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    print(f'Reviews saved to {output_file}')