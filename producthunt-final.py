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

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate('spherical-list-284723-216944ab15f1.json')
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
    
    chrome_options.add_argument("--incognito")
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
        unprocessed_links = process_daily_leaderboard(driver, page_url, launch_date)

def process_daily_leaderboard(driver, page_url, launch_date):
    last_processed_link=None
    # Modify the search URL if necessary
    if "?ref=header_nav" in page_url:
        search_url = page_url.replace("?ref=header_nav", "/all")
        driver.get(search_url)
    
    links = []
    results = []
    all_search_results = []

    # Infinite scroll until no new elements are loaded
    previous_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        # Scroll to the bottom of the page
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(10)  # Wait for new elements to load (adjust this time if needed)
        
        # Get the updated list of elements
        new_links = driver.find_elements(By.XPATH, "//a[contains(@data-test, 'post-name')]")
        
        # Check if new elements were added
        if len(new_links) > len(links):
            links = new_links  # Update the list with newly loaded elements
        else:
            # If no new elements were added, break the loop
            break
        
        # Check if the scroll height has changed
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == previous_height:
            # If the height hasn't changed, we've reached the bottom
            break
        previous_height = new_height
    
    # Process the collected links
    for link in links:
        all_search_results.append(link.get_attribute("href"))

    # Filter out the already processed links
    if last_processed_link:
        try:
            # Get the index of the last processed link
            start_index = all_search_results.index(last_processed_link) + 1
        except ValueError:
            # If the last_processed_link is not found, process all links
            start_index = 0
    else:
        start_index = 0

    # Return only the links that haven't been processed yet
    unprocessed_links = all_search_results[start_index:]
    
    print(f"Total links found: {len(all_search_results)}")
    print(f"Unprocessed links: {len(unprocessed_links)}")

    for each_link in unprocessed_links:
        try:
            doc_id = each_link.split("/posts/")[1].split("#")[0]
        except:
            doc_id = each_link.split("/products/")[1].split("#")[0]

        doc_ref = db.collection("ph").document(doc_id)
        if doc_ref.get().exists:
            print("not processing this as it already exists")
            continue
            
        print(f"Processing link: {each_link}")
        company_info = {}
        start_time = datetime.now()
        print("Start time: ", start_time)
        
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
                    name = driver.find_element(By.XPATH,"//h1[contains(@class, 'text-dark-gray')]").text
                    company_info['name'] = name
                except:
                    print(f"Error finding name element for {each_link}: {e}")
                    name = ""
                    company_info['name'] = name

        model = 'normal'
        
        
        if 'https://www.producthunt.com/products/' not in each_link:
            
            if moveToElement(driver, "//a[contains(@href, '/products/')]"):
                each_link = driver.find_element_by_xpath("//a[contains(@href, '/products/')]").get_attribute("href")
                driver.get(each_link)
            
       
            
        if 'https://www.producthunt.com/posts/' in each_link:
            if moveToElement(driver, "//a[@class='text-16 font-normal text-blue']"):
                model = 'normal'
            else:
                model = 'no        page'
            print("Model: ", model)
    
            if model == 'normal':
                getNormalmodel(driver, each_link, company_info, launch_date)
            elif model == "no page":
                getNopageModel(driver, each_link, company_info, launch_date)
            else:
                print("Failed to extract model")
                
        if 'https://www.producthunt.com/products/' in each_link:
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
            website = ""
    print("Extracted Website URL:", website)
    company_info['website'] =website

    # try:
    #     links = WebDriverWait(driver, 25).until(
    #         EC.presence_of_all_elements_located((By.XPATH, "//div[contains(text(), 'Links')]/following-sibling::div//a"))
    #     )
    
    #     links_websites = []
    
    #     for link_element in links:
    #         link = link_element.get_attribute('href').lower()
            
    #         span_text = link_element.find_element(By.XPATH, ".//span[@class='truncate']").text.strip()
            
    #         links_websites.append(f"{span_text}:{link}")
    
    #     if links_websites:
    #         first_link = links_websites[0].split(":", 1)[-1]  # Get the link part after the colon
    
    #         company_info['website'] = {'website': first_link}
    
    #         if len(links_websites) > 1:
    #             company_info['website']['additional_links'] = links_websites[1:]
    #     else:
    #         company_info['website'] = None
    
    
    # except Exception as e:
    #     print(f"Error occurred while collecting links: {e}")

    other_Websites = driver.find_elements_by_xpath("//div[@data-sentry-component='Links']//a")
    for website_link in other_Websites:
        extra_link= website_link.get_attribute("href").split("?ref=")[0]
        links_websites.append(extra_link)
    if len(links_websites) > 1:
        company_info['company_social_temp'] = links_websites[1:]
        
            
            
    allowed_social_links = {
        'twitter': 'twitter_id',
        'x': 'twitter_id',
        'facebook': 'facebook_id',
        'linkedin': 'li_id',
        'instagram': 'instagram_id',
        'github': 'github_id'
    }
    
    # social_links_div = driver.find_elements(By.XPATH, "//div[@class='text-14 font-semibold text-dark-gray mb-1' and contains(text(),'Social')]")
    social_links_div = driver.find_elements(By.XPATH, "//div[@class='text-14 font-semibold text-dark-gray mb-1' and contains(text(),'Social')]")
    social_links_dict = {key: [] for key in allowed_social_links.values()}  # Allow multiple links per social category
    other_social_links = {}

    if social_links_div:
        for div in social_links_div:
            sibling_divs = div.find_elements(By.XPATH, "following-sibling::div//a")
            for sibling_div in sibling_divs:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.XPATH, ".//a[@href]"))
                )
                link_soc = sibling_div.get_attribute('href').lower()
                social_name = sibling_div.find_element(By.XPATH, ".//div").text.lower()

                if social_name in allowed_social_links:
                    category = allowed_social_links[social_name]
                    social_links_dict[category].append(link_soc)  # Store link in corresponding category as a list
                else:
                    # If the social_name is not in the allowed list, add it to other_social_links
                    if social_name not in other_social_links:
                        other_social_links[social_name] = []
                    other_social_links[social_name].append(link_soc)
                    

    # Store allowed social links in company_social, filter out empty lists
    company_info['company_social'] = {k: v for k, v in social_links_dict.items() if v}
    
    # Store other social links under 'others' if they exist
    if other_social_links:
        company_info['company_social']['others'] = other_social_links
        
    if company_info['company_social'] == {}:
        try:
            social_links_div = driver.find_element_by_xpath( "//div[@data-sentry-component='SocialLinks']")
           
        
            # Extract all <a> elements within the SocialLinks container
            social_links = social_links_div.find_elements(By.XPATH, ".//a[@href]")
        
            # Loop through the <a> elements to categorize them
            for link in social_links:
                href = link.get_attribute('href')  # Get the href attribute
                # print(f"Found link: {href}")  # Print the href for debugging
        
                # Determine the platform by checking the href or the visible text
                for platform, category in allowed_social_links.items():
                    if platform in href.lower():  # Check if the platform keyword is in the href
                        social_links_dict[category].append(href)  # Add the link to the appropriate category
                        break
                else:
                    # If no match is found, add the link to other_social_links
                    domain = href.split("//")[-1].split("/")[0]  # Extract the domain name
                    if domain not in other_social_links:
                        other_social_links[domain] = []
                    other_social_links[domain].append(href)
                    
            if 'company_social_temp' in company_info and company_info['company_social_temp']:
                for temp_link in company_info['company_social_temp']:
                   for platform, category in allowed_social_links.items():
                       if platform in temp_link.lower():
                           social_links_dict[category].append(temp_link)
                           break
                del company_info['company_social_temp']
                
                
            company_info['company_social'] = {k: v for k, v in social_links_dict.items() if v}
            
            # Store other social links under 'others' if they exist
            if other_social_links:
                company_info['company_social']['others'] = other_social_links

        except:
            company_info['company_social'] = {}
            
    if 'li_id' in company_info['company_social']:
        linkedin_ids = company_info['company_social']['li_id']
        
        # Iterate over each LinkedIn link if there are multiple
        cleaned_linkedin_ids = []
        for linkedin_id in linkedin_ids:
            if '/company/' in linkedin_id:
                linkedin_id = linkedin_id.split("/company/")[1].rstrip("/")
            if '?viewasmember' in linkedin_id:
                linkedin_id = linkedin_id.split("?viewasmember")[0].rstrip("/")
            cleaned_linkedin_ids.append(linkedin_id)
        
        # Update company_social['li_id'] with cleaned values
        company_info['company_social']['li_id'] = cleaned_linkedin_ids

    try:
        links_and_texts = []
        ul_elements = driver.find_elements(By.XPATH, "//ul[contains(@class, 'styles_makerList')]")

        if ul_elements == []:
            ul_elements = driver.find_elements_by_xpath("//div[@data-sentry-component='InfiniteScroll']")
            
        if moveToElement(driver, "//*[contains(text(), 'Show all')]"):
            more_profiles_load = driver.find_elements_by_xpath("//*[contains(text(), 'Show all')]")
            for one_click in more_profiles_load:
                one_click.click()

        for ul_element in ul_elements:
            li_elements = ul_element.find_elements(By.XPATH, ".//li")
            if li_elements == []:
                li_elements = ul_element.find_elements(By.XPATH, ".//section")
            for li in li_elements:
                div_elements = li.find_elements(By.XPATH, ".//div")
                for div in div_elements:
                    a_elements = div.find_elements(By.XPATH, ".//a[@href]")
                    for a in a_elements:
                        href = a.get_attribute('href')
                        links_and_texts.append(href)

        links_of_profiles = list(set(links_and_texts))
        links_of_profiles = [link for link in links_of_profiles if '@deleted' not in link and '@' in link]
        # print()
        profiles_infos = []

        for profile_link in links_of_profiles:
            driver.get(profile_link)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'flex flex-col items-center gap-4')]"))
            )
        
            profile_info = {}
            profile_title = driver.find_element(By.XPATH, "//div[@class='text-18 font-light text-light-gray mb-1']").text
            profile_id = driver.current_url.split("https://www.producthunt.com/@")[1]
            profile_name = driver.find_element(By.XPATH, "//h1[@class='text-24 font-semibold text-dark-gray mb-1']").text
        
            profile_links = {}
            
            try:
                links_div = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'styles_links')]"))
                )
                a_tags = links_div.find_elements(By.XPATH, ".//a[@href]")
                
                for a in a_tags:
                    href = a.get_attribute('href')
                    category = a.find_element(By.XPATH, ".//span").text
                    profile_links[category] = href
                    
            except Exception:
                # print(f"Links div not found or error occurred: {e}")
                # You can initialize profile_links as an empty dict if needed
                profile_links = {}
        
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
                    if '?viewasmember' in link_id:
                        link_id = link_id.split("?viewasmember")[0].rstrip("/")
                    
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
        
            filtered_other_links = {key: other_links[key] for key in ['work', 'website'] if key in other_links}
            remaining_other_links = {key: other_links[key] for key in other_links if key not in ['work', 'website']}
            all_other_links = other_links
            profile_info = {
                'name': profile_name,
                'title': profile_title,
                'ph_id': profile_id,
            }
            profile_info.update(updated_links)

        
            if all_other_links:
                profile_info['others'] = all_other_links
            
            # Append to the profiles list as usual
            profiles_infos.append(profile_info)
            company_info['team'] = profiles_infos

    except Exception as e:
        print(f"Error occurred while processing profiles: {e}")
        company_info['team'] = []


    website_url = company_info['website']
    if '?ref=producthunt' in website_url:
        website_url = website_url.replace('?ref=producthunt', '')
    
    
    try:
        for link in company_info['website'].get('additional_links', []):
            # Split and add to company_social
            key, value = link.split(':', 1)
            company_info['company_social'][key.strip().lower()] = value.strip()
    
        company_info['website'] = website_url.strip()
        if 'company_social' in company_info:
            for key, value in company_info['company_social'].items():
                if isinstance(value, list):
                    company_info['company_social'][key] = value[0] if value else ''
    
    except:
        company_info['website'] = website_url.strip()
        if 'company_social' in company_info:
            for key, value in company_info['company_social'].items():
                if isinstance(value, list):
                    company_info['company_social'][key] = value[0] if value else ''

    try:
        doc_id = each_link.split("/posts/")[1].split("#")[0]
    except:
        doc_id = each_link.split("/products/")[1].split("#")[0]
      
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_date = yesterday.strftime("%d-%m-%Y")

    # company_info['launch_date'] = "30-11-2024"
    company_info['created'] = datetime.utcnow()
    company_info['last_updated']=datetime.utcnow()
    company_info['parallel_number'] = randint(1, 10)
    company_info['id'] = doc_id

    doc_ref = db.collection('ph').document(doc_id)
    doc_ref.set(company_info, merge=True)
    
    if 'li_id' in company_info['company_social']:
        linkedin_id = company_info['company_social']['li_id']
        if '/company/' in linkedin_id:
            linkedin_id = linkedin_id.split("/company/")[1].rstrip("/")
            if '?viewasmember' in linkedin_id:
                linkedin_id = linkedin_id.split("?viewasmember")[0].rstrip("/")
            update_or_create_company_firestore_document(linkedin_id, db, doc_id)
            create_about_task(linkedin_id)
            print("created a company: ",linkedin_id)

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
            print("created a profile: ",li_profile['li_id'])
          

