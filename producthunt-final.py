#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 26 23:07:22 2024

@author: joy
"""

import time
from random import randint
from create_numerical_task import create_about_task,create_ppl_task
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium import webdriver
import json
import os
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
import re
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from urllib.parse import urljoin
# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate('key.json')
    default_app = firebase_admin.initialize_app(cred)

db = firestore.client()
def moveToElement(driver, target_xpath):
    
    try:
        target = WebDriverWait(driver, 7).until(EC.visibility_of_element_located((By.XPATH, target_xpath)))
        ActionChains(driver).move_to_element(target).perform()
        return True
    except:
        return False

def login():
    url = 'https://www.producthunt.com/'
    
    chrome_options = webdriver.ChromeOptions()
    
    # Headless mode options
    # chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Other existing options
    prefs = {"profile.default_content_setting_values.notifications": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    
    # chrome_options.add_argument("--incognito")
    chrome_options.add_argument("--start-maximized")
    
    try:
        driver = webdriver.Chrome(executable_path='/home/joy/Downloads/chromedriver_linux64/chromedriver', options=chrome_options)
    except:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
    
    driver.get(url)
    
    return driver

# [All previous functions remain the same until sign_in_and_extract]


def update_or_create_company_firestore_document(linkedin_id, db, doc_id, batch=None):
    """Optimized version that uses batching and reduces reads"""
    doc_ref = db.collection("entities").document(linkedin_id)
    
    # Define fields to be set
    additional_fields = {
        "ph_id": doc_id,
        "parallel_number": randint(1, 10),
        "last_updated": datetime.utcnow(),
        "id": linkedin_id,
        "created": datetime.utcnow()
    }

    # Use the provided batch or create a new one
    use_batch = batch is not None
    if not use_batch:
        batch = db.batch()
    
    # Set with merge=True to update if exists or create if not
    batch.set(doc_ref, additional_fields, merge=True)
    
    # Only commit if we created the batch in this function
    if not use_batch:
        batch.commit()
        print(f"Updated/created document for linkedin_id: {linkedin_id}")


def update_or_create_profile_document(profile_id, db, profile_info):
    # Check if the profile document exists
    profile_doc_ref = db.collection("ppl").document(profile_id)
    profile_doc = profile_doc_ref.get()
    
    # Define additional fields to be added if the profile document doesn't exist
    additional_fields = {
        
        "ph_id": profile_info['ph_id'],
        "parallel_number": randint(1, 10),  # Initialize parallel number or update as needed
        "last_updated": datetime.utcnow(),
        "id": profile_id,
        "created":datetime.utcnow()
    }

    if profile_doc.exists:
        # If profile document exists, update the existing fields and `last_updated`
        profile_doc_ref.set({"ph_id": profile_info['ph_id'], "last_updated": datetime.utcnow()}, merge=True)
        print(f"Updated existing profile document for profile_id: {profile_id}")
    else:
        # If profile document does not exist, create it with the additional fields
        profile_doc_ref.set(additional_fields)
        print(f"Created new profile document for profile_id: {profile_id} with fields: {additional_fields}")


def sign_in_and_extract(driver, username, password, start_date, end_date, last_processed_link=None):
    """
    Iterate through dates from start_date to end_date and process Product Hunt leaderboard
    
    Args:
    - driver: Selenium WebDriver
    - username: Product Hunt username (not used in current implementation)
    - password: Product Hunt password (not used in current implementation)
    - start_date: Start date in format 'YYYY/M/D'
    - end_date: End date in format 'YYYY/M/D'
    - last_processed_link: Optional last processed link to resume from
    """
    # Convert start and end dates to datetime objects
    start = datetime.strptime(start_date, "%Y/%m/%d")
    end = datetime.strptime(end_date, "%Y/%m/%d")
    
    # Generate a list of dates
    date_range = [start + timedelta(days=x) for x in range((end - start).days + 1)]
    
    # Process each date
    for current_date in date_range:
        # break
        # Format the date for the URL and launch date
        url_date = current_date.strftime("%Y/%m/%d")
        launch_date = current_date.strftime("%d-%m-%Y")
        
        # Construct the page URL
        page_url = f"https://www.producthunt.com/leaderboard/daily/{url_date}?ref=header_nav"
        print(f"Processing date: {url_date}")
        
        # Modify the sign_in_and_extract to accept launch_date
        unprocessed_links = process_daily_leaderboard(driver, page_url, launch_date,last_processed_link=None,
                              initial_wait=8,
                              max_no_content_attempts=8,
                              max_scroll_attempts=150,
                              max_links=1000,
                              base_url=None)





def process_daily_leaderboard(driver, page_url, launch_date, last_processed_link=None,
                              initial_wait=8,
                              max_no_content_attempts=8,
                              max_scroll_attempts=150,
                              max_links=1000,
                              base_url=None):
    """
    Scrape links from lazy-loading leaderboard page. Returns list of unprocessed absolute URLs.
    - driver: selenium webdriver
    - page_url: URL to open
    - launch_date: (kept for compatibility; not used here)
    - last_processed_link: optional last link already processed; returned links start after it
    """
    # Navigate (replace query string only if required)
    if "?ref=header_nav" in page_url:
        search_url = page_url.replace("?ref=header_nav", "/all")
        driver.get(search_url)
    else:
        driver.get(page_url)

    # base_url used to resolve relative hrefs
    if base_url is None:
        base_url = page_url

    # initial wait for page to load
    time.sleep(initial_wait)

    all_search_results = []
    seen = set()

    no_new_content_count = 0
    scroll_attempts = 0
    prev_anchor_count = 0

    anchors_xpath = "//*[contains(@data-test, 'post-name')]//a"
    containers_xpath = "//*[contains(@data-test, 'post-name')]"

    while scroll_attempts < max_scroll_attempts:
        scroll_attempts += 1

        # Get current counts (containers and anchors) BEFORE scrolling
        containers = driver.find_elements(By.XPATH, containers_xpath)
        anchors = driver.find_elements(By.XPATH, anchors_xpath)
        current_container_count = len(containers)
        current_anchor_count = len(anchors)

        print(f"Scroll attempt {scroll_attempts}: containers={current_container_count}, anchors={current_anchor_count}")

        # Scroll to near last container to trigger lazy loading
        if containers:
            try:
                last_container = containers[-1]
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", last_container)
                # short waits to let JS run and populate anchors/hrefs
                time.sleep(2)
                driver.execute_script("window.scrollBy(0, 200);")
                time.sleep(4)
            except Exception as e:
                print("Targeted scroll failed:", e)
                driver.execute_script("window.scrollBy(0, 400);")
                time.sleep(4)
        else:
            # nothing yet, incremental scroll
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(4)

        # Re-fetch anchors after waiting
        anchors = driver.find_elements(By.XPATH, anchors_xpath)
        new_anchor_count = len(anchors)

        # Determine whether new anchors were added
        if new_anchor_count > prev_anchor_count:
            no_new_content_count = 0
            added = new_anchor_count - prev_anchor_count
            print(f"SUCCESS: anchors increased to {new_anchor_count} (added {added})")
        else:
            no_new_content_count += 1
            print(f"No new anchors found (attempt {no_new_content_count}/{max_no_content_attempts})")

        prev_anchor_count = new_anchor_count

        # Extract URLs from anchors with fallbacks
        missing_href_count = 0
        for a in anchors:
            href = None
            try:
                href = a.get_attribute("href")
            except Exception:
                href = None

            # fallback to common data attributes
            if not href or href.strip() == "":
                try:
                    href = (a.get_attribute("data-href") or
                            a.get_attribute("data-url") or
                            a.get_attribute("data-link") or
                            a.get_attribute("data-qa-url"))
                except Exception:
                    href = None

            # fallback: try ancestor container attributes or onclick content
            if not href or href.strip() == "":
                try:
                    parent = a.find_element(By.XPATH, "./ancestor::*[contains(@data-test, 'post-name')][1]")
                    href = href or parent.get_attribute("data-href") or parent.get_attribute("data-url") or parent.get_attribute("data-link")
                    if not href or href.strip() == "":
                        onclick = parent.get_attribute("onclick") or a.get_attribute("onclick")
                        if onclick:
                            # grab the first quoted URL-like string inside onclick
                            m = re.search(r"['\"](\/?[^'\" >]+)['\"]", onclick)
                            if m:
                                href = m.group(1)
                except Exception:
                    # ignore and continue
                    pass

            if not href or href.strip() == "":
                missing_href_count += 1
                continue

            # Normalize relative URLs
            try:
                abs_href = urljoin(base_url, href.strip())
            except Exception:
                abs_href = href.strip()

            # Deduplicate
            if abs_href not in seen:
                seen.add(abs_href)
                all_search_results.append(abs_href)

        if missing_href_count > 0:
            print(f"Anchors without an extractable URL this pass: {missing_href_count}")

        # Stop conditions
        if no_new_content_count >= max_no_content_attempts:
            print(f"Stopping: No new content after {max_no_content_attempts} consecutive attempts.")
            break

        if len(all_search_results) >= max_links:
            print(f"Stopping: reached max_links={max_links}.")
            break

        # small pause before next scroll loop
        time.sleep(1.0)

    # If nothing was found, print a sample container outerHTML for debugging
    if len(all_search_results) == 0:
        sample = driver.find_elements(By.XPATH, containers_xpath)[:3]
        for n in sample:
            try:
                html = n.get_attribute("outerHTML")
                print("Sample container (truncated):", (html or "")[:800])
            except Exception:
                pass

    # Determine the start index based on last_processed_link (if provided)
    if last_processed_link:
        try:
            start_index = all_search_results.index(last_processed_link) + 1
        except ValueError:
            # last_processed_link not found — process all
            start_index = 0
    else:
        start_index = 0

    unprocessed_links = all_search_results[start_index:]

    print(f"Total links found: {len(all_search_results)}")
    print(f"Unprocessed links: {len(unprocessed_links)}")
    
    
    for each_link in unprocessed_links:
        # break
        try:
            doc_id = each_link.split("/posts/")[1].split("#")[0]
        except:
            doc_id = each_link.split("/products/")[1].split("#")[0]
        
        if '?' in doc_id:
            doc_id = doc_id.split("?")[0]
        doc_ref = db.collection("ph").document(doc_id)
        if doc_ref.get().exists:
            print("not processing this as it already exists")
            continue
            
        print(f"Processing link: {each_link}")
        company_info = {}
        start_time = datetime.now()
        print("Start time: ", start_time)
        
        
        driver.get(each_link+"/makers/")
        
        
        if  '?' in each_link:
            driver.get(each_link.split("?")[0])
        
        else:
            driver.get(each_link.split("#")[0])
        time.sleep(2)

        try:
            name = driver.find_element(By.XPATH, "//h1[contains(@class, 'font-bold text-dark-gray')]").text
            company_info['name'] = name
        except Exception as e:
            # 
            try:
                name = driver.find_element(By.XPATH, "//div[contains(@class, 'text-24 font-semibold text-dark-gray')]").text
                company_info['name'] = name
                
            except:
                try:
                    name = driver.find_element(By.XPATH,"//h1[contains(@class, 'text-24 font-semibold text-gray-')]").text
                    company_info['name'] = name
                except:
                    print(f"Error finding name element for {each_link}: {e}")
                    name = ""
                    company_info['name'] = name

        model = 'normal'
        
        
        if 'https://www.producthunt.com/posts/' in each_link:
            print("went here")
            if moveToElement(driver, "//a[@class='text-16 font-normal text-blue']"):
                model = 'normal'
                getNormalmodel(driver, each_link, company_info, launch_date)
            elif 'https://www.producthunt.com/products/' in driver.current_url:
                print("condition worked")
                getNormalmodel(driver, each_link, company_info, launch_date)
                model = 'normal'
            else:
                model = 'no page'
                
                
            print("Model: ", model)
        
            # if model == 'normal':
            #     getNormalmodel(driver, each_link, company_info, launch_date)
            # elif model == "no page":
            #     getNopageModel(driver, each_link, company_info, launch_date)
            # else:
            #     print("Failed to extract model")
        
        elif 'https://www.producthunt.com/products/' in each_link:
            getNormalmodel(driver, each_link, company_info, launch_date)
        
        else:  # This handles the case where it's neither posts nor products
            print("here")
            if moveToElement(driver, "//a[contains(@href, '/products/')]"):
                each_link = driver.find_element_by_xpath("//a[contains(@href, '/products/')]").get_attribute("href")
                driver.get(each_link)
                getNormalmodel(driver, each_link, company_info, launch_date)
        end_time = datetime.now()
        # print("End time:  ", end_time)
        
        time_taken = end_time - start_time
        # print(f"Time taken for {each_link}: {time_taken}")
    
    # Return the unprocessed links to be used in subsequent calls
    return unprocessed_links

def getNormalmodel(driver, each_link, company_info, launch_date):
    
    company_info['launch_date'] = launch_date
    try:
        a_class_link = driver.find_element(By.XPATH, "//a[@class='text-16 font-normal text-blue']").get_attribute('href')
        driver.get(a_class_link+ "/makers")
    except:
        if "?" in driver.current_url:
            link_to_get = driver.current_url.split("?")[0]
            driver.get(link_to_get + "/makers")
        else:
            driver.get(driver.current_url + "/makers")
    
    driver.implicitly_wait(5)
    links_websites = []
    
    script_tag = driver.find_element(By.XPATH, '//script[contains(text(), "window[Symbol.for")]')
    
    # Extract the content of the script tag
    script_content = script_tag.get_attribute('innerHTML')
    
    # Parse the JavaScript-like data
    start_keyword = '"websiteUrl":"'
    start_index = script_content.find(start_keyword) + len(start_keyword)
    end_index = script_content.find('"', start_index)
    
    website= script_content[start_index:end_index]
    
    if website == "l.for(" or website == "":
        try:
            website = driver.find_element_by_xpath("//div[@data-sentry-component='Links']//a").get_attribute("href")
        except:
            try:
                website_element = driver.find_element_by_xpath("//div[@data-sentry-component='Status' and .//div[text()='Company Info']]//a")
                
                website = website_element.get_attribute("href").split("?ref")[0]
            except:
                website = ""
    print("Extracted Website URL:", website)
    company_info['website'] = website

    # Extract ALL additional website links properly from both Status and Social sections
    try:
        # Get links from Status section (additional websites)
        other_Websites = driver.find_elements(By.XPATH, "//div[@data-sentry-component='Status']//a")
        for website_link in other_Websites:
            extra_link = website_link.get_attribute("href").split("?ref=")[0]
            links_websites.append(extra_link)
        
        # ALSO get links from Social Links section 
        social_websites = driver.find_elements(By.XPATH, "//div[@data-sentry-component='SocialLinks']//following-sibling::div//a")
        for social_link in social_websites:
            extra_link = social_link.get_attribute("href").split("?ref=")[0]
            if extra_link not in links_websites:  # Avoid duplicates
                links_websites.append(extra_link)
        
        print(f"Found all links: {links_websites}")
        
        # Store all additional links (excluding the main website) in company_social_temp
        if len(links_websites) > 0:
            # Remove the main website URL if it's in the list
            filtered_links = [link for link in links_websites if link != website]
            
            # ONLY add links that are actually social media or special platforms
            social_and_special_links = []
            for link in filtered_links:
                link_lower = link.lower()
                # Check if it's a social media platform or special platform
                if any(platform in link_lower for platform in [
                    'twitter.com/', 'x.com/', 'facebook.com/', 'linkedin.com/', 
                    'instagram.com/', 'github.com/', 'medium.com/', 'telegram.com/',
                    'producthunt.com/r/', 'play.google.com/store', 'apps.apple.com',
                    'itunes.apple.com', 'chrome.google.com/webstore', 
                    'marketplace.visualstudio.com'
                ]):
                    social_and_special_links.append(link)
                    print(f"Added social/special link: {link}")
                else:
                    print(f"Skipping regular website from temp processing: {link}")
            
            if social_and_special_links:
                company_info['company_social_temp'] = social_and_special_links
                print(f"Found {len(social_and_special_links)} social/special platform links: {social_and_special_links}")
            else:
                company_info['company_social_temp'] = []
        else:
            company_info['company_social_temp'] = []
    except Exception as e:
        print(f"Error extracting additional website links: {e}")
        company_info['company_social_temp'] = []

    allowed_social_links = {
        'twitter': 'twitter_id',
        'x': 'twitter_id',
        'facebook': 'facebook_id',
        'linkedin': 'li_id',
        'instagram': 'instagram_id',
        'github': 'github_id'
    }
    
    social_links_div = driver.find_elements(By.XPATH, "//div[@data-sentry-component='SocialLinks']")    
    social_links_dict = {key: [] for key in allowed_social_links.values()}
    other_social_links = []  # This will capture Medium and other non-main platforms
    
    if social_links_div:
        print("Processing SocialLinks div...")
        for div in social_links_div:
            sibling_divs = div.find_elements(By.XPATH, "following-sibling::div//a")
            for sibling_div in sibling_divs:
                try:
                    link_soc = sibling_div.get_attribute('href')
                    print(f"Found social link from SocialLinks: {link_soc}")
                    
                    # Try to get the social name from the div text
                    try:
                        social_name = sibling_div.find_element(By.XPATH, ".//div").text.lower()
                        print(f"Social name: {social_name}")
                    except:
                        # If we can't get the name, determine it from the URL
                        if 'twitter.com/' in link_soc.lower() or 'x.com/' in link_soc.lower():
                            social_name = 'twitter'
                        elif 'facebook.com/' in link_soc.lower():
                            social_name = 'facebook'
                        elif 'linkedin.com/' in link_soc.lower():
                            social_name = 'linkedin'
                        elif 'instagram.com/' in link_soc.lower():
                            social_name = 'instagram'
                        elif 'github.com/' in link_soc.lower():
                            social_name = 'github'
                        else:
                            social_name = 'unknown'
                        print(f"Determined social name from URL: {social_name}")
        
                    if social_name in allowed_social_links:
                        category = allowed_social_links[social_name]
                        # Store complete URLs for all platforms except LinkedIn
                        if social_name == 'linkedin':
                            # For LinkedIn, extract handle/path as before
                            clean_href = link_soc
                            if '?' in clean_href:
                                clean_href = clean_href.split('?')[0]
                            
                            clean_href_lower = clean_href.lower()
                            
                            if '/company/' in clean_href_lower:
                                handle = clean_href.split('/company/')[1].split('/')[0]
                            elif '/in/' in clean_href_lower:
                                handle = clean_href.split('/in/')[1].split('/')[0]
                            elif '/products/' in clean_href_lower:
                                handle = clean_href  # Store full URL for products
                            else:
                                handle = clean_href.split('linkedin.com/')[1].split('/')[0]
                            
                            social_links_dict[category].append(handle)
                            print(f"Added LinkedIn handle {handle} to {category}")
                        else:
                            # For all other platforms, store complete URL
                            social_links_dict[category].append(link_soc)
                            print(f"Added {link_soc} to {category}")
                    else:
                        # Add unrecognized social links to the others array
                        other_social_links.append(link_soc)
                        print(f"Added {link_soc} to other_social_links")
                except Exception as e:
                    print(f"Error processing social link: {e}")
                    continue
    
    # Store allowed social links in company_social, filter out empty lists
    company_info['company_social'] = {k: v for k, v in social_links_dict.items() if v}
    
    # Store other social links under 'others' as direct array if they exist
    if other_social_links:
        company_info['company_social']['others'] = other_social_links
        print(f"Added other_social_links to others: {other_social_links}")
        
    # Debug: Print what we have so far
    print(f"After Social Links processing: {company_info['company_social']}")
    print(f"company_social_temp contains: {company_info.get('company_social_temp', [])}")
        
    # If no social links found, try alternative method
    if not company_info['company_social'] or company_info['company_social'] == {}:
        print("Trying alternative social links method...")
        try:
            social_links_div = driver.find_element_by_xpath("//div[@data-sentry-component='SocialLinks']")
            social_links = social_links_div.find_elements(By.XPATH, ".//a[@href]")
        
            for link in social_links:
                href = link.get_attribute('href')
                print(f"Found alternative social link: {href}")
                found_social = False
                href_lower = href.lower()
                
                # Store complete URLs for all platforms except LinkedIn
                if 'twitter.com/' in href_lower or 'x.com/' in href_lower:
                    # Store complete URL for Twitter/X
                    social_links_dict['twitter_id'].append(href)
                    found_social = True
                    print(f"Added {href} to twitter_id")
                    
                elif 'facebook.com/' in href_lower:
                    # Store complete URL for Facebook
                    social_links_dict['facebook_id'].append(href)
                    found_social = True
                    print(f"Added {href} to facebook_id")
                    
                elif 'linkedin.com/' in href_lower:
                    # Keep LinkedIn logic as is (extract handle/path)
                    clean_href = href
                    if '?' in clean_href:
                        clean_href = clean_href.split('?')[0]
                    
                    clean_href_lower = clean_href.lower()
                    
                    if '/company/' in clean_href_lower:
                        handle = clean_href.split('/company/')[1].split('/')[0]
                    elif '/in/' in clean_href_lower:
                        handle = clean_href.split('/in/')[1].split('/')[0]
                    elif '/products/' in clean_href_lower:
                        handle = clean_href  # Store full URL for products
                    else:
                        handle = clean_href.split('linkedin.com/')[1].split('/')[0]
                    
                    social_links_dict['li_id'].append(handle)
                    found_social = True
                    print(f"Added {handle} to li_id")
                    
                elif 'instagram.com/' in href_lower:
                    # Store complete URL for Instagram
                    social_links_dict['instagram_id'].append(href)
                    found_social = True
                    print(f"Added {href} to instagram_id")
                    
                elif 'github.com/' in href_lower:
                    # Store complete URL for GitHub
                    social_links_dict['github_id'].append(href)
                    found_social = True
                    print(f"Added {href} to github_id")
                                    
            company_info['company_social'] = {k: v for k, v in social_links_dict.items() if v}
            
            # Store other social links under 'others' as direct array if they exist
            if other_social_links:
                company_info['company_social']['others'] = other_social_links
                print(f"Set others from alternative method: {other_social_links}")
    
        except Exception as e:
            print(f"Error in alternative social links extraction: {e}")
            company_info['company_social'] = {}
    
    # Process company_social_temp into the final company_social structure
    if 'company_social_temp' in company_info and company_info['company_social_temp']:
        print("Processing company_social_temp...")
        # Get the main website URL to avoid duplication
        main_website = company_info.get('website', '').lower()
        # Clean the main website URL for comparison
        if main_website:
            if '?ref=' in main_website:
                main_website_clean = main_website.split('?ref=')[0]
            else:
                main_website_clean = main_website
        else:
            main_website_clean = ''
        
        for temp_link in company_info['company_social_temp']:
            # Clean the temp link for comparison
            temp_link_clean = temp_link.lower()
            if '?ref=' in temp_link_clean:
                temp_link_clean = temp_link_clean.split('?ref=')[0]
            
            # Skip if this link is the same as the main website
            if main_website_clean and temp_link_clean == main_website_clean:
                print(f"Skipped main website duplicate: {temp_link}")
                continue
                
            # Check if it's a social platform - store complete URLs except for LinkedIn
            found_social = False
            temp_link_lower = temp_link.lower()
            
            if 'twitter.com/' in temp_link_lower or 'x.com/' in temp_link_lower:
                # Store complete URL for Twitter/X
                if 'twitter_id' not in company_info['company_social']:
                    company_info['company_social']['twitter_id'] = []
                elif not isinstance(company_info['company_social']['twitter_id'], list):
                    company_info['company_social']['twitter_id'] = [company_info['company_social']['twitter_id']]
                company_info['company_social']['twitter_id'].append(temp_link)
                found_social = True
                print(f"Added to twitter_id: {temp_link}")
                
            elif 'facebook.com/' in temp_link_lower:
                # Store complete URL for Facebook
                if 'facebook_id' not in company_info['company_social']:
                    company_info['company_social']['facebook_id'] = []
                elif not isinstance(company_info['company_social']['facebook_id'], list):
                    company_info['company_social']['facebook_id'] = [company_info['company_social']['facebook_id']]
                company_info['company_social']['facebook_id'].append(temp_link)
                found_social = True
                print(f"Added to facebook_id: {temp_link}")
                
            elif 'linkedin.com/' in temp_link_lower:
                # Keep LinkedIn logic as is (store complete URL, will be processed later)
                if 'li_id' not in company_info['company_social']:
                    company_info['company_social']['li_id'] = []
                elif not isinstance(company_info['company_social']['li_id'], list):
                    company_info['company_social']['li_id'] = [company_info['company_social']['li_id']]
                company_info['company_social']['li_id'].append(temp_link)
                found_social = True
                print(f"Added to li_id: {temp_link}")
                
            elif 'instagram.com/' in temp_link_lower:
                # Store complete URL for Instagram
                if 'instagram_id' not in company_info['company_social']:
                    company_info['company_social']['instagram_id'] = []
                elif not isinstance(company_info['company_social']['instagram_id'], list):
                    company_info['company_social']['instagram_id'] = [company_info['company_social']['instagram_id']]
                company_info['company_social']['instagram_id'].append(temp_link)
                found_social = True
                print(f"Added to instagram_id: {temp_link}")
                
            elif 'github.com/' in temp_link_lower:
                # Store complete URL for GitHub
                if 'github_id' not in company_info['company_social']:
                    company_info['company_social']['github_id'] = []
                elif not isinstance(company_info['company_social']['github_id'], list):
                    company_info['company_social']['github_id'] = [company_info['company_social']['github_id']]
                company_info['company_social']['github_id'].append(temp_link)
                found_social = True
                print(f"Added to github_id: {temp_link}")
            
            # If not a main social platform, add to others (including Medium, Telegram, etc.)
            if not found_social:
                # All other links go to 'others' array
                if 'others' not in company_info['company_social']:
                    company_info['company_social']['others'] = []
                company_info['company_social']['others'].append(temp_link)
                print(f"Added to others: {temp_link}")
        
        # Remove the temporary field
        del company_info['company_social_temp']
        print(f"Processed company_social_temp. Final structure: {company_info['company_social']}")

    # Final processing with corrected validation
    if 'company_social' in company_info:
        print(f"Final processing - Before: {company_info['company_social']}")
        # Create a copy to avoid modifying dict during iteration
        social_copy = company_info['company_social'].copy()
        
        for key, value in social_copy.items():
            if isinstance(value, list) and key != 'others':
                if value:  # Only process if list is not empty
                    if key == 'li_id':
                        # Special handling for LinkedIn - ensure it's a handle/path
                        linkedin_url = value[0] if isinstance(value, list) else value
                        # Clean LinkedIn URL to extract handle/path if it's a full URL
                        if 'linkedin.com/' in str(linkedin_url).lower():
                            if '/company/' in linkedin_url:
                                handle = linkedin_url.split('/company/')[1].split('/')[0]
                                if '?' in handle:
                                    handle = handle.split('?')[0]
                            elif '/in/' in linkedin_url:
                                handle = linkedin_url.split('/in/')[1].split('/')[0]
                                if '?' in handle:
                                    handle = handle.split('?')[0]
                            else:
                                handle = linkedin_url
                            company_info['company_social'][key] = handle
                            print(f"Set {key} to handle: {handle}")
                        else:
                            # Already a handle
                            company_info['company_social'][key] = value[0]
                            print(f"Set {key} to existing handle: {value[0]}")
                    else:
                        # For all other platforms (Twitter, Facebook, Instagram, GitHub), keep complete URL
                        company_info['company_social'][key] = value[0]
                        print(f"Set {key} to URL: {value[0]}")
                else:
                    # Empty list, remove the key
                    print(f"Removing empty {key}")
                    del company_info['company_social'][key]
        
        print(f"Final processing - After: {company_info['company_social']}")

    # Team extraction code
    try:
        links_and_texts = []
        
        # Step 1: Get all blocks that might contain profiles
        ul_elements = driver.find_elements(By.XPATH, "//ul[contains(@class, 'styles_makerList')]")
        if not ul_elements:
            ul_elements = driver.find_elements(By.XPATH, "//div[@data-sentry-component='InfiniteScroll']")
            if not ul_elements:
                ul_elements = driver.find_elements(By.XPATH, "//section[contains(@data-test,'maker-card-')]")
        
        # Step 2: Click "Show all" buttons if present
        if moveToElement(driver, "//*[contains(text(), 'Show all')]"):
            more_profiles_load = driver.find_elements(By.XPATH, "//*[contains(text(), 'Show all')]")
            for one_click in more_profiles_load:
                one_click.click()
        
        
        for ul_element in ul_elements:
            card_elements = ul_element.find_elements(By.XPATH, ".//section[contains(@data-test,'maker-card-')]")
            if not card_elements:
                # If ul_element itself is a maker-card, add it to card_elements
                if "maker-card-" in ul_element.get_attribute("data-test"):
                    card_elements = [ul_element]
                else:
                    continue # Skip if it's not a maker-card
    
            for card in card_elements:
                # Try to find all 'a' elements directly within the card or within its immediate children
                # This XPath will find 'a' elements regardless of whether they are direct children
                # of the card or nested within divs within the card.
                all_a_elements = card.find_elements(By.XPATH, ".//a[@href]")
    
                for a in all_a_elements:
                    href = a.get_attribute('href')
                    if href:
                        links_and_texts.append(href)
        # # Step 3: Extract hrefs
        # for ul_element in ul_elements:
        #     # Instead of .//li or .//section inside ul, go straight to cards
        #     card_elements = ul_element.find_elements(By.XPATH, ".//section[contains(@data-test,'maker-card-')]")
        #     if not card_elements:
        #         card_elements = [ul_element]  # in case ul_element is itself a maker-card
        
        #     for card in card_elements:
        #         # Main case: normal logic
        #         div_elements = card.find_elements(By.XPATH, ".//a")
        #         if div_elements:
        #             for div in div_elements:
        #                 a_elements = div.find_elements(By.XPATH, ".//a[@href]")
        #                 for a in a_elements:
        #                     href = a.get_attribute('href')
        #                     if href:
        #                         links_and_texts.append(href)
        #         else:
        #             # Fallback: try getting links directly from the card
        #             fallback_links = card.find_elements(By.XPATH, ".//a[@href]")
        #             for a in fallback_links:
        #                 href = a.get_attribute('href')
        #                 if href:
        #                     links_and_texts.append(href)

        links_of_profiles = list(set(links_and_texts))
        links_of_profiles = [link for link in links_of_profiles if '@deleted' not in link and '@' in link]
        profiles_infos = []

        for profile_link in links_of_profiles:
            try:
                driver.get(profile_link)
                time.sleep(3)
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'flex flex-col items-center gap-4')]"))
                )
                time.sleep(2)
        
                profile_info = {}
                profile_title = driver.find_element(By.XPATH, "//div[@class='text-18 font-light text-light-gray mb-1']").text
                profile_id = driver.current_url.split("https://www.producthunt.com/@")[1]
                profile_name = driver.find_element(By.XPATH, "//h1[@class='text-24 font-semibold text-dark-gray mb-1']").text
                
                profile_links = {}
                
                try:
                    time.sleep(1)
                    links_div = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//h2[text()='Links']/following-sibling::div"))
                    )
                    time.sleep(1)
                    a_tags = links_div.find_elements(By.XPATH, ".//a[@href]")
                    
                    for a in a_tags:
                        try:
                            href = a.get_attribute('href')
                            category = a.find_element(By.XPATH, ".//span").text
                            profile_links[category] = href
                        except Exception as e:
                            print(f"Stale element while processing link: {e}")
                            continue
                            
                except Exception:
                    profile_links = {}
           
            except Exception as e:
                print(f"Error processing profile {profile_link}: {e}")
                continue
                
            updated_links = {}
            other_links = {}
            allowed_social_links = {
                'twitter': 'twitter_id',
                'x': 'twitter_id',
                'facebook': 'facebook_id',
                'linkedin': 'li_id',
                'instagram': 'instagram_id',
                'github': 'github_id',
                'telegram': 'telegram_id'
            }
        
            for category, url in profile_links.items():
                url_lower = url.lower()
                category_lower = category.lower()
                if 'linkedin.com/in/' in url_lower:
                    link_id = url_lower.split('linkedin.com/in/')[1].rstrip('/')
                    updated_links['li_id'] = link_id
                elif 'linkedin.com/company/' in url_lower:
                    link_id = url_lower.split('linkedin.com/company/')[1].rstrip('/')
                    if '?' in link_id:
                        link_id = link_id.split("?")[0].rstrip("/")
                    if "?trk" in link_id:
                        link_id = link_id.split("?trk")[0].rstrip("/")
                    updated_links['company_li_id'] = link_id
                elif 'twitter.com/' in url_lower or 'x.com/' in url_lower:
                    twitter_handle = url_lower.split('twitter.com/')[1] if 'twitter.com/' in url_lower else url_lower.split('x.com/')[1]
                    updated_links['twitter_id'] = twitter_handle
                elif 'facebook.com/' in url_lower:
                    facebook_handle = url_lower.split('facebook.com/')[1].rstrip('/')
                    updated_links['facebook_id'] = facebook_handle
                elif 'instagram.com/' in url_lower:
                    instagram_handle = url_lower.split('instagram.com/')[1].rstrip('/')
                    updated_links['instagram_id'] = instagram_handle
                elif 'github.com/' in url_lower:
                    github_handle = url_lower.split('github.com/')[1].rstrip('/')
                    updated_links['github_id'] = github_handle
                elif 'telegram.com/' in url_lower:
                    telegram_handle = url_lower.split('telegram.com/')[1]
                    updated_links['telegram_id'] = telegram_handle
                elif 'work' in category_lower or 'website' in category_lower:
                    other_links[category.lower()] = url_lower
                else:
                    other_links[category.lower()] = url_lower
        
            all_other_links = other_links
            profile_info = {
                'name': profile_name,
                'title': profile_title,
                'ph_id': profile_id,
            }
            profile_info.update(updated_links)

            if all_other_links:
                profile_info['others'] = all_other_links
            
            profiles_infos.append(profile_info)

        company_info['team'] = profiles_infos

    except Exception as e:
        print(f"Error occurred while processing profiles: {e}")
        company_info['team'] = []

    # Website cleanup and final LinkedIn processing
    website_url = company_info['website']
    if '?ref=producthunt' in website_url:
        website_url = website_url.replace('?ref=producthunt', '')
    
    company_info['website'] = website_url.strip()

    # Document creation and LinkedIn processing
    try:
        doc_id = each_link.split("/posts/")[1].split("#")[0]
    except:
        doc_id = each_link.split("/products/")[1].split("#")[0]
     
    if '?' in doc_id:
        doc_id = doc_id.split("?")[0]
    
    if 'company_social_temp' in company_info:
        del company_info['company_social_temp']
        print("Removed company_social_temp field")
    
    company_info['created'] = datetime.utcnow()
    company_info['last_updated'] = datetime.utcnow()
    company_info['parallel_number'] = randint(1, 10)
    company_info['id'] = doc_id

    doc_ref = db.collection('ph').document(doc_id)
    doc_ref.set(company_info, merge=True)
    
    # LinkedIn processing for company
    if 'company_social' in company_info and 'li_id' in company_info['company_social']:
        linkedin_id = company_info['company_social']['li_id']
        if '/company/' in linkedin_id:
            linkedin_id = linkedin_id.split("/company/")[1].rstrip("/")
            if '?viewasmember' in linkedin_id:
                linkedin_id = linkedin_id.split("?viewasmember")[0].rstrip("/")
            update_or_create_company_firestore_document(linkedin_id, db, doc_id)
            create_about_task(linkedin_id)
            print("created a company: ", linkedin_id)

    # LinkedIn processing for profiles
    for li_profile in profiles_infos:
        if 'li_id' in li_profile:
            if '?trk' in li_profile['li_id']:
                li_profile['li_id'] = li_profile['li_id'].split("?trk")[0]
            if '&utm' in li_profile['li_id']:
                li_profile['li_id'] = li_profile['li_id'].split("&utm")[0]
            if '?utm' in li_profile['li_id']:
                li_profile['li_id'] = li_profile['li_id'].split("?utm")[0]
            if '?locale' in li_profile['li_id']:
                li_profile['li_id'] = li_profile['li_id'].split("?locale")[0]
            if '/?lipi' in li_profile['li_id']:
                li_profile['li_id']= li_profile['li_id'].split("/?lipi")[0]
            if '/' in li_profile['li_id']:
                li_profile['li_id'] = li_profile['li_id'].split("/")[0]
            li_profile['li_id'] = li_profile['li_id'].rstrip("/")
                
            update_or_create_profile_document(li_profile['li_id'], db, li_profile)
            create_ppl_task(li_profile['li_id'])
            print("created a profile: ", li_profile['li_id'])

# Main execution
task_start_date = time.asctime()
driver = login()
username = ""
password = "2025/2/14"

# # # Define the date range you want to process
start_date = "2025/8/22"  # Starting date
end_date = "2025/8/24"   # Ending date (inclusive)
# # 
yesterday_fulltime = datetime.now() - timedelta(days=1)
formatted_date = yesterday_fulltime.strftime("%Y/%-m/%d")
print(formatted_date)

start_date = end_date = formatted_date

# Call the new sign_in_and_extract with date range
sign_in_and_extract(driver, username, password, start_date, end_date)



# task_end_date = time.asctime()


