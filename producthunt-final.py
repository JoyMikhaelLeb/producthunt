#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 26 23:07:22 2024

@author: joy

Converted to nodriver for better bot detection avoidance
"""

import time
import asyncio
from random import randint
from create_numerical_task import create_about_task, create_ppl_task
import nodriver as uc
import json
import os
import re
from datetime import datetime, timedelta
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from urllib.parse import urljoin

# Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate('spherical-list-284723-216944ab15f1.json')
    default_app = firebase_admin.initialize_app(cred)

db = firestore.client()


async def safe_evaluate(page, script):
    """Helper function to safely evaluate JavaScript and extract values from nodriver's RemoteObject"""
    try:
        result = await page.evaluate(script)

        # If result has a value attribute, extract it
        if hasattr(result, 'value'):
            return result.value

        # If result is already a primitive type, return it
        if isinstance(result, (str, int, float, bool, list, dict, type(None))):
            return result

        # Try to convert to dict if it has items
        if hasattr(result, '__dict__'):
            return result.__dict__

        return result
    except Exception as e:
        print(f"Error in safe_evaluate: {e}")
        return None


async def moveToElement(page, target_selector):
    """Move to element using nodriver"""
    try:
        element = await page.select(target_selector, timeout=7)
        if element:
            await element.scroll_into_view()
            await asyncio.sleep(0.5)
            return True
        return False
    except Exception as e:
        print(f"Error moving to element: {e}")
        return False


async def login():
    """Initialize nodriver browser - automatically bypasses bot detection"""
    url = 'https://www.producthunt.com/'

    # nodriver automatically handles anti-bot measures
    # Use browser_executable_path if you have Chrome/Chromium installed in a specific location
    browser = await uc.start(
        headless=False,  # Set to True for headless mode
        sandbox=False,  # Disable sandbox (required on some systems)
        browser_args=[
            '--disable-dev-shm-usage',
            '--start-maximized',
            '--disable-blink-features=AutomationControlled',
        ]
    )

    # Get the main tab
    page = await browser.get(url)
    await asyncio.sleep(3)

    return browser, page


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
        "parallel_number": randint(1, 10),
        "last_updated": datetime.utcnow(),
        "id": profile_id,
        "created": datetime.utcnow()
    }

    if profile_doc.exists:
        profile_doc_ref.set({"ph_id": profile_info['ph_id'], "last_updated": datetime.utcnow()}, merge=True)
        print(f"Updated existing profile document for profile_id: {profile_id}")
    else:
        profile_doc_ref.set(additional_fields)
        print(f"Created new profile document for profile_id: {profile_id} with fields: {additional_fields}")


