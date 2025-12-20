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
        elif "thedermaco" in url_lower or "the-derma-co" in url_lower:
            return "thedermaco"
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
                
                # SECOND: Extract from Ingredients tab - try multiple ways to find it
                ingredients_found = False
                
                # Try multiple XPath patterns to find Ingredients tab
                ingredient_tab_patterns = [
                    "//h3[normalize-space()='Ingredients']",
                    "//h3[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]",
                    "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient') and (self::h3 or self::h4 or self::button or self::div[@role='button'])]",
                    "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]",
                    "//div[@role='button' and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]"
                ]
                
                for pattern in ingredient_tab_patterns:
                    try:
                        ingredients_tab = driver.find_element(By.XPATH, pattern)
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", ingredients_tab)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", ingredients_tab)
                        time.sleep(2)  # Wait longer for content to load
                        
                        # Wait for content to appear - try multiple selectors
                        content_selectors = [
                            (By.ID, "content-details"),
                            (By.CSS_SELECTOR, "[id*='content']"),
                            (By.CSS_SELECTOR, "[class*='content']"),
                            (By.CSS_SELECTOR, "[class*='ingredient']"),
                            (By.CSS_SELECTOR, "[id*='ingredient']")
                        ]
                        
                        content_element = None
                        for selector_type, selector_value in content_selectors:
                            try:
                                wait.until(EC.presence_of_element_located((selector_type, selector_value)))
                                content_element = driver.find_element(selector_type, selector_value)
                                break
                            except:
                                continue
                        
                        if content_element:
                            html = content_element.get_attribute("innerHTML")
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
                            if ingredients_text and len(ingredients_text) > 10:
                                text_parts.append(f"Ingredients:\n{ingredients_text}")
                                ingredients_found = True
                                print(f"Successfully extracted ingredients from tab: {ingredients_text[:100]}")
                                break
                    except Exception as e:
                        continue
                
                if not ingredients_found:
                    print(f"Could not extract Ingredients tab - tried {len(ingredient_tab_patterns)} patterns")
                
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
    
    async def _scrape_thedermaco(self, driver: webdriver.Chrome) -> str:
        """Scrape ingredients from The Derma Co product page - specific handler for their tab structure"""
        print("🚀 THE DERMA CO SCRAPER CALLED - Starting extraction...")
        try:
            await asyncio.sleep(2)  # Give JS time to render
            
            loop = asyncio.get_event_loop()
            
            def scrape():
                import time
                
                wait = WebDriverWait(driver, 15)
                text_parts = []
                
                print("🔍 The Derma Co: Looking for Ingredients List tab...")
                
                # The Derma Co uses h2 elements with class "cms-box" for tabs
                # Find the "Ingredients List" tab - MORE AGGRESSIVE SEARCH
                ingredient_tab = None
                
                # Try multiple ways to find the tab
                tab_selectors = [
                    # Method 1: XPath to find h2 containing "Ingredients"
                    ("//h2[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]", "h2 XPath"),
                    # Method 2: Any element containing "Ingredients List"
                    ("//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredients list')]", "any element with 'ingredients list'"),
                    ("//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient list')]", "any element with 'ingredient list'"),
                    # Method 3: Button or clickable element
                    ("//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]", "button with ingredient"),
                    ("//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]", "link with ingredient"),
                    # Method 4: Elements with role="tab"
                    ("//*[@role='tab' and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]", "tab role with ingredient"),
                    # Method 5: CSS selectors
                    ("h2.cms-box", "h2.cms-box CSS"),
                    ("h2[class*='cms-box']", "h2 with cms-box class"),
                    ("[class*='tab'][class*='ingredient']", "tab class with ingredient"),
                    ("[id*='ingredient'][id*='tab']", "id with ingredient and tab"),
                ]
                
                for selector, description in tab_selectors:
                    try:
                        if selector.startswith("//") or selector.startswith("("):
                            # XPath
                            tabs = driver.find_elements(By.XPATH, selector)
                        else:
                            # CSS selector
                            tabs = driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for tab in tabs:
                            if not tab.is_displayed():
                                continue
                            tab_text = tab.text.strip().lower()
                            # More flexible matching - just needs "ingredient" and "list" somewhere
                            if 'ingredient' in tab_text and 'list' in tab_text:
                                ingredient_tab = tab
                                print(f"✅ Found Ingredients List tab ({description}): {tab.text.strip()}")
                                break
                        if ingredient_tab:
                            break
                    except Exception as e:
                        print(f"   ⚠️ Selector '{description}' failed: {e}")
                        continue
                
                if not ingredient_tab:
                    print("⚠️ Could not find Ingredients List tab, trying to click ALL tabs/buttons to find ingredients...")
                    # Try clicking ALL clickable elements that might be tabs
                    try:
                        all_clickables = driver.find_elements(By.XPATH, "//h2 | //button | //a | //*[@role='tab'] | //*[contains(@class, 'tab')] | //*[contains(@class, 'cms-box')]")
                        print(f"   Found {len(all_clickables)} potential tab elements, trying to click them...")
                        for elem in all_clickables[:10]:  # Limit to first 10 to avoid too many clicks
                            try:
                                if not elem.is_displayed():
                                    continue
                                text = elem.text.strip().lower()
                                if 'ingredient' in text or 'list' in text or 'composition' in text:
                                    print(f"   Trying to click: {elem.text.strip()[:50]}")
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", elem)
                                    time.sleep(0.3)
                                    driver.execute_script("arguments[0].click();", elem)
                                    time.sleep(2)  # Wait for content to load
                            except:
                                continue
                    except Exception as e:
                        print(f"   ⚠️ Error trying all tabs: {e}")
                else:
                    # Click the tab
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", ingredient_tab)
                        time.sleep(0.5)
                        
                        # Click using JavaScript (more reliable)
                        driver.execute_script("arguments[0].click();", ingredient_tab)
                        print("✅ Clicked Ingredients List tab")
                        time.sleep(4)  # Wait longer for content to load
                        
                        # Also try regular click as backup
                        try:
                            ingredient_tab.click()
                            time.sleep(2)
                        except:
                            pass
                    except Exception as e:
                        print(f"⚠️ Error clicking tab: {e}")
                
                # Now extract the ingredient content
                print("🔍 Extracting ingredient content...")
                
                # Scroll to ensure all content is visible
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                
                # Method 1: Get all visible text and find the longest comma-separated line
                body_text = driver.find_element(By.TAG_NAME, "body").text
                lines = body_text.split('\n')
                
                print(f"   📊 Total body text: {len(body_text)} chars, {len(lines)} lines")
                
                # Find lines with many commas (ingredient lists)
                ingredient_lines = []
                for line in lines:
                    line_stripped = line.strip()
                    if ',' in line_stripped:
                        comma_count = line_stripped.count(',')
                        if comma_count >= 5:  # At least 6 ingredients
                            line_lower = line_stripped.lower()
                            # Check for ingredient indicators
                            if any(word in line_lower for word in ['aqua', 'water', 'acid', 'sodium', 'potassium', 'glycerin', 'ethyl', 'ferulic', 'hyaluronic', 'glycol', 'cellulose', 'citrate', 'benzoate']):
                                ingredient_lines.append((line_stripped, comma_count))
                                print(f"   📋 Found candidate line with {comma_count + 1} ingredients: {line_stripped[:100]}...")
                
                if ingredient_lines:
                    # Use the longest line (most ingredients)
                    longest_line, comma_count = max(ingredient_lines, key=lambda x: x[1])
                    text_parts.append(f"Complete Ingredients List:\n{longest_line}")
                    print(f"✅ Found ingredient list: {len(longest_line)} chars, ~{comma_count + 1} ingredients")
                    print(f"   Full list: {longest_line}")
                else:
                    print(f"   ⚠️ No long comma-separated lines found in body text")
                
                # Method 2: Look for elements containing "Aqua" and commas - MORE AGGRESSIVE (including hidden elements)
                try:
                    print("   🔍 Searching for elements containing 'Aqua' and commas (including hidden elements)...")
                    # Try multiple XPath patterns - check BOTH visible and hidden elements
                    xpath_patterns = [
                        "//*[contains(text(), 'Aqua') and contains(text(), ',')]",
                        "//*[contains(text(), 'aqua') and contains(text(), ',')]",
                        "//p[contains(text(), ',')]",
                        "//div[contains(text(), ',')]",
                        "//span[contains(text(), ',')]",
                        "//*[contains(@class, 'ingredient')]",
                        "//*[contains(@id, 'ingredient')]",
                        "//*[contains(@class, 'composition')]",
                        "//*[contains(@id, 'composition')]"
                    ]
                    
                    for xpath in xpath_patterns:
                        try:
                            all_elements = driver.find_elements(By.XPATH, xpath)
                            print(f"      Found {len(all_elements)} elements with pattern")
                            for elem in all_elements:
                                # Check BOTH visible text and innerHTML (for hidden elements)
                                text = elem.text.strip()
                                if not text or len(text) < 50:
                                    # Try innerHTML for hidden elements
                                    try:
                                        inner_html = elem.get_attribute('innerHTML') or elem.get_attribute('textContent') or ""
                                        if inner_html and len(inner_html) > len(text):
                                            # Parse HTML to get text
                                            from bs4 import BeautifulSoup
                                            soup = BeautifulSoup(inner_html, 'html.parser')
                                            text = soup.get_text().strip()
                                    except:
                                        pass
                                
                                if ',' in text and len(text) > 50:
                                    comma_count = text.count(',')
                                    if comma_count >= 10:  # At least 11 ingredients
                                        # Check if it starts with Aqua or Water or contains common ingredients
                                        text_lower = text.lower()
                                        if (text_lower.startswith(('aqua', 'water')) or 
                                            'aqua' in text_lower[:50] or
                                            any(word in text_lower for word in ['ethyl ascorbic', 'glycerin', 'sodium', 'potassium', 'citrate'])):
                                            # This looks like the full ingredient list
                                            if text not in [p.split('\n', 1)[-1] if '\n' in p else p for p in text_parts]:
                                                text_parts.append(f"Full Ingredients:\n{text}")
                                                print(f"✅ Found full ingredient list via element search: {len(text)} chars, {comma_count + 1} ingredients")
                                                print(f"   Full list: {text[:200]}...")
                                                break
                        except Exception as e:
                            print(f"      Error with pattern: {e}")
                            continue
                except Exception as e:
                    print(f"   ⚠️ Element search error: {e}")
                    import traceback
                    traceback.print_exc()
                
                # Method 3: Look for content after the clicked tab OR in any tab panel
                try:
                    # Try to find tab panels or content areas
                    tab_panel_selectors = [
                        "//*[@role='tabpanel']",
                        "//*[contains(@class, 'tab-content')]",
                        "//*[contains(@class, 'tabpanel')]",
                        "//*[contains(@id, 'tab')]",
                        "//*[contains(@class, 'cms-content')]",
                        "//*[contains(@class, 'product-details')]"
                    ]
                    
                    for selector in tab_panel_selectors:
                        try:
                            panels = driver.find_elements(By.XPATH, selector)
                            for panel in panels:
                                # Get text from panel (even if hidden)
                                text = panel.text.strip()
                                if not text:
                                    # Try innerHTML
                                    try:
                                        inner_html = panel.get_attribute('innerHTML') or ""
                                        if inner_html:
                                            from bs4 import BeautifulSoup
                                            soup = BeautifulSoup(inner_html, 'html.parser')
                                            text = soup.get_text().strip()
                                    except:
                                        pass
                                
                                if text and ',' in text:
                                    comma_count = text.count(',')
                                    if comma_count >= 10:
                                        text_lower = text.lower()
                                        if any(word in text_lower for word in ['aqua', 'water', 'ethyl', 'ascorbic', 'glycerin']):
                                            if text not in [p.split('\n', 1)[-1] if '\n' in p else p for p in text_parts]:
                                                text_parts.append(f"Tab Panel Content:\n{text}")
                                                print(f"✅ Found ingredients in tab panel: {len(text)} chars, {comma_count + 1} ingredients")
                                                print(f"   Preview: {text[:200]}...")
                                                break
                        except:
                            continue
                except Exception as e:
                    print(f"   ⚠️ Tab panel search error: {e}")
                
                # Method 4: Parse page source HTML directly for ingredient lists
                try:
                    print("   🔍 Parsing page source HTML for ingredient lists...")
                    page_source = driver.page_source
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(page_source, 'html.parser')
                    
                    # Find all text nodes that contain many commas
                    all_text = soup.get_text()
                    lines = all_text.split('\n')
                    for line in lines:
                        line_stripped = line.strip()
                        if ',' in line_stripped:
                            comma_count = line_stripped.count(',')
                            if comma_count >= 15:  # At least 16 ingredients (more strict)
                                line_lower = line_stripped.lower()
                                if any(word in line_lower for word in ['aqua', 'water', 'ethyl ascorbic', 'glycerin', 'sodium', 'potassium']):
                                    if line_stripped not in [p.split('\n', 1)[-1] if '\n' in p else p for p in text_parts]:
                                        text_parts.append(f"HTML Source Ingredients:\n{line_stripped}")
                                        print(f"✅ Found ingredient list in HTML source: {len(line_stripped)} chars, {comma_count + 1} ingredients")
                                        print(f"   Full list: {line_stripped}")
                                        break
                except Exception as e:
                    print(f"   ⚠️ HTML source parsing error: {e}")
                
                # Combine results
                if text_parts:
                    result = "\n\n".join(text_parts)
                    print(f"✅ The Derma Co extraction complete: {len(result)} chars")
                    # CRITICAL: Make sure we have the full ingredient list
                    # Check if result contains a long comma-separated list
                    for part in text_parts:
                        if 'Ingredients List' in part or 'Complete Ingredients' in part or 'Full Ingredients' in part:
                            # Extract just the ingredient list part
                            lines = part.split('\n')
                            for line in lines:
                                if ',' in line and line.count(',') >= 10:
                                    print(f"🎯 FOUND COMPLETE INGREDIENT LIST: {line.count(',') + 1} ingredients")
                                    print(f"   List: {line}")
                                    # Return this as the primary content
                                    return f"Complete Ingredients List:\n{line}\n\n{result}"
                    return result
                else:
                    # Fallback to body text - but try to extract ingredient list from it
                    print("⚠️ No specific ingredient content found, searching body text for ingredient list...")
                    # Look for the longest comma-separated line in body text
                    longest_ingredient_line = None
                    max_commas = 0
                    for line in lines:
                        line_stripped = line.strip()
                        if ',' in line_stripped:
                            comma_count = line_stripped.count(',')
                            if comma_count > max_commas:
                                line_lower = line_stripped.lower()
                                if any(word in line_lower for word in ['aqua', 'water', 'ethyl', 'acid', 'sodium']):
                                    longest_ingredient_line = line_stripped
                                    max_commas = comma_count
                    
                    if longest_ingredient_line and max_commas >= 10:
                        print(f"🎯 FOUND INGREDIENT LIST IN BODY TEXT: {max_commas + 1} ingredients")
                        print(f"   List: {longest_ingredient_line}")
                        return f"Complete Ingredients List:\n{longest_ingredient_line}"
                    
                    return body_text[:10000]
            
            return await loop.run_in_executor(None, scrape)
        except Exception as e:
            print(f"Error scraping The Derma Co: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to generic
            return await self._scrape_generic(driver)
    
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
                
                # FIRST: Try to find and click tabs that contain ingredient-related keywords
                # Many sites (like thedermaco.com) use tabs for ingredients
                ingredient_keywords = [
                    "ingredient", "ingredients", "key ingredient", "key ingredients",
                    "inci", "composition", "formula", "formulation", "contains",
                    "ingredient list", "full ingredient", "all ingredients", "ingredient list",
                    "ingredients list", "complete ingredients", "full ingredient list"
                ]
                
                # Try to find tab elements first (common pattern: tabs, buttons with tab role, etc.)
                try:
                    # Look for tab elements
                    tab_selectors = [
                        "[role='tab']", "[class*='tab']", "[class*='Tab']",
                        "button[class*='tab']", "a[class*='tab']",
                        "[data-tab]", "[aria-controls]", "[class*='nav-tab']"
                    ]
                    
                    for selector in tab_selectors:
                        try:
                            tabs = driver.find_elements(By.CSS_SELECTOR, selector)
                            for tab in tabs:
                                try:
                                    tab_text = tab.text.strip().lower()
                                    if any(keyword in tab_text for keyword in ingredient_keywords):
                                        # Scroll and click the tab
                                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", tab)
                                        time.sleep(0.5)
                                        
                                        # Get tab's aria-controls or data-target to find the content panel
                                        aria_controls = tab.get_attribute("aria-controls")
                                        data_target = tab.get_attribute("data-target") or tab.get_attribute("data-bs-target")
                                        
                                        try:
                                            driver.execute_script("arguments[0].click();", tab)
                                            print(f"✅ Clicked ingredient tab: {tab.text.strip()[:50]}")
                                            
                                            # Wait for content to load - check if we have a target panel
                                            if aria_controls or data_target:
                                                # Wait for the panel to become visible
                                                panel_id = aria_controls or data_target.lstrip('#')
                                                try:
                                                    wait.until(EC.visibility_of_element_located((By.ID, panel_id)))
                                                    print(f"   Panel {panel_id} is now visible")
                                                except:
                                                    pass
                                            
                                            time.sleep(4)  # Wait longer for dynamic content to load
                                            
                                            # Try multiple methods to find and extract the tab panel content
                                            panel_found = False
                                            
                                            # Method 1: Use aria-controls or data-target
                                            if aria_controls or data_target:
                                                panel_id = aria_controls or data_target.lstrip('#')
                                                try:
                                                    panel = driver.find_element(By.ID, panel_id)
                                                    if panel.is_displayed():
                                                        panel_text = panel.text.strip()
                                                        if panel_text and len(panel_text) > 20:
                                                            text_parts.append(f"Tab Content ({tab.text.strip()}):\n{panel_text}")
                                                            print(f"   ✅ Extracted {len(panel_text)} chars from tab panel (ID: {panel_id})")
                                                            panel_found = True
                                                except:
                                                    pass
                                            
                                            # Method 2: Find active/visible tab panel by class or attributes
                                            if not panel_found:
                                                try:
                                                    # Look for active tab panels
                                                    active_panel_selectors = [
                                                        "[role='tabpanel'][aria-hidden='false']",
                                                        "[class*='tab-panel'][class*='active']",
                                                        "[class*='tab-content'][class*='active']",
                                                        "[class*='tab-pane'][class*='active']",
                                                        "[class*='tabpanel'][class*='show']",
                                                        "[class*='tab-content'][class*='show']",
                                                        "[aria-expanded='true']"
                                                    ]
                                                    
                                                    for panel_selector in active_panel_selectors:
                                                        try:
                                                            panels = driver.find_elements(By.CSS_SELECTOR, panel_selector)
                                                            for panel in panels:
                                                                if panel.is_displayed():
                                                                    panel_text = panel.text.strip()
                                                                    if panel_text and len(panel_text) > 20:
                                                                        # Check if this looks like ingredient content
                                                                        if any(keyword in panel_text.lower() for keyword in ingredient_keywords) or ',' in panel_text:
                                                                            text_parts.append(f"Tab Content ({tab.text.strip()}):\n{panel_text}")
                                                                            print(f"   ✅ Extracted {len(panel_text)} chars from active tab panel")
                                                                            panel_found = True
                                                                            break
                                                        except:
                                                            continue
                                                    if panel_found:
                                                        break
                                                except:
                                                    pass
                                            
                                            # Method 3: Find panel by looking for elements near the clicked tab
                                            if not panel_found:
                                                try:
                                                    # Get the tab's parent container and look for sibling panels
                                                    tab_parent = tab.find_element(By.XPATH, "./ancestor::*[contains(@class, 'tab') or contains(@class, 'nav')][1]")
                                                    # Look for visible content divs/panels in the same container
                                                    sibling_panels = tab_parent.find_elements(By.XPATH, ".//*[contains(@class, 'tab-panel') or contains(@class, 'tab-content') or contains(@class, 'tab-pane')]")
                                                    for panel in sibling_panels:
                                                        if panel.is_displayed():
                                                            panel_text = panel.text.strip()
                                                            if panel_text and len(panel_text) > 20:
                                                                text_parts.append(f"Tab Content ({tab.text.strip()}):\n{panel_text}")
                                                                print(f"   ✅ Extracted {len(panel_text)} chars from sibling panel")
                                                                panel_found = True
                                                                break
                                                except:
                                                    pass
                                            
                                            # Method 4: Use innerHTML to get raw HTML content (sometimes text doesn't capture everything)
                                            if not panel_found:
                                                try:
                                                    # Find any visible element that contains ingredient keywords
                                                    all_elements = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'ingredient')]")
                                                    for elem in all_elements:
                                                        if elem.is_displayed():
                                                            # Get parent container that likely has the full content
                                                            parent = elem.find_element(By.XPATH, "./ancestor::*[contains(@class, 'tab') or contains(@class, 'panel') or contains(@class, 'content')][1]")
                                                            if parent:
                                                                parent_text = parent.text.strip()
                                                                if parent_text and len(parent_text) > 50 and ',' in parent_text:
                                                                    text_parts.append(f"Tab Content (Found via keyword):\n{parent_text}")
                                                                    print(f"   ✅ Extracted {len(parent_text)} chars from keyword-based search")
                                                                    panel_found = True
                                                                    break
                                                except:
                                                    pass
                                            
                                        except Exception as e:
                                            try:
                                                tab.click()
                                                time.sleep(3)
                                            except:
                                                print(f"   ⚠️ Could not click tab: {e}")
                                                pass
                                except:
                                    continue
                        except:
                            continue
                except Exception as e:
                    print(f"Error clicking tabs: {e}")
                
                # SECOND: Try to click on accordions/buttons that contain ingredient-related keywords
                
                clicked_elements = set()  # Track clicked elements to avoid duplicates
                
                try:
                    # Scroll through the page to find accordion elements
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    
                    # Find all clickable elements that might be accordions/buttons
                    # Look for buttons, divs, spans, h3, h4, etc. that contain ingredient keywords
                    selectors_to_try = [
                        "button", "div[role='button']", "a[role='button']",
                        "h3", "h4", "h5", "h6", "[class*='accordion']", "[class*='Accordion']",
                        "[class*='collapse']", "[class*='expand']", "[class*='toggle']",
                        "[aria-expanded]", "[data-toggle]", "[data-target]",
                        "[class*='tab']", "[class*='Tab']", "[role='tab']",
                        "[class*='section']", "[class*='Section']", "[class*='panel']",
                        "summary", "[class*='details']", "[class*='Details']"
                    ]
                    
                    for selector in selectors_to_try:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                try:
                                    # Get element text and check if it contains ingredient keywords
                                    element_text = element.text.strip().lower()
                                    element_id = element.id or element.get_attribute("id") or ""
                                    
                                    # Also check aria-label, title, and data attributes
                                    aria_label = (element.get_attribute("aria-label") or "").lower()
                                    title = (element.get_attribute("title") or "").lower()
                                    data_label = (element.get_attribute("data-label") or "").lower()
                                    
                                    # Skip if already clicked
                                    if element_id in clicked_elements:
                                        continue
                                    
                                    # Check if element text or attributes contain ingredient keywords
                                    text_to_check = f"{element_text} {aria_label} {title} {data_label}"
                                    if any(keyword in text_to_check for keyword in ingredient_keywords):
                                        # Scroll element into view
                                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                        time.sleep(0.5)
                                        
                                        # Try to click the element
                                        try:
                                            # Try JavaScript click first (more reliable)
                                            driver.execute_script("arguments[0].click();", element)
                                            clicked_elements.add(element_id)
                                            print(f"Clicked accordion/button: {element_text[:50] or aria_label[:50] or title[:50]}")
                                            time.sleep(2)  # Wait longer for content to expand
                                        except:
                                            # Try regular click as fallback
                                            try:
                                                element.click()
                                                clicked_elements.add(element_id)
                                                print(f"Clicked accordion/button (regular): {element_text[:50] or aria_label[:50] or title[:50]}")
                                                time.sleep(2)
                                            except:
                                                pass
                                except:
                                    continue
                        except:
                            continue
                    
                    # Also try XPath to find elements containing ingredient keywords (case-insensitive)
                    for keyword in ingredient_keywords:
                        try:
                            # Try multiple XPath patterns to find elements with ingredient keywords
                            xpath_patterns = [
                                f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]",
                                f"//*[contains(translate(@aria-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]",
                                f"//*[contains(translate(@title, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]",
                                f"//*[contains(translate(@data-label, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]"
                            ]
                            
                            for xpath in xpath_patterns:
                                try:
                                    elements = driver.find_elements(By.XPATH, xpath)
                                    for element in elements:
                                        try:
                                            element_id = element.id or element.get_attribute("id") or ""
                                            if element_id in clicked_elements:
                                                continue
                                            
                                            # Check if it's a clickable element
                                            tag_name = element.tag_name.lower()
                                            if tag_name in ['button', 'a', 'div', 'span', 'h3', 'h4', 'h5', 'h6', 'summary']:
                                                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                                                time.sleep(0.5)
                                                try:
                                                    driver.execute_script("arguments[0].click();", element)
                                                    clicked_elements.add(element_id)
                                                    print(f"Clicked element via XPath: {keyword}")
                                                    time.sleep(2)  # Wait longer for content
                                                except:
                                                    try:
                                                        element.click()
                                                        clicked_elements.add(element_id)
                                                        print(f"Clicked element via XPath (regular): {keyword}")
                                                        time.sleep(2)
                                                    except:
                                                        pass
                                        except:
                                            continue
                                except:
                                    continue
                        except:
                            continue
                    
                except Exception as e:
                    print(f"Error clicking accordions: {e}")
                
                # THIRD: Extract text from the page (after clicking accordions)
                try:
                    # Wait longer for all accordions to expand and content to load
                    time.sleep(5)  # Increased wait time for dynamic content
                    
                    # Scroll to ensure all content is loaded
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    
                    # FIRST: Try to find ingredient content directly using more specific selectors
                    # Look for common patterns where ingredients are actually displayed
                    ingredient_content_selectors = [
                        # Common ingredient list patterns
                        "[class*='ingredient'] p", "[class*='ingredient'] div",
                        "[id*='ingredient'] p", "[id*='ingredient'] div",
                        "[class*='ingredient-list']", "[id*='ingredient-list']",
                        "[class*='ingredients-list']", "[id*='ingredients-list']",
                        "[data-tab-content*='ingredient']", "[aria-labelledby*='ingredient']",
                        # Tab panel content
                        "[role='tabpanel'][aria-hidden='false']",
                        "[class*='tab-content'][class*='active']",
                        "[class*='tab-panel'][class*='active']",
                        # Expanded accordion content
                        "[class*='accordion'][class*='active']",
                        "[class*='collapse'][class*='show']",
                        "[aria-expanded='true']",
                        # Generic content areas that might contain ingredients
                        "[class*='product-details']", "[class*='product-info']",
                        "[class*='description']", "[class*='content']"
                    ]
                    
                    for selector in ingredient_content_selectors:
                        try:
                            elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for element in elements:
                                # Check if element is visible
                                if not element.is_displayed():
                                    continue
                                    
                                text = element.text.strip()
                                text_lower = text.lower()
                                
                                # Check if this looks like ingredient content
                                # Ingredients typically contain commas, percentages, or common ingredient words
                                has_ingredient_indicators = (
                                    ',' in text or  # Ingredients are usually comma-separated
                                    any(word in text_lower for word in ['water', 'glycerin', 'acid', 'extract', 'oil', 'alcohol', 'paraben', 'sulfate']) or
                                    len(text) > 50  # Reasonable length for ingredient list
                                )
                                
                                if text and len(text) > 20 and has_ingredient_indicators:
                                    # Check if it contains ingredient keywords
                                    if any(keyword in text_lower for keyword in ["ingredient", "composition", "formula", "inci", "contains"]):
                                        text_parts.append(f"Ingredients Section:\n{text}")
                                        print(f"✅ Found ingredient content via selector: {selector[:50]} ({len(text)} chars)")
                                    elif ',' in text and len(text.split(',')) > 3:  # Looks like a comma-separated list
                                        text_parts.append(f"Possible Ingredients:\n{text}")
                                        print(f"✅ Found possible ingredient list via selector: {selector[:50]} ({len(text)} chars)")
                        except Exception as e:
                            continue
                    
                    # SECOND: Before getting body text, try one more comprehensive extraction
                    # Look for any visible element that contains a long comma-separated list
                    try:
                        print("🔍 Performing comprehensive ingredient list search...")
                        # Find all visible text elements
                        all_text_elements = driver.find_elements(By.XPATH, "//*[text()[contains(., ',')]]")
                        for elem in all_text_elements:
                            if not elem.is_displayed():
                                continue
                            
                            text = elem.text.strip()
                            # Check if this looks like an ingredient list (comma-separated, reasonable length)
                            if text and ',' in text and 50 < len(text) < 2000:
                                # Count commas - ingredient lists usually have many
                                comma_count = text.count(',')
                                if comma_count >= 5:  # At least 5 commas suggests a real ingredient list
                                    # Check for common ingredient indicators
                                    text_lower = text.lower()
                                    has_ingredient_words = any(word in text_lower for word in [
                                        'aqua', 'water', 'acid', 'alcohol', 'glycerin', 'extract', 
                                        'sodium', 'potassium', 'citrate', 'benzoate', 'paraben'
                                    ])
                                    
                                    if has_ingredient_words:
                                        # Get the full parent container to ensure we have the complete list
                                        try:
                                            parent = elem.find_element(By.XPATH, "./ancestor::*[contains(@class, 'tab') or contains(@class, 'panel') or contains(@class, 'content') or contains(@class, 'ingredient')][1]")
                                            if parent:
                                                parent_text = parent.text.strip()
                                                # Use parent if it's longer and contains the element text
                                                if parent_text and len(parent_text) > len(text) and text in parent_text:
                                                    if parent_text not in text_parts:
                                                        text_parts.append(f"Comprehensive Ingredient List:\n{parent_text}")
                                                        print(f"   ✅ Found comprehensive list: {len(parent_text)} chars, {comma_count+1} ingredients")
                                                        break
                                        except:
                                            # Use element text directly
                                            if text not in text_parts:
                                                text_parts.append(f"Comprehensive Ingredient List:\n{text}")
                                                print(f"   ✅ Found ingredient list: {len(text)} chars, {comma_count+1} ingredients")
                                                break
                    except Exception as e:
                        print(f"   ⚠️ Error in comprehensive search: {e}")
                    
                    # THIRD: Get all text content and parse for ingredient sections
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                    
                    # Look for sections with ingredient keywords
                    keywords = ["ingredient", "composition", "formula", "formulation", "contains", "inci", "all ingredients"]
                    lines = body_text.split("\n")
                    relevant_lines = []
                    in_ingredient_section = False
                    
                    for line in lines:
                        line_lower = line.lower()
                        line_stripped = line.strip()
                        
                        # Skip empty lines
                        if not line_stripped:
                            continue
                            
                        # Check if this line starts an ingredient section
                        if any(keyword in line_lower for keyword in keywords):
                            in_ingredient_section = True
                            relevant_lines.append(line_stripped)
                        elif in_ingredient_section:
                            # Continue collecting lines until we hit a new section
                            # Stop if we hit another header-like section (all caps, or contains common section keywords)
                            if (line_stripped.isupper() and len(line_stripped) > 5) or any(stop_word in line_lower for stop_word in ["description", "benefits", "how to use", "directions", "warnings", "price", "reviews", "rating", "add to cart", "buy now"]):
                                # But if it's still ingredient-related, continue
                                if not any(ing_keyword in line_lower for ing_keyword in keywords):
                                    break
                            relevant_lines.append(line_stripped)
                            if len(relevant_lines) > 200:  # Increased limit for longer ingredient lists
                                break
                    
                    if relevant_lines:
                        ingredient_text = "\n".join(relevant_lines)
                        # Only add if it looks like actual ingredients (has commas or multiple items)
                        if ',' in ingredient_text or len(relevant_lines) > 3:
                            text_parts.append(ingredient_text)
                            print(f"✅ Found ingredient section in body text ({len(ingredient_text)} chars)")
                    
                    # Also get visible text from expanded sections
                    try:
                        # Look for common ingredient section selectors (more comprehensive)
                        ingredient_selectors = [
                            "[class*='ingredient']", "[id*='ingredient']",
                            "[class*='composition']", "[id*='composition']",
                            "[class*='inci']", "[id*='inci']",
                            "[class*='Ingredients']", "[id*='Ingredients']",
                            "[data-tab-content*='ingredient']", "[aria-labelledby*='ingredient']",
                            "[class*='formula']", "[id*='formula']", "[class*='formulation']", "[id*='formulation']",
                            "[class*='ingredient-list']", "[id*='ingredient-list']",
                            "[class*='ingredients-list']", "[id*='ingredients-list']",
                            "[data-content*='ingredient']", "[data-section*='ingredient']"
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
                        
                        # Also try to find tab panel content after clicking tabs - MORE COMPREHENSIVE
                        tab_panel_selectors = [
                            "[role='tabpanel']", 
                            "[class*='tab-panel']", "[class*='tabPanel']",
                            "[class*='tab-content']", "[id*='tab-content']", "[id*='tabpanel']",
                            "[class*='tab-pane']", "[class*='tabPane']",
                            "[class*='panel-body']", "[class*='tab-body']"
                        ]
                        
                        for selector in tab_panel_selectors:
                            try:
                                panels = driver.find_elements(By.CSS_SELECTOR, selector)
                                for panel in panels:
                                    # Check if this panel is visible (active tab)
                                    is_visible = panel.is_displayed()
                                    if is_visible:
                                        # Get both text and innerHTML to ensure we capture everything
                                        text = panel.text.strip()
                                        
                                        # Also try to get innerHTML for better extraction
                                        try:
                                            html_content = panel.get_attribute("innerHTML")
                                            if html_content:
                                                # Parse HTML to get text (sometimes text property misses content)
                                                from bs4 import BeautifulSoup
                                                soup = BeautifulSoup(html_content, "html.parser")
                                                html_text = soup.get_text(separator=" ", strip=True)
                                                if html_text and len(html_text) > len(text):
                                                    text = html_text
                                        except:
                                            pass
                                        
                                        if text and len(text) > 20:
                                            # Check if it contains ingredient-related content
                                            text_lower = text.lower()
                                            has_ingredient_keyword = any(keyword in text_lower for keyword in ingredient_keywords)
                                            looks_like_ingredients = ',' in text and len(text.split(',')) > 3
                                            
                                            if has_ingredient_keyword or looks_like_ingredients:
                                                # Avoid duplicates
                                                if text not in text_parts:
                                                    text_parts.append(text)
                                                    print(f"✅ Found ingredient panel content: {len(text)} chars")
                            except:
                                continue
                        
                        # Also try to find content by looking for elements that contain comma-separated lists
                        # This catches ingredient lists that might not have ingredient keywords nearby
                        try:
                            all_paragraphs = driver.find_elements(By.CSS_SELECTOR, "p, div, span, li")
                            for elem in all_paragraphs:
                                if not elem.is_displayed():
                                    continue
                                    
                                text = elem.text.strip()
                                # Look for comma-separated lists that look like ingredients
                                if text and ',' in text and len(text.split(',')) >= 5:
                                    # Check if it contains common ingredient words
                                    text_lower = text.lower()
                                    ingredient_indicators = ['acid', 'alcohol', 'water', 'aqua', 'glycerin', 'extract', 'oil', 'sodium', 'potassium']
                                    if any(indicator in text_lower for indicator in ingredient_indicators):
                                        # Check if parent is in a tab/panel area
                                        try:
                                            parent = elem.find_element(By.XPATH, "./ancestor::*[contains(@class, 'tab') or contains(@class, 'panel') or contains(@class, 'content')][1]")
                                            if parent and parent.is_displayed():
                                                # Get full parent text (might be the complete list)
                                                parent_text = parent.text.strip()
                                                if parent_text and len(parent_text) > len(text):
                                                    if parent_text not in text_parts:
                                                        text_parts.append(parent_text)
                                                        print(f"✅ Found ingredient list in paragraph: {len(parent_text)} chars")
                                                        break
                                        except:
                                            # If no parent found, use the element text itself
                                            if text not in text_parts and len(text) > 50:
                                                text_parts.append(text)
                                                print(f"✅ Found ingredient list directly: {len(text)} chars")
                                                break
                        except:
                            pass
                    except:
                        pass
                    
                except Exception as e:
                    print(f"Error extracting text: {e}")
                
                # FOURTH: Fallback - get body text if nothing found
                if not text_parts:
                    try:
                        body_text = driver.find_element(By.TAG_NAME, "body").text
                        # Return first 8000 characters (increased for better extraction)
                        return body_text[:8000]
                    except:
                        return ""
                
                # Combine all text parts
                result = "\n\n".join(text_parts) if text_parts else ""
                
                # Debug: Log what we extracted
                print(f"📊 Extraction summary: {len(text_parts)} sections, {len(result)} total characters")
                if text_parts:
                    for i, part in enumerate(text_parts[:3]):  # Show first 3 parts
                        print(f"   Part {i+1}: {len(part)} chars - {part[:100]}...")
                
                if not result or len(result.strip()) < 10:
                    # Final fallback - try to get more comprehensive body text
                    print("⚠️ No ingredient content found, using comprehensive body text extraction...")
                    try:
                        # Try to get text from all visible elements, not just body
                        all_text_parts = []
                        
                        # Get text from main content areas
                        content_selectors = [
                            "main", "[role='main']", 
                            "[class*='product']", "[class*='content']",
                            "[class*='details']", "[class*='description']"
                        ]
                        
                        for selector in content_selectors:
                            try:
                                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                for elem in elements:
                                    if elem.is_displayed():
                                        text = elem.text.strip()
                                        if text and len(text) > 50:
                                            all_text_parts.append(text)
                            except:
                                continue
                        
                        if all_text_parts:
                            body_text = "\n\n".join(all_text_parts)
                            print(f"✅ Extracted {len(body_text)} chars from content areas")
                            return body_text[:10000]  # Return more content
                        else:
                            body_text = driver.find_element(By.TAG_NAME, "body").text
                            print(f"✅ Extracted {len(body_text)} chars from body")
                            return body_text[:10000]  # Return more content
                    except Exception as e:
                        print(f"❌ Error in fallback extraction: {e}")
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
            elif platform == "thedermaco":
                print(f"🎯 Using The Derma Co specific scraper")
                extracted_text = await self._scrape_thedermaco(driver)
                print(f"📊 The Derma Co scraper returned {len(extracted_text)} chars")
            else:
                extracted_text = await self._scrape_generic(driver)
            
            if not extracted_text or len(extracted_text.strip()) < 10:
                raise Exception("No meaningful text extracted from the page")
            
            print(f"Extracted {len(extracted_text)} characters of text")
            
            # Extract product image
            product_image = await self.extract_product_image(driver, url)
            
            return {
                "extracted_text": extracted_text,
                "platform": platform,
                "url": url,
                "product_image": product_image
            }
            
        except WebDriverException as e:
            raise Exception(f"Selenium WebDriver error: {str(e)}. Make sure ChromeDriver is installed.")
        except Exception as e:
            raise Exception(f"Failed to scrape URL: {str(e)}")
        finally:
            # Don't close driver here - keep it for reuse
            pass
    
    async def extract_product_image(self, driver: webdriver.Chrome, url: str) -> Optional[str]:
        """
        Extract product image URL from the page using Selenium
        
        Args:
            driver: Selenium WebDriver instance
            url: The product URL (for platform detection)
            
        Returns:
            Image URL string or None if not found
        """
        try:
            loop = asyncio.get_event_loop()
            
            def extract():
                image_urls = set()
                candidate_images = []  # Store images with metadata for better selection
                
                try:
                    # Method 1: Look for common product image selectors (most reliable)
                    product_image_selectors = [
                        # Nykaa specific
                        'img[class*="product-image"]',
                        'img[class*="ProductImage"]',
                        'img[class*="product-img"]',
                        '[class*="product-image"] img',
                        '[class*="ProductImage"] img',
                        # Amazon specific
                        '#landingImage',
                        '#main-image',
                        '#imgBlkFront',
                        '[data-a-image-name="landingImage"]',
                        # Flipkart specific
                        'img[class*="_396cs4"]',
                        '[class*="product-image"] img',
                        # Generic product image containers
                        '[class*="product-gallery"] img',
                        '[class*="product-slider"] img',
                        '[class*="main-image"] img',
                        '[id*="product-image"] img',
                        '[id*="main-image"] img',
                        '[data-testid*="product-image"]',
                        '[data-testid*="main-image"]',
                    ]
                    
                    for selector in product_image_selectors:
                        try:
                            imgs = driver.find_elements(By.CSS_SELECTOR, selector)
                            for img in imgs[:5]:  # Limit to first 5 matches per selector
                                try:
                                    src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                                    srcset = img.get_attribute('srcset') or ''
                                    
                                    # Collect all candidate URLs
                                    candidates = []
                                    if src and src.startswith(('http://', 'https://', '//')):
                                        candidates.append(src)
                                    if srcset:
                                        # Parse srcset (format: "url1 size1, url2 size2")
                                        for item in srcset.split(','):
                                            url_part = item.strip().split(' ')[0]
                                            if url_part and url_part.startswith(('http://', 'https://', '//')):
                                                candidates.append(url_part)
                                    
                                    for candidate_url in candidates:
                                        if candidate_url:
                                            # Convert protocol-relative URLs
                                            if candidate_url.startswith('//'):
                                                candidate_url = 'https:' + candidate_url
                                            
                                            # Filter out placeholders, logos, icons
                                            if not any(exclude in candidate_url.lower() for exclude in [
                                                'placeholder', 'logo', 'icon', 'avatar', 'banner', 
                                                'spinner', 'loading', 'default', 'no-image', 'not-found'
                                            ]):
                                                # Get image dimensions for prioritization
                                                try:
                                                    width = img.size.get('width', 0)
                                                    height = img.size.get('height', 0)
                                                    area = width * height
                                                except:
                                                    area = 0
                                                
                                                clean_url = candidate_url.split('?')[0]
                                                if clean_url and clean_url not in image_urls:
                                                    image_urls.add(clean_url)
                                                    candidate_images.append({
                                                        'url': clean_url,
                                                        'area': area,
                                                        'has_product_keyword': 'product' in clean_url.lower()
                                                    })
                                except Exception as e:
                                    continue
                        except Exception as e:
                            continue
                    
                    # Method 2: Comprehensive extraction - get all images and filter intelligently
                    if not image_urls:
                        try:
                            imgs = driver.find_elements(By.CSS_SELECTOR, 'img[src], img[data-src], source[srcset]')
                            for img in imgs:
                                try:
                                    src = img.get_attribute('src') or img.get_attribute('data-src') or ''
                                    srcset = img.get_attribute('srcset') or ''
                                    
                                    candidates = []
                                    if src and src.startswith(('http://', 'https://', '//')):
                                        candidates.append(src)
                                    if srcset:
                                        for item in srcset.split(','):
                                            url_part = item.strip().split(' ')[0]
                                            if url_part and url_part.startswith(('http://', 'https://', '//')):
                                                candidates.append(url_part)
                                    
                                    for candidate_url in candidates:
                                        if candidate_url:
                                            # Convert protocol-relative URLs
                                            if candidate_url.startswith('//'):
                                                candidate_url = 'https:' + candidate_url
                                            
                                            # More lenient filtering - exclude only obvious non-product images
                                            exclude_patterns = [
                                                'placeholder', 'logo', 'icon', 'avatar', 'banner',
                                                'spinner', 'loading', 'default', 'no-image', 'not-found',
                                                'social', 'share', 'facebook', 'twitter', 'instagram',
                                                'favicon', 'sprite', 'advertisement', 'ad-'
                                            ]
                                            
                                            # Check if URL looks like a product image
                                            url_lower = candidate_url.lower()
                                            is_likely_product = (
                                                # Has image extension
                                                any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']) or
                                                # Contains product-related keywords
                                                any(keyword in url_lower for keyword in ['product', 'catalog', 'item', 'sku']) or
                                                # Is from known e-commerce domains
                                                any(domain in url_lower for domain in ['nykaa', 'amazon', 'flipkart', 'myntra', 'purplle'])
                                            )
                                            
                                            if is_likely_product and not any(exclude in url_lower for exclude in exclude_patterns):
                                                try:
                                                    width = img.size.get('width', 0)
                                                    height = img.size.get('height', 0)
                                                    area = width * height
                                                except:
                                                    area = 0
                                                
                                                clean_url = candidate_url.split('?')[0]
                                                if clean_url and clean_url not in image_urls:
                                                    image_urls.add(clean_url)
                                                    candidate_images.append({
                                                        'url': clean_url,
                                                        'area': area,
                                                        'has_product_keyword': 'product' in clean_url.lower()
                                                    })
                                except Exception as e:
                                    continue
                        except Exception as e:
                            print(f"Error in comprehensive image extraction: {e}")
                    
                    # Method 3: Fallback - simpler extraction for product images
                    if not image_urls:
                        try:
                            img_elements = driver.find_elements(By.CSS_SELECTOR, 'img[src], img[data-src]')
                            for img in img_elements[:20]:  # Check first 20 images
                                try:
                                    src = img.get_attribute('src') or img.get_attribute('data-src')
                                    if src and src.startswith(('http://', 'https://', '//')):
                                        if src.startswith('//'):
                                            src = 'https:' + src
                                        
                                        # Very basic filtering - just exclude obvious non-images
                                        if not any(exclude in src.lower() for exclude in [
                                            'logo', 'icon', 'favicon', 'spinner', 'loading'
                                        ]):
                                            # Check if it's a reasonable size (likely a product image)
                                            try:
                                                width = img.size.get('width', 0)
                                                height = img.size.get('height', 0)
                                                if width > 100 and height > 100:  # Reasonable minimum size
                                                    clean_url = src.split('?')[0]
                                                    if clean_url:
                                                        image_urls.add(clean_url)
                                                        candidate_images.append({
                                                            'url': clean_url,
                                                            'area': width * height,
                                                            'has_product_keyword': 'product' in clean_url.lower()
                                                        })
                                            except:
                                                # If we can't get size, still consider it
                                                clean_url = src.split('?')[0]
                                                if clean_url:
                                                    image_urls.add(clean_url)
                                                    candidate_images.append({
                                                        'url': clean_url,
                                                        'area': 0,
                                                        'has_product_keyword': 'product' in clean_url.lower()
                                                    })
                                except Exception as e:
                                    continue
                        except Exception as e:
                            print(f"Error in fallback image extraction: {e}")
                    
                    # Select the best image
                    if candidate_images:
                        # Sort by: 1) has product keyword, 2) larger area
                        candidate_images.sort(key=lambda x: (
                            x['has_product_keyword'],
                            x['area']
                        ), reverse=True)
                        
                        selected = candidate_images[0]['url']
                        print(f"Selected product image: {selected}")
                        return selected
                    
                    # Fallback: return first image if we have any
                    if image_urls:
                        selected = list(image_urls)[0]
                        print(f"Selected first available image: {selected}")
                        return selected
                    
                    print("No product image found")
                    return None
                    
                except Exception as e:
                    print(f"Error extracting product image: {e}")
                    import traceback
                    traceback.print_exc()
                    return None
            
            return await loop.run_in_executor(None, extract)
        except Exception as e:
            print(f"Error in extract_product_image: {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else (os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929")
            
            # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
            max_tokens = 4096 if "claude-3-opus-20240229" in model_name else 8192
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
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
    
    async def search_ingredients_by_product_name(self, product_name: str, url: str = None) -> List[str]:
        """
        Use Claude to search for INCI ingredients based on product name and URL
        This is a fallback when direct extraction from URL fails
        
        Args:
            product_name: The detected product name
            url: The product URL (for web search)
            
        Returns:
            List of estimated INCI ingredient names
        """
        try:
            # Build prompt with URL for web search
            url_context = ""
            if url:
                url_context = f"""
PRODUCT URL: {url}

IMPORTANT: Use web search to find the ACTUAL ingredient list from this specific product page.
Search for: "{product_name} ingredients" OR visit the URL directly to find the ingredient list.
Do NOT guess or estimate - find the REAL ingredients from the product page or official sources.
"""
            
            prompt = f"""
You are a cosmetic ingredient expert. A user is trying to find the INCI (International Nomenclature of Cosmetic Ingredients) list for this product:

Product Name: {product_name}
{url_context}

Since we were unable to extract the ingredients directly from the product URL, please help by:
1. Using web search to find the ACTUAL ingredient list from the product URL or official product page
2. Searching for "{product_name} ingredients list" or "{product_name} INCI ingredients"
3. Finding the real, complete ingredient list - NOT estimated or guessed ingredients
4. If you find the product page, extract the FULL ingredient list as it appears

CRITICAL REQUIREMENTS:
- Use web search to find the ACTUAL ingredients from the product page
- Return the COMPLETE ingredient list, not just a few ingredients
- Return ONLY a JSON array of INCI names
- Be accurate - these are real ingredients, not estimates
- Include ALL ingredients in the order they appear on the product

Example output format:
["Water", "Glycerin", "Sodium Hyaluronate", "Hyaluronic Acid"]

Return only the JSON array of INCI names:"""

            claude_client = self._get_claude_client()
            from app.config import CLAUDE_MODEL
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else (os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929")
            
            # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
            max_tokens = 4096 if "claude-3-opus-20240229" in model_name else 8192
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
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
    
    async def extract_ingredients_from_text(self, raw_text: str, url: str = None) -> List[str]:
        """
        Use Claude API to extract INCI ingredient names from scraped text
        
        Args:
            raw_text: Raw text scraped from the product page
            url: The product URL (optional, but recommended for better context)
            
        Returns:
            List of extracted INCI ingredient names
        """
        try:
            url_context = f"\n\nProduct URL: {url}" if url else ""
            
            # PRIORITIZE INGREDIENT CONTENT: Extract ingredient sections first, then add other content
            ingredient_sections = []
            other_content = []
            
            # Split text by lines and prioritize ingredient-related sections
            lines = raw_text.split('\n')
            in_ingredient_section = False
            current_section = []
            
            ingredient_keywords = ['ingredient', 'inci', 'composition', 'formula', 'formulation', 'contains']
            
            for line in lines:
                line_lower = line.lower()
                # Check if this line starts an ingredient section
                if any(keyword in line_lower for keyword in ingredient_keywords):
                    if current_section and not in_ingredient_section:
                        other_content.extend(current_section)
                    current_section = [line]
                    in_ingredient_section = True
                elif in_ingredient_section:
                    current_section.append(line)
                    # Stop if we hit a new major section
                    if line.strip() and (line.isupper() or any(stop in line_lower for stop in ['description', 'benefits', 'how to use', 'directions', 'warnings', 'price', 'reviews'])):
                        if not any(keyword in line_lower for keyword in ingredient_keywords):
                            ingredient_sections.append('\n'.join(current_section))
                            current_section = []
                            in_ingredient_section = False
                else:
                    current_section.append(line)
            
            # Add final section
            if current_section:
                if in_ingredient_section:
                    ingredient_sections.append('\n'.join(current_section))
                else:
                    other_content.extend(current_section)
            
            # Also look for comma-separated lists that look like ingredients
            for line in lines:
                if ',' in line and len(line.split(',')) >= 5:
                    line_lower = line.lower()
                    # Check for ingredient indicators
                    if any(word in line_lower for word in ['aqua', 'water', 'acid', 'sodium', 'potassium', 'glycerin', 'extract']):
                        if line not in ingredient_sections:
                            ingredient_sections.append(line)
            
            # Combine: ingredient sections first (up to 6000 chars), then other content (up to 2000 chars)
            prioritized_text = '\n\n'.join(ingredient_sections)
            if len(prioritized_text) < 6000:
                prioritized_text += '\n\n' + '\n'.join(other_content[:2000])
            
            # Use prioritized text, but fall back to original if prioritization didn't work
            text_to_analyze = prioritized_text[:10000] if prioritized_text else raw_text[:10000]
            
            # Debug logging
            print(f"📊 Text prioritization: {len(ingredient_sections)} ingredient sections, {len(text_to_analyze)} chars to analyze")
            if ingredient_sections:
                print(f"   First ingredient section preview: {ingredient_sections[0][:200]}...")
            
            prompt = f"""
You are an expert cosmetic ingredient analyst. Your task is to extract INCI (International Nomenclature of Cosmetic Ingredients) names from the following text scraped from an e-commerce product page.

{url_context}

CRITICAL REQUIREMENTS - READ CAREFULLY:
1. **FIND THE COMPLETE INGREDIENTS LIST** - Look for the LONGEST, MOST COMPLETE list of ingredients. This can be:
   - A single long comma-separated line (e.g., "Aqua, Glycerin, Sodium Hyaluronate, ...")
   - Multiple lines that together form the complete list
   - Text in sections labeled "Ingredients", "Ingredients List", "INCI", "Composition", "Formula", "Formulation", "All Ingredients", or "Ingredient List"
2. **DO NOT STOP EARLY** - Even if you find some ingredient names in descriptions or other sections, you MUST continue searching for the COMPLETE ingredients list. The full list usually has 10-30+ ingredients
3. **HANDLE MULTI-LINE LISTS** - Ingredients may be split across multiple lines. If you see lines that look like ingredient names (chemical names, Latin names, etc.), combine them into one complete list
4. **LOOK FOR PATTERNS** - Ingredient lists often:
   - Start with "Aqua" or "Water"
   - Contain chemical names like "Sodium Hyaluronate", "Ethyl Ascorbic Acid", etc.
   - Are separated by commas, semicolons, or line breaks
   - Appear after text like "Ingredients:", "INCI:", "Composition:", etc.
3. **EXTRACT ALL INGREDIENTS** - When you find the complete ingredients list (usually a long comma-separated string), extract EVERY SINGLE ingredient from that list. Do not skip any, do not stop after finding a few
4. **PRIORITIZE THE LONGEST LIST** - If you see multiple ingredient mentions, prioritize the LONGEST comma-separated list as that is likely the complete INCI list
5. Ingredients are typically listed in order of concentration (highest to lowest), separated by commas
6. The complete ingredients list usually looks like: "Aqua, Ingredient1, Ingredient2, Ingredient3, ..." with many ingredients separated by commas
7. Remove any non-ingredient text, headers, descriptions, marketing content, or explanatory text
8. PRESERVE EXACT INGREDIENT NAMES - DO NOT SHORTEN OR SIMPLIFY:
   - If the text says "Ethyl Ascorbic Acid", extract it as "Ethyl Ascorbic Acid" (NOT "Ascorbic Acid")
   - If the text says "Sodium Hyaluronate", extract it as "Sodium Hyaluronate" (NOT "Hyaluronic Acid")
   - If the text says "Tocopherol", extract it as "Tocopherol" (NOT "Vitamin E")
   - Preserve ALL parts of compound names (e.g., "Ethylhexylglycerin", "C12-15 Alkyl Benzoate", "Dipotassium Glycyrrhizinate")
   - DO NOT remove prefixes like "Ethyl", "Sodium", "Potassium", "Methyl", "Trisodium", etc.
   - DO NOT convert to common names or shorten scientific names
   - DO NOT guess or infer ingredient names - only extract what is explicitly stated in the text
7. Clean up formatting:
   - Remove extra spaces, punctuation marks that aren't part of ingredient names
   - Remove brand names, product names, or marketing claims
   - Keep ingredient names EXACTLY as they appear in the source text
8. Each ingredient should be a separate string in the array
9. Preserve the exact order of ingredients as listed (order matters in cosmetics)
10. If ingredients are listed with percentages or concentrations, remove those numbers
11. If no valid ingredients found, return empty array []
12. DO NOT generate or estimate ingredients - only extract what is actually present in the scraped text
13. **CRITICAL: DO NOT STOP AFTER FINDING A FEW INGREDIENTS** - Continue searching the entire text for the complete ingredients list. The full list is usually 10-20+ ingredients in a single comma-separated string
14. **LOOK FOR THE LONGEST COMMA-SEPARATED LIST** - The complete ingredients list is usually the longest comma-separated string in the text. Extract ALL ingredients from that longest list
15. **EXAMPLE**: If you see "Aqua, Ethyl Ascorbic Acid, Ethoxydiglycol, Butylene Glycol, Ferulic Acid, Hyaluronic Acid, Dipotassium Glycyrrhizinate, Trisodium Ethylenediamine Disuccinate, Hydroxyethyl Cellulose, Succinoglycan Gum, Sodium Polyacrylate, Citric Acid, Sodium Citrate, Sodium Benzoate, Sodium Metabisulfite & Potassium Sorbate" - extract ALL 16 ingredients, not just the first 3

COMMON INCI INGREDIENT PATTERNS:
- Usually start with capital letters (e.g., "Water", "Glycerin", "Ascorbic Acid", "Ethyl Ascorbic Acid")
- May contain numbers (e.g., "C12-15 Alkyl Benzoate")
- May contain hyphens (e.g., "Ethylhexylglycerin")
- May contain multiple words (e.g., "Ethyl Ascorbic Acid", "Sodium Hyaluronate", "Dipotassium Glycyrrhizinate", "Trisodium Ethylenediamine Disuccinate")
- Often separated by commas in the source text
- May use "&" or "and" to separate the last ingredient (e.g., "Sodium Metabisulfite & Potassium Sorbate")

IMPORTANT EXAMPLES OF COMPOUND NAMES:
- "Ethyl Ascorbic Acid" (NOT "Ascorbic Acid") - this is a different, more stable form
- "Sodium Hyaluronate" (NOT "Hyaluronic Acid") - these are different forms
- "Tocopherol" (NOT "Vitamin E") - use the INCI name
- "Aloe Barbadensis Leaf Juice" (NOT "Aloe Vera") - use the full INCI name
- "Dipotassium Glycyrrhizinate" - extract the full name
- "Trisodium Ethylenediamine Disuccinate" - extract the full name

Example output format (COMPLETE list with ALL ingredients):
["Aqua", "Ethyl Ascorbic Acid", "Ethoxydiglycol", "Butylene Glycol", "Ferulic Acid", "Hyaluronic Acid", "Dipotassium Glycyrrhizinate", "Trisodium Ethylenediamine Disuccinate", "Hydroxyethyl Cellulose", "Succinoglycan Gum", "Sodium Polyacrylate", "Citric Acid", "Sodium Citrate", "Sodium Benzoate", "Sodium Metabisulfite", "Potassium Sorbate"]

**REMEMBER**: 
- Find the LONGEST comma-separated ingredient list in the text
- Extract ALL ingredients from that complete list
- Do NOT stop after finding just a few ingredients
- The complete list usually has 10-20+ ingredients

Text to analyze (prioritized with ingredient sections first):
{text_to_analyze}

Return ONLY the JSON array of ALL INCI ingredient names from the complete list, nothing else:"""

            # Debug logging: Check what we actually scraped
            print(f"🔍 DEBUG: Total scraped text length: {len(raw_text)} characters")
            
            # Check for ingredient-related content
            raw_text_lower = raw_text.lower()
            ingredient_indicators = [
                'aqua', 'water', 'ethyl ascorbic acid', 'ferulic acid', 'hyaluronic acid',
                'dipotassium', 'trisodium', 'sodium benzoate', 'potassium sorbate'
            ]
            
            found_indicators = [ind for ind in ingredient_indicators if ind in raw_text_lower]
            if found_indicators:
                print(f"   ✅ Found ingredient indicators: {found_indicators[:5]}")
            else:
                print(f"   ⚠️  No common ingredient indicators found in scraped text!")
            
            # Check for comma-separated lists (ingredient lists are usually comma-separated)
            comma_count = raw_text.count(',')
            print(f"   📊 Comma count in scraped text: {comma_count} (ingredient lists usually have many commas)")
            
            # Find the longest comma-separated segment (likely the ingredient list)
            lines_with_commas = [line for line in raw_text.split('\n') if ',' in line and len(line.split(',')) >= 5]
            if lines_with_commas:
                longest_line = max(lines_with_commas, key=len)
                print(f"   📋 Longest comma-separated line: {len(longest_line)} chars")
                print(f"      Preview: {longest_line[:150]}...")
                ingredient_count_estimate = len(longest_line.split(','))
                print(f"      Estimated ingredients: {ingredient_count_estimate}")
            else:
                print(f"   ⚠️  No long comma-separated lines found (ingredient lists are usually comma-separated)")
            
            # Log sections that contain ingredient keywords
            ingredient_sections_found = []
            for i, line in enumerate(raw_text.split('\n')):
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in ['ingredient', 'inci', 'composition', 'formula']):
                    ingredient_sections_found.append((i, line[:100]))
            
            if ingredient_sections_found:
                print(f"   📝 Found {len(ingredient_sections_found)} lines with ingredient keywords")
                for line_num, preview in ingredient_sections_found[:3]:
                    print(f"      Line {line_num}: {preview}...")
            
            if url:
                print(f"   🔗 Product URL: {url}")

            # Get Claude client (lazy-loaded)
            claude_client = self._get_claude_client()
            
            # Call Claude API - use config model (defaults to claude-sonnet-4-5-20250929)
            from app.config import CLAUDE_MODEL
            model_name = CLAUDE_MODEL if CLAUDE_MODEL else (os.getenv("CLAUDE_MODEL") or os.getenv("MODEL_NAME") or "claude-sonnet-4-5-20250929")
            
            # Set max_tokens based on model (claude-3-opus-20240229 has max 4096)
            max_tokens = 4096 if "claude-3-opus-20240229" in model_name else 8192
            
            response = claude_client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
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
                        print(f"✅ Claude extracted {len(ingredients)} ingredients")
                        
                        # ALWAYS try to find and parse the longest comma-separated list as a fallback
                        # This ensures we get the complete list even if Claude misses some
                        print("🔍 ALWAYS checking for complete ingredient list in scraped text...")
                        
                        # Find the longest comma-separated line that looks like an ingredient list
                        lines = raw_text.split('\n')
                        candidate_lists = []
                        
                        for line in lines:
                            line_stripped = line.strip()
                            if ',' in line_stripped:
                                # Count commas and check for ingredient-like content
                                comma_count = line_stripped.count(',')
                                if comma_count >= 5:  # At least 6 ingredients (5 commas)
                                    line_lower = line_stripped.lower()
                                    # Check for common ingredient words
                                    has_ingredient_words = any(word in line_lower for word in [
                                        'aqua', 'water', 'acid', 'sodium', 'potassium', 'glycerin', 
                                        'extract', 'alcohol', 'citrate', 'benzoate', 'sorbate', 'ethyl',
                                        'ferulic', 'hyaluronic', 'glycol', 'cellulose'
                                    ])
                                    if has_ingredient_words:
                                        candidate_lists.append((line_stripped, comma_count + 1))
                        
                        if candidate_lists:
                            # Use the longest list
                            longest_list_text, estimated_count = max(candidate_lists, key=lambda x: x[1])
                            print(f"   📋 Found candidate ingredient list with ~{estimated_count} ingredients")
                            print(f"   Preview: {longest_list_text[:200]}...")
                            
                            # Parse the comma-separated list
                            # Clean up the text first
                            cleaned = longest_list_text
                            # Remove common prefixes like "Ingredients:", "INCI:", etc.
                            for prefix in ['ingredients:', 'inci:', 'composition:', 'formula:', 'ingredient list:', 'ingredients list:']:
                                if cleaned.lower().startswith(prefix):
                                    cleaned = cleaned[len(prefix):].strip()
                            
                            # Split by comma and clean each ingredient
                            parsed_ingredients = []
                            for item in cleaned.split(','):
                                # Clean up each ingredient
                                ingredient = item.strip()
                                # Remove trailing punctuation that's not part of the name
                                while ingredient and ingredient[-1] in ['.', ';', ':']:
                                    ingredient = ingredient[:-1].strip()
                                # Remove leading/trailing quotes
                                ingredient = ingredient.strip('"\'')
                                if ingredient and len(ingredient) > 1:
                                    parsed_ingredients.append(ingredient)
                            
                            # Also handle "&" separators (e.g., "A & B")
                            final_ingredients = []
                            for ing in parsed_ingredients:
                                if ' & ' in ing or ' and ' in ing.lower():
                                    # Split on & or and
                                    parts = re.split(r'\s+&\s+|\s+and\s+', ing, flags=re.IGNORECASE)
                                    final_ingredients.extend([p.strip() for p in parts if p.strip()])
                                else:
                                    final_ingredients.append(ing)
                            
                            # ALWAYS use the parsed list if it has more ingredients than Claude
                            # CRITICAL: If Claude only found 3-5 ingredients but parsed list has 10+, use parsed
                            if len(final_ingredients) > len(ingredients):
                                print(f"   ✅ Fallback parsing found {len(final_ingredients)} ingredients (vs {len(ingredients)} from Claude)")
                                print(f"   🎯 USING FALLBACK PARSED INGREDIENTS (more complete)")
                                ingredients = final_ingredients
                            elif len(final_ingredients) >= 8 and len(ingredients) < 8:
                                # If parsed list has 8+ and Claude has less, use parsed
                                print(f"   ✅ Fallback parsing found {len(final_ingredients)} ingredients (Claude only found {len(ingredients)})")
                                print(f"   🎯 USING FALLBACK PARSED INGREDIENTS (more complete)")
                                ingredients = final_ingredients
                            elif len(final_ingredients) >= 10 and len(ingredients) <= 5:
                                # Still prefer parsed if it's significantly longer
                                print(f"   🎯 USING FALLBACK PARSED INGREDIENTS (parsed list is much longer)")
                                ingredients = final_ingredients
                            elif len(final_ingredients) >= 12 and len(ingredients) <= 3:
                                # CRITICAL FIX: If parsed has 12+ and Claude only has 3, definitely use parsed
                                print(f"   🎯 CRITICAL: Using fallback parsed ingredients ({len(final_ingredients)} vs {len(ingredients)} from Claude)")
                                print(f"   This fixes the issue where Claude stops early!")
                                ingredients = final_ingredients
                            else:
                                print(f"   ℹ️  Fallback parsing found {len(final_ingredients)} ingredients (Claude found {len(ingredients)})")
                                # Even if same length, prefer parsed if it's a complete list (10+ ingredients)
                                if len(final_ingredients) >= 10 and len(ingredients) < 10:
                                    print(f"   🎯 Using parsed list (complete list with {len(final_ingredients)} ingredients)")
                                    ingredients = final_ingredients
                        else:
                            print(f"   ⚠️  No candidate ingredient lists found in scraped text")
                        
                        # Post-processing validation: Check for common mistakes
                        raw_text_lower = raw_text.lower()
                        validated_ingredients = []
                        
                        for ing in ingredients:
                            ing_lower = ing.lower()
                            ing_original = ing
                            
                            # Check if a longer compound name exists in the source text
                            # Common patterns: "Ethyl Ascorbic Acid" vs "Ascorbic Acid"
                            if "ascorbic acid" in ing_lower and "ethyl" not in ing_lower:
                                # Check if "ethyl ascorbic acid" exists in source
                                if "ethyl ascorbic acid" in raw_text_lower or "ethylascorbic" in raw_text_lower.replace(" ", ""):
                                    print(f"WARNING: Found '{ing}' but source text contains 'Ethyl Ascorbic Acid'. Checking source...")
                                    # Try to find the exact match in source - look for the full compound name
                                    # Look for "ethyl ascorbic acid" (case insensitive, with possible spaces/hyphens)
                                    pattern = r'ethyl[\s-]?ascorbic[\s-]?acid'
                                    if re.search(pattern, raw_text_lower):
                                        # Extract the exact capitalization from source
                                        match = re.search(pattern, raw_text, re.IGNORECASE)
                                        if match:
                                            exact_name = match.group(0)
                                            validated_ingredients.append(exact_name)
                                            print(f"  -> Corrected to: {exact_name}")
                                            continue
                            
                            # Check for other common compound name patterns that might be shortened
                            # Sodium Hyaluronate vs Hyaluronic Acid
                            if "hyaluronic acid" in ing_lower and "sodium" not in ing_lower:
                                if "sodium hyaluronate" in raw_text_lower:
                                    pattern = r'sodium[\s-]?hyaluronate'
                                    if re.search(pattern, raw_text_lower):
                                        match = re.search(pattern, raw_text, re.IGNORECASE)
                                        if match:
                                            exact_name = match.group(0)
                                            validated_ingredients.append(exact_name)
                                            print(f"  -> Corrected to: {exact_name}")
                                            continue
                            
                            # Keep the original ingredient if no correction needed
                            validated_ingredients.append(ing_original)
                        
                        if validated_ingredients != ingredients:
                            print(f"Validation corrected ingredients: {ingredients} -> {validated_ingredients}")
                        
                        return validated_ingredients
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
            
            # Try to extract ingredients using Claude (pass both URL and scraped data)
            ingredients = await self.extract_ingredients_from_text(extracted_text, url)
            
            # If extraction succeeded, return direct results
            if ingredients and len(ingredients) > 0:
                return {
                    "ingredients": ingredients,
                    "extracted_text": extracted_text,
                    "platform": scrape_result["platform"],
                    "url": url,
                    "is_estimated": False,
                    "source": "url_extraction",
                    "product_name": None,
                    "product_image": scrape_result.get("product_image")
                }
            
            # If extraction failed, check if we got meaningful scraped text
            # Only fall back to AI if scraping actually got content but no ingredients were found
            if extracted_text and len(extracted_text.strip()) > 50:
                print(f"WARNING: Scraped {len(extracted_text)} characters but no ingredients extracted. This may indicate:")
                print("  1. Ingredients are not present on the page")
                print("  2. Ingredients are in a format Claude couldn't parse")
                print("  3. Ingredients section was not properly scraped")
                print("Attempting fallback: detecting product name...")
                
                product_name = await self.detect_product_name(extracted_text, url)
                
                if product_name:
                    print(f"Detected product name: {product_name}")
                    print("WARNING: Using AI web search to find ingredients from product URL...")
                    estimated_ingredients = await self.search_ingredients_by_product_name(product_name, url)
                    
                    if estimated_ingredients and len(estimated_ingredients) > 0:
                        return {
                            "ingredients": estimated_ingredients,
                            "extracted_text": extracted_text,
                            "platform": scrape_result["platform"],
                            "url": url,
                            "is_estimated": True,
                            "source": "ai_search",
                            "product_name": product_name,
                            "product_image": scrape_result.get("product_image")
                        }
            else:
                print("WARNING: Scraping returned very little or no content. This suggests:")
                print("  1. The page may be blocking automated access")
                print("  2. The page structure may be different than expected")
                print("  3. JavaScript may not have loaded properly")
            
            # If fallback also failed, return empty
            return {
                "ingredients": [],
                "extracted_text": extracted_text,
                "platform": scrape_result["platform"],
                "url": url,
                "is_estimated": False,
                "source": "url_extraction",
                "product_name": product_name,
                "product_image": scrape_result.get("product_image")
            }
            
        except Exception as e:
            # If scraping failed, try to detect product from URL only
            print(f"Scraping failed: {e}, attempting product name detection from URL...")
            try:
                product_name = await self.detect_product_name("", url)
                if product_name:
                    estimated_ingredients = await self.search_ingredients_by_product_name(product_name, url)
                    if estimated_ingredients and len(estimated_ingredients) > 0:
                        return {
                            "ingredients": estimated_ingredients,
                            "extracted_text": f"Unable to scrape URL: {str(e)}",
                            "platform": self._detect_platform(url),
                            "url": url,
                            "is_estimated": True,
                            "source": "ai_search",
                            "product_name": product_name,
                            "product_image": None
                        }
            except:
                pass
            
            raise Exception(f"Failed to extract ingredients from URL: {str(e)}")

