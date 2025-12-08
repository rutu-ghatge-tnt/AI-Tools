"""
URL Scraper for extracting ingredients from e-commerce product pages
Supports: Amazon, Nykaa, Flipkart, and other e-commerce sites
Uses Selenium WebDriver for JavaScript-enabled scraping
"""
import re
import json
import asyncio
from typing import List, Optional, Dict
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from anthropic import Anthropic
import os


class URLScraper:
    def __init__(self):
        """Initialize the URL scraper - Anthropic client is lazy-loaded only when needed"""
        self.claude_client: Optional[Anthropic] = None
        self.driver: Optional[webdriver.Chrome] = None
    
    def _get_claude_client(self):
        """Lazy-load Claude client only when needed for ingredient extraction"""
        if self.claude_client is None:
            claude_key = os.getenv("CLAUDE_API_KEY")
            if not claude_key:
                raise Exception("CLAUDE_API_KEY environment variable is not set")
            try:
                self.claude_client = Anthropic(api_key=claude_key)
            except Exception as e:
                raise Exception(f"Failed to initialize Claude client: {str(e)}")
        return self.claude_client
        
    async def _get_driver(self):
        """Initialize Selenium Chrome driver (runs in executor for async compatibility)"""
        if self.driver is None:
            loop = asyncio.get_event_loop()
            
            def init_driver():
                import subprocess
                import platform
                
                chrome_options = Options()
                
                # Check if running on server (headless mode) or local (visible browser)
                # Use environment variable HEADLESS_MODE or default to True for servers
                headless_mode = os.getenv("HEADLESS_MODE", "true").lower() == "true"
                
                if headless_mode:
                    # Server deployment - use headless mode
                    chrome_options.add_argument("--headless=new")  # New headless mode
                    chrome_options.add_argument("--disable-gpu")
                    print("Running in headless mode (server deployment)")
                else:
                    # Local development - visible browser
                    chrome_options.add_argument("--start-maximized")
                    print("Running in visible mode (local development)")
                
                # Essential options for both local and server
                chrome_options.add_argument("--no-sandbox")  # Required for server/Linux
                chrome_options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
                chrome_options.add_argument("--disable-blink-features=AutomationControlled")
                chrome_options.add_argument("--window-size=1920,1080")  # Set window size for consistency
                chrome_options.add_argument("--disable-extensions")
                chrome_options.add_argument("--disable-software-rasterizer")
                chrome_options.add_argument("--disable-background-timer-throttling")
                chrome_options.add_argument("--disable-backgrounding-occluded-windows")
                chrome_options.add_argument("--disable-renderer-backgrounding")
                
                # Additional Linux server options
                chrome_options.add_argument("--disable-setuid-sandbox")
                chrome_options.add_argument("--disable-web-security")
                chrome_options.add_argument("--disable-features=IsolateOrigins,site-per-process")
                chrome_options.add_argument("--single-process")  # Run in single process mode (helps on some servers)
                
                # User agent
                chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                
                # Experimental options
                chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                chrome_options.add_experimental_option('useAutomationExtension', False)
                
                # Try to find Chrome binary on Linux servers
                chrome_binary = None
                if platform.system() == "Linux":
                    # Try common Chrome/Chromium paths
                    possible_paths = [
                        "/usr/bin/google-chrome",
                        "/usr/bin/google-chrome-stable",
                        "/usr/bin/chromium",
                        "/usr/bin/chromium-browser",
                        "/snap/bin/chromium"
                    ]
                    for path in possible_paths:
                        if os.path.exists(path):
                            chrome_binary = path
                            print(f"Found Chrome binary at: {chrome_binary}")
                            break
                    
                    if chrome_binary:
                        chrome_options.binary_location = chrome_binary
                    else:
                        # Try to find via which command
                        try:
                            result = subprocess.run(
                                ["which", "google-chrome"],
                                capture_output=True,
                                text=True,
                                timeout=2
                            )
                            if result.returncode == 0 and result.stdout.strip():
                                chrome_binary = result.stdout.strip()
                                chrome_options.binary_location = chrome_binary
                                print(f"Found Chrome via which: {chrome_binary}")
                        except:
                            pass
                        
                        if not chrome_binary:
                            try:
                                result = subprocess.run(
                                    ["which", "chromium-browser"],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                if result.returncode == 0 and result.stdout.strip():
                                    chrome_binary = result.stdout.strip()
                                    chrome_options.binary_location = chrome_binary
                                    print(f"Found Chromium via which: {chrome_binary}")
                            except:
                                pass
                
                # Use webdriver-manager to automatically download and manage ChromeDriver
                try:
                    service = Service(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                except Exception as e:
                    # Fallback: try without service (if ChromeDriver is in PATH)
                    print(f"Warning: ChromeDriverManager failed, trying direct: {e}")
                    try:
                        driver = webdriver.Chrome(options=chrome_options)
                    except Exception as e2:
                        error_msg = str(e2)
                        install_instructions = ""
                        if platform.system() == "Linux":
                            install_instructions = (
                                "\n\nTo fix on Linux server, run:\n"
                                "sudo apt-get update\n"
                                "sudo apt-get install -y google-chrome-stable\n"
                                "OR\n"
                                "sudo apt-get install -y chromium-browser chromium-chromedriver\n"
                                "\nIf Chrome is installed but not found, check:\n"
                                "1. Chrome binary location: which google-chrome\n"
                                "2. Set CHROME_BIN environment variable if Chrome is in non-standard location\n"
                                "3. Ensure all Chrome dependencies are installed:\n"
                                "   sudo apt-get install -y libnss3 libatk-bridge2.0-0 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2"
                            )
                        raise Exception(
                            f"Failed to initialize Chrome driver: {error_msg}\n"
                            f"Server deployment requires:\n"
                            f"1. Chrome browser installed\n"
                            f"2. ChromeDriver available (webdriver-manager will download it)\n"
                            f"3. Set HEADLESS_MODE=true in environment variables{install_instructions}"
                        )
                
                # Execute script to hide webdriver property
                try:
                    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': '''
                            Object.defineProperty(navigator, 'webdriver', {
                                get: () => undefined
                            })
                        '''
                    })
                except:
                    pass  # Non-critical, continue anyway
                
                return driver
            
            try:
                self.driver = await loop.run_in_executor(None, init_driver)
            except Exception as e:
                error_msg = str(e)
                if "chromedriver" in error_msg.lower() or "executable" in error_msg.lower() or "session not created" in error_msg.lower():
                    raise Exception(
                        f"ChromeDriver error: {error_msg}\n"
                        f"For server deployment, ensure:\n"
                        f"1. Chrome/Chromium is installed and accessible\n"
                        f"2. Set HEADLESS_MODE=true in environment variables\n"
                        f"3. ChromeDriver is available (webdriver-manager will download it)\n"
                        f"4. On Linux: Install Chrome dependencies (see error message above)"
                    )
                else:
                    raise Exception(f"Failed to initialize Chrome driver: {error_msg}")
            
        return self.driver
    
    async def _close_driver(self):
        """Close the Selenium driver"""
        if self.driver:
            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(None, self.driver.quit)
            except:
                pass
            self.driver = None
    
    def _detect_platform(self, url: str) -> str:
        """Detect the e-commerce platform from URL - extracts actual platform name from domain"""
        from urllib.parse import urlparse
        url_lower = url.lower()
        
        # Check for known platforms first
        if "amazon" in url_lower:
            return "amazon"
        elif "nykaa" in url_lower:
            return "nykaa"
        elif "flipkart" in url_lower:
            return "flipkart"
        elif "myntra" in url_lower:
            return "myntra"
        elif "purplle" in url_lower:
            return "purplle"
        elif "beautybay" in url_lower:
            return "beautybay"
        elif "sephora" in url_lower:
            return "sephora"
        elif "ulta" in url_lower:
            return "ulta"
        elif "cultbeauty" in url_lower:
            return "cultbeauty"
        elif "lookfantastic" in url_lower:
            return "lookfantastic"
        else:
            # Extract domain name from URL to detect actual platform instead of generic
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                # Remove www. prefix
                if domain.startswith("www."):
                    domain = domain[4:]
                # Extract main domain (e.g., "example.com" -> "example")
                domain_parts = domain.split(".")
                if len(domain_parts) >= 2:
                    # Get the main domain name (second to last part, or last if only one)
                    platform_name = domain_parts[-2] if len(domain_parts) > 2 else domain_parts[0]
                    # Return the actual platform name instead of "generic"
                    return platform_name
            except:
                pass
            # Fallback to generic only if we can't parse the URL
            return "generic"
    
    async def _scrape_amazon(self, driver: webdriver.Chrome) -> str:
        """Scrape ingredients from Amazon product page"""
        try:
            loop = asyncio.get_event_loop()
            
            def scrape():
                wait = WebDriverWait(driver, 10)
                
                # Try multiple selectors for ingredients/description
                selectors = [
                    "#feature-bullets ul",
                    "#productDescription",
                    "#productDetails_techSpec_section_1",
                    ".a-unordered-list",
                    "[data-feature-name='productDescription']",
                    "#productDescription_feature_div"
                ]
                
                text_parts = []
                for selector in selectors:
                    try:
                        elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector)))
                        for element in elements:
                            text = element.text.strip()
                            if text and len(text) > 20:
                                text_parts.append(text)
                    except TimeoutException:
                        continue
                    except:
                        continue
                
                if text_parts:
                    return "\n".join(text_parts)
                else:
                    # Fallback: get all text content
                    return driver.find_element(By.TAG_NAME, "body").text
            
            return await loop.run_in_executor(None, scrape)
        except Exception as e:
            print(f"Error scraping Amazon: {e}")
            if self.driver:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: driver.find_element(By.TAG_NAME, "body").text)
            return ""
    
    async def _scrape_nykaa(self, driver: webdriver.Chrome) -> str:
        """Scrape ingredients and product details from Nykaa product page"""
        try:
            loop = asyncio.get_event_loop()
            
            def scrape():
                import time
                from bs4 import BeautifulSoup
                
                # Wait for page to load
                wait = WebDriverWait(driver, 10)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#app")))
                time.sleep(2)
                
                text_parts = []
                
                # FIRST: Extract main product information (name, price, ratings, brand) from the page header
                try:
                    # Get the main product section - try multiple selectors
                    product_selectors = [
                        "[class*='product-detail']",
                        "[class*='ProductDetail']",
                        "[class*='product-info']",
                        "h1",
                        "[data-testid='product-name']",
                        ".css-1geu4rv",  # Common Nykaa product name class
                    ]
                    
                    product_info = []
                    
                    # Try to get product name
                    for selector in product_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for elem in elements:
                                text = elem.text.strip()
                                if text and len(text) > 5 and len(text) < 200:
                                    product_info.append(f"Product Name: {text}")
                                    break
                            if product_info:
                                break
                        except:
                            continue
                    
                    # Try to get price - look for ₹ symbol or price patterns
                    price_selectors = [
                        "[class*='price']",
                        "[class*='Price']",
                        "[data-testid='price']",
                        "[class*='selling']",
                    ]
                    
                    for selector in price_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for elem in elements:
                                text = elem.text.strip()
                                if '₹' in text or 'Rs.' in text or 'INR' in text or ('price' in text.lower() and any(c.isdigit() for c in text)):
                                    # Extract price with context
                                    price_text = text
                                    if len(price_text) < 100:  # Reasonable price length
                                        product_info.append(f"Price: {price_text}")
                                        break
                            if any('Price:' in p for p in product_info):
                                break
                        except:
                            continue
                    
                    # Also try XPath to find elements containing ₹
                    try:
                        price_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '₹')]")
                        for elem in price_elements[:5]:  # Limit to first 5 matches
                            text = elem.text.strip()
                            if '₹' in text and len(text) < 50:
                                product_info.append(f"Price: {text}")
                                break
                    except:
                        pass
                    
                    # Try to get ratings
                    rating_selectors = [
                        "[class*='rating']",
                        "[class*='Rating']",
                        "[data-testid='rating']",
                        "[class*='star']",
                    ]
                    
                    for selector in rating_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for elem in elements:
                                text = elem.text.strip()
                                if '/' in text and ('5' in text or 'star' in text.lower() or 'rating' in text.lower()):
                                    product_info.append(f"Ratings: {text}")
                                    break
                            if any('Ratings:' in p for p in product_info):
                                break
                        except:
                            continue
                    
                    # Also try XPath for ratings
                    try:
                        rating_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '/5') or contains(text(), 'rating')]")
                        for elem in rating_elements[:5]:
                            text = elem.text.strip()
                            if ('/5' in text or 'rating' in text.lower()) and len(text) < 100:
                                product_info.append(f"Ratings: {text}")
                                break
                    except:
                        pass
                    
                    # Get brand name - usually before product name or in breadcrumbs
                    try:
                        brand_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='brand'], [class*='Brand'], a[href*='/brand/']")
                        for elem in brand_elements:
                            text = elem.text.strip()
                            if text and len(text) > 2 and len(text) < 50:
                                product_info.append(f"Brand: {text}")
                                break
                    except:
                        pass
                    
                    if product_info:
                        text_parts.append("Product Information:\n" + "\n".join(product_info))
                    
                    # Also get visible text from product header area
                    try:
                        # Get page title
                        page_title = driver.title
                        if page_title and len(page_title) > 10:
                            text_parts.append(f"Page Title: {page_title}")
                    except:
                        pass
                    
                except Exception as e:
                    print(f"Could not extract main product info: {e}")
                
                # Scroll down to load content
                driver.execute_script("window.scrollBy(0, 500);")
                time.sleep(1)
                
                # SECOND: Extract from Ingredients tab
                try:
                    # Look for Ingredients tab
                    ingredients_tab = driver.find_element(By.XPATH, "//h3[normalize-space()='Ingredients']")
                    driver.execute_script("arguments[0].scrollIntoView(true);", ingredients_tab)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", ingredients_tab)
                    time.sleep(1.5)
                    
                    # Wait for content to appear
                    wait.until(EC.presence_of_element_located((By.ID, "content-details")))
                    
                    # Get the content block
                    block = driver.find_element(By.ID, "content-details")
                    html = block.get_attribute("innerHTML")
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Extract text from paragraphs and lists
                    lines = []
                    for p in soup.find_all("p"):
                        lines.append(p.get_text(strip=True))
                    for li in soup.find_all("li"):
                        lines.append("• " + li.get_text(strip=True))
                    if not lines:
                        lines = [soup.get_text(separator="\n", strip=True)]
                    
                    ingredients_text = "\n".join(lines).strip()
                    if ingredients_text:
                        text_parts.append(f"Ingredients:\n{ingredients_text}")
                except Exception as e:
                    print(f"Could not extract Ingredients tab: {e}")
                
                # THIRD: Extract from Description tab
                try:
                    desc_tab = driver.find_element(By.XPATH, "//h3[normalize-space()='Description']")
                    driver.execute_script("arguments[0].scrollIntoView(true);", desc_tab)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", desc_tab)
                    time.sleep(1.5)
                    
                    wait.until(EC.presence_of_element_located((By.ID, "content-details")))
                    block = driver.find_element(By.ID, "content-details")
                    html = block.get_attribute("innerHTML")
                    soup = BeautifulSoup(html, "html.parser")
                    
                    lines = []
                    for p in soup.find_all("p"):
                        lines.append(p.get_text(strip=True))
                    for li in soup.find_all("li"):
                        lines.append("• " + li.get_text(strip=True))
                    if not lines:
                        lines = [soup.get_text(separator="\n", strip=True)]
                    
                    desc_text = "\n".join(lines).strip()
                    if desc_text:
                        text_parts.append(f"Description:\n{desc_text}")
                except Exception as e:
                    print(f"Could not extract Description tab: {e}")
                
                # FOURTH: Always get additional visible text from page for comprehensive extraction
                try:
                    # Get visible text from the page (more content for better extraction)
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    # Extract first 5000 chars which usually contains product info, price, ratings
                    visible_text = body_text[:5000]
                    if visible_text and visible_text not in "\n".join(text_parts):
                        # Only add if it's not already included
                        text_parts.append(f"Additional Page Content:\n{visible_text}")
                except:
                    pass
                
                result = "\n\n".join(text_parts) if text_parts else driver.find_element(By.TAG_NAME, "body").text
                print(f"Nykaa extraction summary: {len(text_parts)} sections, {len(result)} total characters")
                if product_info:
                    print(f"Extracted product info: {product_info}")
                return result
            
            return await loop.run_in_executor(None, scrape)
        except Exception as e:
            print(f"Error scraping Nykaa: {e}")
            if self.driver:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: driver.find_element(By.TAG_NAME, "body").text)
            return ""
    
    async def _scrape_flipkart(self, driver: webdriver.Chrome) -> str:
        """Scrape ingredients from Flipkart product page"""
        try:
            await asyncio.sleep(2)  # Give JS time to render
            
            loop = asyncio.get_event_loop()
            
            def scrape():
                selectors = [
                    ".product-description",
                    "._2418kt",
                    "[data-id='product-description']",
                    "._1mXcCf",
                    ".product-details"
                ]
                
                text_parts = []
                for selector in selectors:
                    try:
                        elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        for element in elements:
                            text = element.text.strip()
                            if text and len(text) > 20:
                                text_parts.append(text)
                    except:
                        continue
                
                if text_parts:
                    return "\n".join(text_parts)
                else:
                    return driver.find_element(By.TAG_NAME, "body").text
            
            return await loop.run_in_executor(None, scrape)
        except Exception as e:
            print(f"Error scraping Flipkart: {e}")
            if self.driver:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: driver.find_element(By.TAG_NAME, "body").text)
            return ""
    
    async def _scrape_generic(self, driver: webdriver.Chrome) -> str:
        """Scrape ingredients from generic e-commerce page - clicks accordions to find ingredient lists"""
        try:
            await asyncio.sleep(2)  # Give JS time to render
            
            loop = asyncio.get_event_loop()
            
            def scrape():
                import time
                from bs4 import BeautifulSoup
                
                wait = WebDriverWait(driver, 10)
                text_parts = []
                
                # FIRST: Try to click on accordions/buttons that contain ingredient-related keywords
                ingredient_keywords = [
                    "ingredient", "ingredients", "key ingredient", "key ingredients",
                    "inci", "composition", "formula", "formulation", "contains",
                    "ingredient list", "full ingredient", "ingredient list"
                ]
                
                clicked_elements = set()  # Track clicked elements to avoid duplicates
                
                try:
                    # Scroll through the page to find accordion elements
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    
                    # Find all clickable elements that might be accordions/buttons
                    # Look for buttons, divs, spans, h3, h4, etc. that contain ingredient keywords
                    selectors_to_try = [
                        "button", "div[role='button']", "a[role='button']",
                        "h3", "h4", "h5", "[class*='accordion']", "[class*='Accordion']",
                        "[class*='collapse']", "[class*='expand']", "[class*='toggle']",
                        "[aria-expanded]", "[data-toggle]", "[data-target]"
                    ]
                    
                    for selector in selectors_to_try:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                try:
                                    # Get element text and check if it contains ingredient keywords
                                    element_text = element.text.strip().lower()
                                    element_id = element.id or element.get_attribute("id") or ""
                                    
                                    # Skip if already clicked
                                    if element_id in clicked_elements:
                                        continue
                                    
                                    # Check if element text contains ingredient keywords
                                    if any(keyword in element_text for keyword in ingredient_keywords):
                                        # Scroll element into view
                                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                        time.sleep(0.5)
                                        
                                        # Try to click the element
                                        try:
                                            # Try JavaScript click first (more reliable)
                                            driver.execute_script("arguments[0].click();", element)
                                            clicked_elements.add(element_id)
                                            print(f"Clicked accordion/button: {element_text[:50]}")
                                            time.sleep(1.5)  # Wait for content to expand
                                        except:
                                            # Try regular click as fallback
                                            try:
                                                element.click()
                                                clicked_elements.add(element_id)
                                                print(f"Clicked accordion/button (regular): {element_text[:50]}")
                                                time.sleep(1.5)
                                            except:
                                                pass
                                except:
                                    continue
                        except:
                            continue
                    
                    # Also try XPath to find elements containing ingredient keywords
                    for keyword in ingredient_keywords:
                        try:
                            xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]"
                            elements = driver.find_elements(By.XPATH, xpath)
                            for element in elements:
                                try:
                                    element_id = element.id or element.get_attribute("id") or ""
                                    if element_id in clicked_elements:
                                        continue
                                    
                                    # Check if it's a clickable element
                                    tag_name = element.tag_name.lower()
                                    if tag_name in ['button', 'a', 'div', 'span', 'h3', 'h4', 'h5']:
                                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                        time.sleep(0.5)
                                        try:
                                            driver.execute_script("arguments[0].click();", element)
                                            clicked_elements.add(element_id)
                                            print(f"Clicked element via XPath: {keyword}")
                                            time.sleep(1.5)
                                        except:
                                            pass
                                except:
                                    continue
                        except:
                            continue
                    
                except Exception as e:
                    print(f"Error clicking accordions: {e}")
                
                # SECOND: Extract text from the page (after clicking accordions)
                try:
                    # Wait a bit for all accordions to expand
                    time.sleep(2)
                    
                    # Get all text content
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    
                    # Look for sections with ingredient keywords
                    keywords = ["ingredient", "composition", "formula", "contains", "inci"]
                    lines = body_text.split("\n")
                    relevant_lines = []
                    in_ingredient_section = False
                    
                    for line in lines:
                        line_lower = line.lower()
                        if any(keyword in line_lower for keyword in keywords):
                            in_ingredient_section = True
                            relevant_lines.append(line)
                        elif in_ingredient_section and line.strip():
                            relevant_lines.append(line)
                            if len(relevant_lines) > 100:  # Increased limit
                                break
                    
                    if relevant_lines:
                        text_parts.append("\n".join(relevant_lines))
                    
                    # Also get visible text from expanded sections
                    try:
                        # Look for common ingredient section selectors
                        ingredient_selectors = [
                            "[class*='ingredient']", "[id*='ingredient']",
                            "[class*='composition']", "[id*='composition']",
                            "[class*='inci']", "[id*='inci']"
                        ]
                        
                        for selector in ingredient_selectors:
                            try:
                                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                for element in elements:
                                    text = element.text.strip()
                                    if text and len(text) > 20:
                                        text_parts.append(text)
                            except:
                                continue
                    except:
                        pass
                    
                except Exception as e:
                    print(f"Error extracting text: {e}")
                
                # THIRD: Fallback - get body text if nothing found
                if not text_parts:
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        # Return first 5000 characters
                        return body_text[:5000]
                    except:
                        return ""
                
                # Combine all text parts
                result = "\n\n".join(text_parts) if text_parts else ""
                if not result or len(result.strip()) < 10:
                    # Final fallback
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        return body_text[:5000]
                    except:
                        return ""
                
                return result
            
            return await loop.run_in_executor(None, scrape)
        except Exception as e:
            print(f"Error scraping generic page: {e}")
            if self.driver:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: driver.find_element(By.TAG_NAME, "body").text[:5000])
            return ""
    
    async def scrape_url(self, url: str) -> Dict[str, any]:
        """
        Scrape a product URL and extract text content using Selenium
        
        Returns:
            Dict with 'extracted_text' and 'platform' keys
        """
        driver = None
        try:
            # Initialize driver
            driver = await self._get_driver()
            
            loop = asyncio.get_event_loop()
            
            # Load URL in executor (Selenium is synchronous)
            print(f"Loading URL with Selenium: {url}")
            await loop.run_in_executor(None, driver.get, url)
            
            # Wait for page to load
            await asyncio.sleep(3)  # Give JavaScript time to render
            
            # Detect platform and scrape accordingly
            platform = self._detect_platform(url)
            print(f"Detected platform: {platform}")
            
            if platform == "amazon":
                extracted_text = await self._scrape_amazon(driver)
            elif platform == "nykaa":
                extracted_text = await self._scrape_nykaa(driver)
            elif platform == "flipkart":
                extracted_text = await self._scrape_flipkart(driver)
            else:
                extracted_text = await self._scrape_generic(driver)
            
            if not extracted_text or len(extracted_text.strip()) < 10:
                raise Exception("No meaningful text extracted from the page")
            
            print(f"Extracted {len(extracted_text)} characters of text")
            
            return {
                "extracted_text": extracted_text,
                "platform": platform,
                "url": url
            }
            
        except WebDriverException as e:
            raise Exception(f"Selenium WebDriver error: {str(e)}. Make sure ChromeDriver is installed.")
        except Exception as e:
            raise Exception(f"Failed to scrape URL: {str(e)}")
        finally:
            # Don't close driver here - keep it for reuse
            pass
    
    async def close(self):
        """Close the Selenium driver"""
        await self._close_driver()
    
    async def detect_product_name(self, raw_text: str, url: str) -> Optional[str]:
        """
        Detect product name from scraped text or URL using Claude
        
        Args:
            raw_text: Raw text scraped from the product page
            url: The product URL
            
        Returns:
            Product name string or None if not detected
        """
        try:
            prompt = f"""
You are analyzing an e-commerce product page. Your task is to identify the product name from the following information.

URL: {url}

Scraped text (first 2000 characters):
{raw_text[:2000]}

Please extract the product name. This should be:
1. The main product name (e.g., "The Ordinary Glycolic Acid 7% Exfoliating Solution")
2. Not the brand name alone
3. Not the category
4. The specific product name that would help identify it on other platforms

Return ONLY the product name as a plain text string. If you cannot identify a clear product name, return "null".

Product name:"""

            claude_client = self._get_claude_client()
            from app.config import CLAUDE_MODEL
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else "claude-3-opus-20240229"
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=200,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            product_name = response.content[0].text.strip()
            
            # Clean up response
            if product_name.lower() in ["null", "none", "n/a", ""]:
                return None
            
            # Remove quotes if present
            product_name = product_name.strip('"\'')
            
            return product_name if product_name else None
            
        except Exception as e:
            print(f"Error detecting product name: {e}")
            return None
    
    async def search_ingredients_by_product_name(self, product_name: str) -> List[str]:
        """
        Use Claude to search for INCI ingredients based on product name
        This is a fallback when direct extraction from URL fails
        
        Args:
            product_name: The detected product name
            
        Returns:
            List of estimated INCI ingredient names
        """
        try:
            prompt = f"""
You are a cosmetic ingredient expert. A user is trying to find the INCI (International Nomenclature of Cosmetic Ingredients) list for this product:

Product Name: {product_name}

Since we were unable to extract the ingredients directly from the product URL, please help by providing an estimated INCI ingredient list based on:
1. Your knowledge of this specific product
2. Similar products from the same brand/line
3. Common ingredients in products of this type
4. Information available from various e-commerce platforms and cosmetic databases

IMPORTANT:
- Return ONLY a JSON array of INCI names
- Include only ingredients that are likely to be in this product
- Be as accurate as possible based on product knowledge
- If this is a well-known product, use your knowledge of its actual formulation
- If uncertain, include common ingredients for this product type

Example output format:
["Water", "Glycerin", "Sodium Hyaluronate", "Hyaluronic Acid"]

Return only the JSON array of INCI names:"""

            claude_client = self._get_claude_client()
            from app.config import CLAUDE_MODEL
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else "claude-3-opus-20240229"
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=2000,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}]
            )
            
            claude_response = response.content[0].text.strip()
            
            # Parse JSON response
            try:
                if '[' in claude_response and ']' in claude_response:
                    start = claude_response.find('[')
                    end = claude_response.rfind(']') + 1
                    json_str = claude_response[start:end]
                    
                    ingredients = json.loads(json_str)
                    
                    if isinstance(ingredients, list) and all(isinstance(item, str) for item in ingredients):
                        return ingredients
                    else:
                        return []
                else:
                    return []
            except json.JSONDecodeError:
                return []
                
        except Exception as e:
            print(f"Error searching ingredients by product name: {e}")
            return []
    
    async def extract_ingredients_from_text(self, raw_text: str) -> List[str]:
        """
        Use Claude API to extract INCI ingredient names from scraped text
        
        Args:
            raw_text: Raw text scraped from the product page
            
        Returns:
            List of extracted INCI ingredient names
        """
        try:
            prompt = f"""
You are an expert cosmetic ingredient analyst. Your task is to extract INCI (International Nomenclature of Cosmetic Ingredients) names from the following text scraped from an e-commerce product page.

Please analyze the text and return ONLY a JSON array of INCI names in the exact format shown below.

Requirements:
1. Extract only valid INCI ingredient names
2. Remove any non-ingredient text, headers, descriptions, or marketing content
3. Clean up formatting (remove extra spaces, punctuation, brand names)
4. Return as a simple JSON array of strings
5. If no valid ingredients found, return empty array []
6. Focus on finding ingredient lists, composition sections, or INCI lists

Example output format:
["Water", "Glycerin", "Sodium Hyaluronate", "Hyaluronic Acid"]

Text to analyze:
{raw_text[:8000]}  # Limit to 8000 chars to avoid token limits

Return only the JSON array:"""

            # Get Claude client (lazy-loaded)
            claude_client = self._get_claude_client()
            
            # Call Claude API - use config model (defaults to claude-3-opus-20240229)
            from app.config import CLAUDE_MODEL
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else "claude-3-opus-20240229"
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=2000,
                temperature=0.1,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Extract response content
            claude_response = response.content[0].text.strip()
            
            # Try to parse JSON response
            try:
                # Clean up response to extract just the JSON part
                if '[' in claude_response and ']' in claude_response:
                    start = claude_response.find('[')
                    end = claude_response.rfind(']') + 1
                    json_str = claude_response[start:end]
                    
                    ingredients = json.loads(json_str)
                    
                    # Validate that we got a list of strings
                    if isinstance(ingredients, list) and all(isinstance(item, str) for item in ingredients):
                        return ingredients
                    else:
                        raise Exception("Invalid response format from Claude")
                else:
                    raise Exception("No JSON array found in Claude response")
                    
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse Claude response as JSON: {str(e)}")
                
        except Exception as e:
            raise Exception(f"Failed to extract ingredients with Claude: {str(e)}")
    
    async def extract_ingredients_from_url(self, url: str) -> Dict[str, any]:
        """
        Complete workflow: Scrape URL and extract ingredients
        Falls back to AI search if direct extraction fails
        
        Args:
            url: Product page URL
            
        Returns:
            Dict with 'ingredients' (List[str]), 'extracted_text' (str), 'platform' (str),
            'is_estimated' (bool), 'source' (str), 'product_name' (str)
        """
        try:
            # Scrape the URL
            scrape_result = await self.scrape_url(url)
            extracted_text = scrape_result["extracted_text"]
            
            # Try to extract ingredients using Claude
            ingredients = await self.extract_ingredients_from_text(extracted_text)
            
            # If extraction succeeded, return direct results
            if ingredients and len(ingredients) > 0:
                return {
                    "ingredients": ingredients,
                    "extracted_text": extracted_text,
                    "platform": scrape_result["platform"],
                    "url": url,
                    "is_estimated": False,
                    "source": "url_extraction",
                    "product_name": None
                }
            
            # If extraction failed, try fallback: detect product name and search
            print("Direct extraction failed, attempting fallback: detecting product name...")
            product_name = await self.detect_product_name(extracted_text, url)
            
            if product_name:
                print(f"Detected product name: {product_name}")
                print("Searching for ingredients using AI...")
                estimated_ingredients = await self.search_ingredients_by_product_name(product_name)
                
                if estimated_ingredients and len(estimated_ingredients) > 0:
                    return {
                        "ingredients": estimated_ingredients,
                        "extracted_text": extracted_text,
                        "platform": scrape_result["platform"],
                        "url": url,
                        "is_estimated": True,
                        "source": "ai_search",
                        "product_name": product_name
                    }
            
            # If fallback also failed, return empty
            return {
                "ingredients": [],
                "extracted_text": extracted_text,
                "platform": scrape_result["platform"],
                "url": url,
                "is_estimated": False,
                "source": "url_extraction",
                "product_name": product_name
            }
            
        except Exception as e:
            # If scraping failed, try to detect product from URL only
            print(f"Scraping failed: {e}, attempting product name detection from URL...")
            try:
                product_name = await self.detect_product_name("", url)
                if product_name:
                    estimated_ingredients = await self.search_ingredients_by_product_name(product_name)
                    if estimated_ingredients and len(estimated_ingredients) > 0:
                        return {
                            "ingredients": estimated_ingredients,
                            "extracted_text": f"Unable to scrape URL: {str(e)}",
                            "platform": self._detect_platform(url),
                            "url": url,
                            "is_estimated": True,
                            "source": "ai_search",
                            "product_name": product_name
                        }
            except:
                pass
            
            raise Exception(f"Failed to extract ingredients from URL: {str(e)}")