async def sign_in_and_extract(page, username, password, start_date, end_date, last_processed_link=None):
    """
    Iterate through dates from start_date to end_date and process Product Hunt leaderboard

    Args:
    - page: nodriver page object
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
        # Format the date for the URL and launch date
        url_date = current_date.strftime("%Y/%m/%d")
        launch_date = current_date.strftime("%d-%m-%Y")

        # Construct the page URL
        page_url = f"https://www.producthunt.com/leaderboard/daily/{url_date}?ref=header_nav"
        print(f"Processing date: {url_date}")

        # Process the daily leaderboard
        await process_daily_leaderboard(
            page, page_url, launch_date,
            last_processed_link=None,
            initial_wait=8,
            max_no_content_attempts=8,
            max_scroll_attempts=150,
            max_links=1000,
            base_url=None
        )


async def process_daily_leaderboard(page, page_url, launch_date, last_processed_link=None,
                              initial_wait=8,
                              max_no_content_attempts=8,
                              max_scroll_attempts=150,
                              max_links=1000,
                              base_url=None):
    """
    Scrape links from lazy-loading leaderboard page using nodriver.
    Returns list of unprocessed absolute URLs.
    """
    # Navigate
    if "?ref=header_nav" in page_url:
        search_url = page_url.replace("?ref=header_nav", "/all")
        await page.get(search_url)
    else:
        await page.get(page_url)

    if base_url is None:
        base_url = page_url

    # Initial wait for page to load
    await asyncio.sleep(initial_wait)

    all_search_results = []
    seen = set()

    no_new_content_count = 0
    scroll_attempts = 0
    prev_link_count = 0

    # Helper function to clean URLs
    def clean_url(url):
        """Remove ?ref=footer or /reviews from the end of URLs"""
        if '?ref=footer' in url:
            url = url.split('?ref=footer')[0]
        if url.endswith('/reviews'):
            url = url[:-8]
        return url

    print("Starting to extract product links...")

    while scroll_attempts < max_scroll_attempts:
        scroll_attempts += 1

        # Get page HTML source
        try:
            html_content = await page.get_content()

            # Extract product URLs using regex
            pattern = r'href=["\'](https?://www\.producthunt\.com/products/[^"\']+)["\']'
            matches = re.findall(pattern, html_content)

            # Also try to find /posts/ URLs
            pattern_posts = r'href=["\'](/products/[^"\']+)["\']'
            relative_matches = re.findall(pattern_posts, html_content)

            # Convert relative URLs to absolute
            for rel_url in relative_matches:
                abs_url = urljoin(base_url, rel_url)
                matches.append(abs_url)

            # Clean and deduplicate URLs
            for url in matches:
                cleaned_url = clean_url(url)
                if cleaned_url not in seen:
                    seen.add(cleaned_url)
                    all_search_results.append(cleaned_url)

            current_link_count = len(all_search_results)

        except Exception as e:
            print(f"Error extracting links: {e}")
            current_link_count = len(all_search_results)

        print(f"Scroll attempt {scroll_attempts}: Total unique links found: {current_link_count}")

        # Check if new links were added
        if current_link_count > prev_link_count:
            no_new_content_count = 0
            added = current_link_count - prev_link_count
            print(f"SUCCESS: links increased to {current_link_count} (added {added})")

            # Show sample of newly added links
            if all_search_results:
                sample_size = min(3, len(all_search_results))
                print(f"Sample links: {all_search_results[-sample_size:]}")
        else:
            no_new_content_count += 1
            print(f"No new links found (attempt {no_new_content_count}/{max_no_content_attempts})")

        prev_link_count = current_link_count

        # Stop conditions
        if no_new_content_count >= max_no_content_attempts:
            print(f"Stopping: No new content after {max_no_content_attempts} consecutive attempts.")
            break

        if len(all_search_results) >= max_links:
            print(f"Stopping: reached max_links={max_links}.")
            break

        # Scroll to load more content (slower scrolling for better loading)
        try:
            await page.evaluate('window.scrollBy(0, 800)')
            await asyncio.sleep(5)  # Increased from 3 to 5 seconds
        except Exception as e:
            print(f"Scroll error: {e}")
            await asyncio.sleep(5)

    # Determine the start index based on last_processed_link
    if last_processed_link:
        try:
            start_index = all_search_results.index(last_processed_link) + 1
        except ValueError:
            start_index = 0
    else:
        start_index = 0

    unprocessed_links = all_search_results[start_index:]

    print(f"Total links found: {len(all_search_results)}")
    print(f"Unprocessed links: {len(unprocessed_links)}")

    # Process each link
    for each_link in unprocessed_links:
        try:
            doc_id = each_link.split("/posts/")[1].split("#")[0]
        except:
            doc_id = each_link.split("/products/")[1].split("#")[0]

        if '?' in doc_id:
            doc_id = doc_id.split("?")[0]

        # Always process the link (even if it exists in Firebase)
        print(f"Processing link: {each_link}")
        company_info = {}
        start_time = datetime.now()
        print("Start time: ", start_time)

        # Navigate to makers page
        await page.get(each_link + "/makers/")

        if '?' in each_link:
            await page.get(each_link.split("?")[0])
        else:
            await page.get(each_link.split("#")[0])

        await asyncio.sleep(2)

        # Extract product name
        try:
            name_elem = await page.select("h1.font-bold.text-dark-gray", timeout=5)
            if name_elem:
                name = await name_elem.text
                company_info['name'] = name
            else:
                raise Exception("Name not found")
        except:
            try:
                name_elem = await page.select("div.text-24.font-semibold.text-dark-gray", timeout=5)
                if name_elem:
                    name = await name_elem.text
                    company_info['name'] = name
                else:
                    raise Exception("Name not found")
            except:
                try:
                    name_elem = await page.select("h1.text-24.font-semibold.text-gray-", timeout=5)
                    if name_elem:
                        name = await name_elem.text
                        company_info['name'] = name
                    else:
                        name = ""
                        company_info['name'] = name
                except:
                    print(f"Error finding name element for {each_link}")
                    name = ""
                    company_info['name'] = name

        # Process based on URL type
        if 'https://www.producthunt.com/posts/' in each_link:
            print("Processing posts URL")
            if await moveToElement(page, "a.text-16.font-normal.text-blue"):
                await getNormalmodel(page, each_link, company_info, launch_date)
            elif 'https://www.producthunt.com/products/' in page.url:
                print("Redirected to products page")
                await getNormalmodel(page, each_link, company_info, launch_date)
            else:
                print("No page model detected")

        elif 'https://www.producthunt.com/products/' in each_link:
            await getNormalmodel(page, each_link, company_info, launch_date)

        else:
            print("Handling alternative URL format")
            try:
                product_link_elem = await page.select("a[href*='/products/']", timeout=5)
                if product_link_elem:
                    each_link = await product_link_elem.get_attribute("href")
                    await page.get(each_link)
                    await getNormalmodel(page, each_link, company_info, launch_date)
            except:
                print("Could not find product link")

        end_time = datetime.now()
        time_taken = end_time - start_time
        print(f"Time taken for {each_link}: {time_taken}")

    return unprocessed_links


async def getNormalmodel(page, each_link, company_info, launch_date):
    """Extract product information and team details using same paths as BeautifulSoup script"""

    company_info['launch_date'] = launch_date

    # Navigate to makers page
    try:
        a_class_elem = await page.select("a.text-16.font-normal.text-blue", timeout=5)
        if a_class_elem:
            a_class_link = await a_class_elem.get_attribute('href')
            await page.get(a_class_link + "/makers")
        else:
            raise Exception("Link not found")
    except:
        current_url = page.url
        if "?" in current_url:
            link_to_get = current_url.split("?")[0]
            await page.get(link_to_get + "/makers")
        else:
            await page.get(current_url + "/makers")

    await asyncio.sleep(5)

    # Get page HTML content for extraction
    html_content = await page.get_content()

    # Extract product name from HTML (same as BeautifulSoup approach)
    name = ""
    # Try: <h2 class="text-24 font-semibold text-gray-900">Product Name</h2>
    name_match = re.search(r'<h2[^>]*class="[^"]*text-24[^"]*font-semibold[^"]*"[^>]*>([^<]+)</h2>', html_content)
    if name_match:
        name = name_match.group(1).strip()
        print(f"✓ Extracted name from h2: {name}")

    # Fallback: Try h1 with similar classes
    if not name:
        name_match = re.search(r'<h1[^>]*class="[^"]*font-semibold[^"]*"[^>]*>([^<]+)</h1>', html_content)
        if name_match:
            name = name_match.group(1).strip()
            print(f"✓ Extracted name from h1: {name}")

    # Fallback: Try from meta tag
    if not name:
        meta_match = re.search(r'<meta property="og:title" content="([^"]+)"', html_content)
        if meta_match:
            # Meta title format: "Product Name - Description | Product Hunt"
            full_title = meta_match.group(1)
            if ' - ' in full_title:
                name = full_title.split(' - ')[0].strip()
            elif ' | ' in full_title:
                name = full_title.split(' | ')[0].strip()
            else:
                name = full_title.strip()
            print(f"✓ Extracted name from meta: {name}")

    company_info['name'] = name or ""
    print(f"Product name: {company_info['name']}")

    # Extract website URL from JSON in script tag (same as BeautifulSoup)
    website = ""
    if '"websiteUrl":"' in html_content:
        start = html_content.find('"websiteUrl":"') + len('"websiteUrl":"')
        end = html_content.find('"', start)
        website = html_content[start:end]
        print(f"✓ Extracted website from JSON: {website}")

    # Fallback: extract from anchor tag
    if not website:
        try:
            website_elem = await page.select("a[href^='http']", timeout=3)
            if website_elem:
                href = await website_elem.get_attribute("href")
                if href and "producthunt.com" not in href:
                    website = href
                    print(f"✓ Extracted website from anchor: {website}")
        except:
            pass

    company_info['website'] = website or ""
    print(f"Website: {company_info['website']}")

    # Extract social links from JSON in script tag (same as BeautifulSoup)
    links_websites = []

    # Twitter URL
    if '"twitterUrl":"' in html_content:
        start = html_content.find('"twitterUrl":"') + len('"twitterUrl":"')
        if html_content[start:start+4] == 'http':
            end = html_content.find('"', start)
            twitter_url = html_content[start:end]
            if twitter_url:
                links_websites.append(twitter_url)
                print(f"✓ Found Twitter from JSON: {twitter_url}")

    # LinkedIn URL
    if '"linkedinUrl":"' in html_content:
        start = html_content.find('"linkedinUrl":"') + len('"linkedinUrl":"')
        if html_content[start:start+4] == 'http':
            end = html_content.find('"', start)
            linkedin_url = html_content[start:end]
            if linkedin_url:
                links_websites.append(linkedin_url)
                print(f"✓ Found LinkedIn from JSON: {linkedin_url}")

    # Facebook URL
    if '"facebookUrl":"' in html_content:
        start = html_content.find('"facebookUrl":"') + len('"facebookUrl":"')
        if html_content[start:start+4] == 'http':
            end = html_content.find('"', start)
            facebook_url = html_content[start:end]
            if facebook_url:
                links_websites.append(facebook_url)
                print(f"✓ Found Facebook from JSON: {facebook_url}")

    # Instagram URL
    if '"instagramUrl":"' in html_content:
        start = html_content.find('"instagramUrl":"') + len('"instagramUrl":"')
        if html_content[start:start+4] == 'http':
            end = html_content.find('"', start)
            instagram_url = html_content[start:end]
            if instagram_url:
                links_websites.append(instagram_url)
                print(f"✓ Found Instagram from JSON: {instagram_url}")

    # GitHub URL
    if '"githubUrl":"' in html_content:
        start = html_content.find('"githubUrl":"') + len('"githubUrl":"')
        if html_content[start:start+4] == 'http':
            end = html_content.find('"', start)
            github_url = html_content[start:end]
            if github_url:
                links_websites.append(github_url)
                print(f"✓ Found GitHub from JSON: {github_url}")

    # Process social links using the same logic as BeautifulSoup script
    def process_social_links_dict(links_list, main_website=""):
        """Convert a list of social links into a categorized dictionary"""
        if not links_list:
            return {}

        main_website_clean = main_website.lower().split('?ref=')[0].rstrip('/') if main_website else ""
        result = {}

        def set_or_append(key, val):
            if not val:
                return
            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(val)
            else:
                result[key] = val

        for link in links_list:
            link_clean = link.lower().split('?ref=')[0].rstrip('/')

            # Skip if it's the main website
            if main_website_clean and link_clean == main_website_clean:
                continue

            # Categorize the link
            if 'twitter.com/' in link_clean or 'x.com/' in link_clean:
                set_or_append('twitter_id', link)
            elif 'linkedin.com/in/' in link_clean:
                # Extract LinkedIn ID (everything after /in/)
                match = re.search(r'linkedin\.com/in/([^/?]+)', link_clean)
                if match:
                    li_id = match.group(1)
                    set_or_append('li_id', li_id)
                else:
                    set_or_append('li_id', link)
            elif 'linkedin.com/newsletters/' in link_clean:
                # Newsletter links go to 'others', not 'li_id'
                set_or_append('others', link)
            elif 'linkedin.com/' in link_clean:
                set_or_append('li_id', link)
            elif 'facebook.com/' in link_clean:
                set_or_append('facebook_id', link)
            elif 'instagram.com/' in link_clean:
                set_or_append('instagram_id', link)
            elif 'github.com/' in link_clean:
                set_or_append('github_id', link)
            else:
                set_or_append('others', link)

        # Deduplicate and flatten single-item lists
        for key, val in list(result.items()):
            if isinstance(val, list):
                seen = set()
                dedup = []
                for item in val:
                    if item not in seen:
                        dedup.append(item)
                        seen.add(item)
                if len(dedup) == 1 and key != 'others':
                    result[key] = dedup[0]
                else:
                    result[key] = dedup

        return result

    # Process the social links we extracted from JSON
    company_info['company_social'] = process_social_links_dict(links_websites, website)
    print(f"✓ Processed social links: {company_info.get('company_social', {})}")

    # Extract team members from HTML using same approach as BeautifulSoup
    try:
        links_of_profiles = []

        # Find all profile links from maker cards in HTML
        # Pattern: href="/users/@username"
        profile_pattern = r'href=["\'](https://www\.producthunt\.com/@[^"\']+)["\']'
        profile_matches = re.findall(profile_pattern, html_content)

        # Also try relative URLs
        profile_pattern_rel = r'href=["\'](/@[^"\']+)["\']'
        profile_rel_matches = re.findall(profile_pattern_rel, html_content)

        # Convert relative to absolute
        for rel_url in profile_rel_matches:
            abs_url = f"https://www.producthunt.com{rel_url}"
            profile_matches.append(abs_url)

        # Deduplicate and filter
        links_of_profiles = list(set(profile_matches))
        links_of_profiles = [link for link in links_of_profiles if '@deleted' not in link and '@' in link]

        print(f"✓ Found {len(links_of_profiles)} profile links")

        profiles_infos = []

        for profile_link in links_of_profiles:
            try:
                await page.get(profile_link)
                await asyncio.sleep(2)

                # Get profile HTML
                profile_html = await page.get_content()

                # Extract profile name and title from JSON in script tag
                name = ""
                title = ""
                ph_id = profile_link.split("/@")[1] if "/@" in profile_link else ""

                # Extract from JSON: '"profile":{"__typename":"User","name":"...", "headline":"..."}'
                name_match = re.search(r'"profile":\{[^}]+?"name":"([^"]+)"', profile_html)
                if name_match:
                    name = name_match.group(1)
                    print(f"  ✓ Found profile: {name}")

                title_match = re.search(r'"headline":"([^"]*)"', profile_html)
                if title_match:
                    title = title_match.group(1)

                # Extract social links from "Links" section in HTML
                profile_social_links = []

                # Find links after "Links" heading
                if 'Links</h2>' in profile_html or 'Links" class=' in profile_html:
                    # Extract all href values after Links section
                    links_section_start = profile_html.find('Links</h2>')
                    if links_section_start == -1:
                        links_section_start = profile_html.find('Links"')

                    if links_section_start != -1:
                        links_section = profile_html[links_section_start:links_section_start+5000]
                        social_pattern = r'href=["\'](https?://[^"\'>]+)["\']'
                        social_matches = re.findall(social_pattern, links_section)

                        for href in social_matches:
                            if "producthunt.com" not in href:
                                clean_href = href.split("?ref=")[0].rstrip("/")
                                profile_social_links.append(clean_href)
                                print(f"    ↳ Found link: {clean_href}")

                profile_info = {"name": name, "title": title, "ph_id": ph_id}

                # Process profile social links
                if profile_social_links:
                    processed_socials = process_social_links_dict(profile_social_links)
                    profile_info.update(processed_socials)

                profiles_infos.append(profile_info)

            except Exception as e:
                print(f"  ✗ Error processing profile {profile_link}: {e}")
                continue

        company_info['team'] = profiles_infos
        print(f"✓ Total team members processed: {len(profiles_infos)}")

    except Exception as e:
        print(f"✗ Error occurred while processing profiles: {e}")
        company_info['team'] = []

    # Save to Firestore
    try:
        doc_id = each_link.split("/posts/")[1].split("#")[0]
    except:
        doc_id = each_link.split("/products/")[1].split("#")[0]

    if '?' in doc_id:
        doc_id = doc_id.split("?")[0]

    company_info['created'] = datetime.utcnow()
    company_info['last_updated'] = datetime.utcnow()
    company_info['parallel_number'] = randint(1, 10)
    company_info['id'] = doc_id

    # Ensure no temp fields exist before saving
    if 'company_social_temp' in company_info:
        del company_info['company_social_temp']
        print("✓ Removed company_social_temp")

    print(f"\n{'='*60}")
    print(f"Saving to Firebase: {doc_id}")
    print(f"{'='*60}")

    doc_ref = db.collection('ph').document(doc_id)
    doc_ref.set(company_info, merge=True)
    print(f"✓ Saved to Firebase")

    # Process LinkedIn for company
    if 'company_social' in company_info and 'li_id' in company_info['company_social']:
        linkedin_id = company_info['company_social']['li_id']
        if '/company/' in linkedin_id or 'linkedin.com/company/' in linkedin_id:
            if 'linkedin.com/company/' in linkedin_id:
                linkedin_id = linkedin_id.split("linkedin.com/company/")[1]
            elif '/company/' in linkedin_id:
                linkedin_id = linkedin_id.split("/company/")[1]

            # Clean: remove trailing /, query params, and everything after any remaining /
            linkedin_id = linkedin_id.rstrip("/").split("?")[0].split("/")[0]

            # Validate linkedin_id is not empty before creating document
            if linkedin_id and linkedin_id.strip():
                update_or_create_company_firestore_document(linkedin_id, db, doc_id)
                create_about_task(linkedin_id)
                print(f"✓ Created company task: {linkedin_id}")
            else:
                print(f"⚠ Skipping empty LinkedIn ID for company")

    # Process LinkedIn for profiles
    for li_profile in company_info.get('team', []):
        if 'li_id' in li_profile:
            li_id = li_profile['li_id']
            # Clean up LinkedIn ID
            for param in ['?trk', '&utm', '?utm', '?locale', '/?lipi']:
                if param in li_id:
                    li_id = li_id.split(param)[0]

            if '/' in li_id:
                li_id = li_id.split("/")[0]
            li_id = li_id.rstrip("/")

            # Validate li_id is not empty before creating document
            if li_id and li_id.strip():
                li_profile['li_id'] = li_id
                update_or_create_profile_document(li_id, db, li_profile)
                create_ppl_task(li_id)
                print(f"✓ Created profile task: {li_id}")
            else:
                print(f"⚠ Skipping empty LinkedIn ID for profile")



async def main():
    """Main execution function"""
    task_start_date = time.asctime()
    print(f"Task started at: {task_start_date}")

    browser = None
    try:
        # Initialize browser
        print("Initializing browser...")
        browser, page = await login()
        print("Browser initialized successfully!")

        username = ""
        password = ""

        # Calculate yesterday's date
        yesterday_fulltime = datetime.now() - timedelta(days=1)
        # Format date without leading zeros (cross-platform compatible)
        formatted_date = f"{yesterday_fulltime.year}/{yesterday_fulltime.month}/{yesterday_fulltime.day}"
        print(f"Processing date: {formatted_date}")

        start_date = end_date = formatted_date

        # Uncomment to process specific date range:
        # start_date = "2025/8/22"
        # end_date = "2025/8/24"

        # Process Product Hunt data
        await sign_in_and_extract(page, username, password, start_date, end_date)
        print("Processing completed successfully!")

    except KeyboardInterrupt:
        print("\nScript interrupted by user")
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Close browser gracefully
        if browser:
            try:
                print("Closing browser...")
                browser.stop()
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error closing browser: {e}")


# Run the async main function
if __name__ == "__main__":
    asyncio.run(main())