def getNopageModel(driver, each_link, company_info, launch_date):
    # Existing code with launch_date parameter added to these lines
    company_info['launch_date'] = launch_date  # Update this line
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
            website = ""
    print("Extracted Website URL:", website)
    
    company_info['website'] =website
        
    # try:
    #     driver.find_element_by_xpath("//div[@class='text-14 font-semibold text-dark-gray text-center']").click()
    #     original_window = driver.current_window_handle

    #     # Wait for the new tab to open (handle might take some time to appear)
    #     WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))

    #     # Get all window handles and switch to the new tab
    #     new_window = [window for window in driver.window_handles if window != original_window][0]
    #     driver.switch_to.window(new_window)
        
    #     # Get the current URL of the new tab
    #     new_tab_url = driver.current_url
    #     website = new_tab_url
    #     if '?ref=producthunt' in website:
    #         website = website.split("?ref=producthunt")[0]

    #     time.sleep(3)
    #     # Close the new tab
    #     driver.close()
        
    #     # Switch back to the original tab
    #     driver.switch_to.window(original_window)
    
    # except:
    #     try:
    #         driver.find_element_by_xpath("//button[@data-test='get-it-button']").click()
    #         original_window = driver.current_window_handle

    #        # Wait for the new tab to open (handle might take some time to appear)
    #         WebDriverWait(driver, 10).until(EC.number_of_windows_to_be(2))
    
    #         # Get all window handles and switch to the new tab
    #         new_window = [window for window in driver.window_handles if window != original_window][0]
    #         driver.switch_to.window(new_window)
            
    #         # Get the current URL of the new tab
    #         new_tab_url = driver.current_url
    #         website = new_tab_url
    #         if '?ref=producthunt' in website:
    #             website = website.split("?ref=producthunt")[0]
    
    #         # Close the new tab
    #         driver.close()
            
    #         # Switch back to the original tab
    #         driver.switch_to.window(original_window)
              
            
    #     except:
    #         website = ""

    print(website)
    profiles_infos = []
    if moveToElement(driver, "//div[contains(text(), 'About this launch')]") == True:
        about_section = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(text(), 'About this launch')]"))
        )

        # Find the parent div of the "About this launch" section to get its text
        parent_div = about_section.find_element(By.XPATH, './following-sibling::div')
        href_elements = parent_div.find_elements(By.TAG_NAME, 'a')
        links_and_texts = []
        # Loop through each <a> tag and print the href attribute only if it contains '/@'
        for element in href_elements:
            href_value = element.get_attribute('href')
            if '/@' in href_value:
                links_and_texts.append(href_value)

        allowed_social_links = {
            'twitter': 'twitter_id',
            'x': 'twitter_id',  # Treat X as Twitter
            'facebook': 'facebook_id',
            'linkedin': 'li_id',
            'instagram': 'instagram_id',
            'github': 'github_id',
            'telegram': 'telegram_id'  # Treat Telegram as a social link
        }

        links_of_profiles = list(set(links_and_texts))
        links_of_profiles = [link for link in links_of_profiles if '@deleted' not in link]
        # Initialize a list to store profile information
        profiles_infos = []

        for profile_link in links_of_profiles:
            driver.get(profile_link)
             

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'flex flex-col items-center gap-4')]"))
            )
        
            profile_info = {}
            profile_title = driver.find_element(By.XPATH, "//div[@class='text-18 font-light text-light-gray mb-1']").text
            profile_id = driver.current_url.split("https://www.producthunt.com/@")[1]
            profile_name = driver.find_element(By.XPATH, "//h1[@class='text-24 font-semibold text-dark-gray mb-1']").text
        
            profile_links = {}
            
            try:
                links_div = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'styles_links')]"))
                )
                a_tags = links_div.find_elements(By.XPATH, ".//a[@href]")
                
                for a in a_tags:
                    href = a.get_attribute('href')
                    category = a.find_element(By.XPATH, ".//span").text
                    profile_links[category] = href
                    
            except Exception as e:
                # print(f"Links div not found or error occurred: {e}")
                # You can initialize profile_links as an empty dict if needed
                profile_links = {}
        
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
        
            allowed_other_links = ['Work', 'Website']
        
            for category, url in profile_links.items():
                url_lower = url.lower()
                category_lower = category.lower()
                if 'linkedin.com/in/' in url_lower:
                    link_id = url_lower.split('linkedin.com/in/')[1].rstrip('/')
                    updated_links['li_id'] = link_id
                elif 'linkedin.com/company/' in url_lower:
                    link_id = url_lower.split('linkedin.com/company/')[1].rstrip('/')
                    if '?viewasmember' in link_id:
                        link_id = link_id.split("?viewasmember")[0].rstrip("/")
                    
                    if "?trk" in link_id:
                        link_id = link_id.split("?trk")[0].rstrip("/")
                        
                    updated_links['company_li_id'] = link_id
                elif 'twitter.com/' in url_lower or 'x.com/' in url_lower:
                    twitter_handle = url_lower.split('twitter.com/')[1] if 'twitter.com/' in url_lower else url_lower.split('x.com/')[1]
                    updated_links['twitter_id'] = twitter_handle
                elif 'facebook.com/' in url_lower:
                    facebook_handle = url_lower.split('facebook.com/')[1].rstrip("/")
                    updated_links['facebook_id'] = facebook_handle
                elif 'instagram.com/' in url_lower:
                    instagram_handle = url_lower.split('instagram.com/')[1].rstrip("/")
                    updated_links['instagram_id'] = instagram_handle
                elif 'github.com/' in url_lower:
                    github_handle = url_lower.split('github.com/')[1].rstrip("/")
                    updated_links['github_id'] = github_handle
                elif 'telegram.com/' in url_lower:
                    telegram_handle = url_lower.split('telegram.com/')[1].rstrip("/")
                    updated_links['telegram_id'] = telegram_handle
                elif 'work' in category_lower or 'website' in category_lower:
                    other_links[category.lower()] = url_lower
                else:
                    other_links[category.lower()] = url_lower
        
            filtered_other_links = {key: other_links[key] for key in ['work', 'website'] if key in other_links}
            remaining_other_links = {key: other_links[key] for key in other_links if key not in ['work', 'website']}
        
            profile_info = {
                'name': profile_name,
                'title': profile_title,
                'ph_id': profile_id,
            }
            profile_info.update(updated_links)
        
            if filtered_other_links:
                profile_info['other_links'] = filtered_other_links
        
            if remaining_other_links:
                profile_info['others'] = remaining_other_links
        
            profiles_infos.append(profile_info)
            company_info['team'] = profiles_infos

    else:
        
        company_info['team'] = []


            
    company_info['website'] = website
    company_info['company_social']=  {}
    # Znew_company_info = process_company_info(company_info)
    try:
        doc_id = each_link.split("/posts/")[1].split("#")[0]
    except:
        doc_id = each_link.split("/products/")[1].split("#")[0]
        
    # doc_id = doc_id.
    yesterday = datetime.now() - timedelta(days=1)
    yesterday_date = yesterday.strftime("%d-%m-%Y")

    # company_info['launch_date'] = "19-11-2024"
    company_info['created'] = datetime.utcnow()
    company_info['last_updated']=datetime.utcnow()
    company_info['parallel_number'] = randint(1, 10)
    company_info['id'] = doc_id

    doc_ref = db.collection('ph').document(doc_id)
    doc_ref.set(company_info, merge=True)

    
   
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
            print("created a profile: ",li_profile['li_id'])



# Main execution
task_start_date = time.asctime()
driver = login()
username = ""
password = "2025/2/14"

# # # Define the date range you want to process
# start_date = "2025/5/20"  # Starting date
# end_date = "2025/5/20"   # Ending date (inclusive)
# # 
yesterday_fulltime = datetime.now() - timedelta(days=1)
formatted_date = yesterday_fulltime.strftime("%Y/%-m/%d")
print(formatted_date)

start_date = end_date = formatted_date

# Call the new sign_in_and_extract with date range
sign_in_and_extract(driver, username, password, start_date, end_date)

task_end_date = time.asctime()