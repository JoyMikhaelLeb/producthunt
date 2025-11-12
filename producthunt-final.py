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
    browser = await uc.start(
        headless=False,  # Set to True for headless mode
        browser_args=[
            '--no-sandbox',
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
    prev_anchor_count = 0

    # Use CSS selectors for better compatibility with nodriver
    anchors_selector = "[data-test*='post-name'] a"
    containers_selector = "[data-test*='post-name']"

    while scroll_attempts < max_scroll_attempts:
        scroll_attempts += 1

        # Get current counts BEFORE scrolling
        containers = None
        anchors = None
        try:
            # Use query_selector_all via evaluate for better reliability
            containers = await page.query_selector_all(containers_selector)
            anchors = await page.query_selector_all(anchors_selector)
            current_container_count = len(containers) if containers else 0
            current_anchor_count = len(anchors) if anchors else 0
        except Exception as e:
            print(f"Error getting elements: {e}")
            current_container_count = 0
            current_anchor_count = 0

        print(f"Scroll attempt {scroll_attempts}: containers={current_container_count}, anchors={current_anchor_count}")

        # Scroll to trigger lazy loading
        if containers and len(containers) > 0:
            try:
                last_container = containers[-1]
                await last_container.scroll_into_view()
                await asyncio.sleep(2)
                await page.evaluate('window.scrollBy(0, 200)')
                await asyncio.sleep(4)
            except Exception as e:
                print("Targeted scroll failed:", e)
                await page.evaluate('window.scrollBy(0, 400)')
                await asyncio.sleep(4)
        else:
            await page.evaluate('window.scrollBy(0, 400)')
            await asyncio.sleep(4)

        # Re-fetch anchors after waiting
        try:
            anchors = await page.query_selector_all(anchors_selector)
            new_anchor_count = len(anchors) if anchors else 0
        except Exception as e:
            print(f"Error re-fetching anchors: {e}")
            anchors = None
            new_anchor_count = 0

        # Determine whether new anchors were added
        if new_anchor_count > prev_anchor_count:
            no_new_content_count = 0
            added = new_anchor_count - prev_anchor_count
            print(f"SUCCESS: anchors increased to {new_anchor_count} (added {added})")
        else:
            no_new_content_count += 1
            print(f"No new anchors found (attempt {no_new_content_count}/{max_no_content_attempts})")

        prev_anchor_count = new_anchor_count

        # Extract URLs from anchors
        missing_href_count = 0
        if anchors:
            for a in anchors:
                href = None
                try:
                    href = await a.get_attribute("href")
                except:
                    href = None

                # Fallback to common data attributes
                if not href or href.strip() == "":
                    try:
                        href = (await a.get_attribute("data-href") or
                                await a.get_attribute("data-url") or
                                await a.get_attribute("data-link") or
                                await a.get_attribute("data-qa-url"))
                    except:
                        href = None

                if not href or href.strip() == "":
                    missing_href_count += 1
                    continue

                # Normalize relative URLs
                try:
                    abs_href = urljoin(base_url, href.strip())
                except:
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

        await asyncio.sleep(1.0)

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

        doc_ref = db.collection("ph").document(doc_id)
        if doc_ref.get().exists:
            print("not processing this as it already exists")
            continue

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
    """Extract product information and team details"""

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
    links_websites = []

    # Extract website URL from script tag
    try:
        script_content = await page.evaluate('''() => {
            const scriptTag = document.querySelector('script[type="application/json"]');
            return scriptTag ? scriptTag.innerHTML : '';
        }''')

        if script_content:
            start_keyword = '"websiteUrl":"'
            start_index = script_content.find(start_keyword)
            if start_index != -1:
                start_index += len(start_keyword)
                end_index = script_content.find('"', start_index)
                website = script_content[start_index:end_index]
            else:
                website = ""
        else:
            website = ""

        if website == "l.for(" or website == "":
            try:
                website_elem = await page.select("div[data-sentry-component='Links'] a", timeout=3)
                if website_elem:
                    website = await website_elem.get_attribute("href")
                else:
                    raise Exception("Website not found")
            except:
                try:
                    website_elem = await page.select("div[data-sentry-component='Status'] a", timeout=3)
                    if website_elem:
                        website_url = await website_elem.get_attribute("href")
                        website = website_url.split("?ref")[0] if "?ref" in website_url else website_url
                    else:
                        website = ""
                except:
                    website = ""

        print("Extracted Website URL:", website)
        company_info['website'] = website

    except Exception as e:
        print(f"Error extracting website: {e}")
        company_info['website'] = ""

    # Extract all additional website links
    try:
        # Get links from Status section
        other_website_elems = await page.select_all("div[data-sentry-component='Status'] a")
        if other_website_elems:
            for website_link in other_website_elems:
                extra_link = await website_link.get_attribute("href")
                if extra_link:
                    extra_link = extra_link.split("?ref=")[0]
                    links_websites.append(extra_link)

        # Get links from Social Links section
        social_website_elems = await page.select_all("div[data-sentry-component='SocialLinks'] ~ div a")
        if social_website_elems:
            for social_link in social_website_elems:
                extra_link = await social_link.get_attribute("href")
                if extra_link:
                    extra_link = extra_link.split("?ref=")[0]
                    if extra_link not in links_websites:
                        links_websites.append(extra_link)

        print(f"Found all links: {links_websites}")

        # Filter social and special links
        if len(links_websites) > 0:
            filtered_links = [link for link in links_websites if link != website]

            social_and_special_links = []
            for link in filtered_links:
                link_lower = link.lower()
                if any(platform in link_lower for platform in [
                    'twitter.com/', 'x.com/', 'facebook.com/', 'linkedin.com/',
                    'instagram.com/', 'github.com/', 'medium.com/', 'telegram.com/',
                    'producthunt.com/r/', 'play.google.com/store', 'apps.apple.com',
                    'itunes.apple.com', 'chrome.google.com/webstore',
                    'marketplace.visualstudio.com'
                ]):
                    social_and_special_links.append(link)
                    print(f"Added social/special link: {link}")

            company_info['company_social_temp'] = social_and_special_links if social_and_special_links else []
        else:
            company_info['company_social_temp'] = []

    except Exception as e:
        print(f"Error extracting additional website links: {e}")
        company_info['company_social_temp'] = []

    # Process social links
    allowed_social_links = {
        'twitter': 'twitter_id',
        'x': 'twitter_id',
        'facebook': 'facebook_id',
        'linkedin': 'li_id',
        'instagram': 'instagram_id',
        'github': 'github_id'
    }

    social_links_dict = {key: [] for key in allowed_social_links.values()}
    other_social_links = []

    try:
        social_links_divs = await page.select_all("div[data-sentry-component='SocialLinks']")

        if social_links_divs:
            print("Processing SocialLinks div...")
            for div in social_links_divs:
                # Get sibling div links
                sibling_links = await page.evaluate('''(div) => {
                    const links = [];
                    let nextSibling = div.nextElementSibling;
                    while (nextSibling) {
                        const anchors = nextSibling.querySelectorAll('a');
                        anchors.forEach(a => {
                            if (a.href) {
                                const divText = a.querySelector('div') ? a.querySelector('div').textContent : '';
                                links.push({href: a.href, text: divText});
                            }
                        });
                        nextSibling = nextSibling.nextElementSibling;
                    }
                    return links;
                }''', div)

                for link_data in sibling_links:
                    link_soc = link_data['href']
                    social_name = link_data['text'].lower() if link_data['text'] else ''

                    print(f"Found social link: {link_soc}")

                    # Determine social platform from URL if name not available
                    if not social_name:
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

                    if social_name in allowed_social_links:
                        category = allowed_social_links[social_name]

                        if social_name == 'linkedin':
                            # Extract LinkedIn handle
                            clean_href = link_soc.split('?')[0] if '?' in link_soc else link_soc
                            clean_href_lower = clean_href.lower()

                            if '/company/' in clean_href_lower:
                                handle = clean_href.split('/company/')[1].split('/')[0]
                            elif '/in/' in clean_href_lower:
                                handle = clean_href.split('/in/')[1].split('/')[0]
                            elif '/products/' in clean_href_lower:
                                handle = clean_href
                            else:
                                handle = clean_href.split('linkedin.com/')[1].split('/')[0]

                            social_links_dict[category].append(handle)
                            print(f"Added LinkedIn handle {handle}")
                        else:
                            social_links_dict[category].append(link_soc)
                            print(f"Added {link_soc} to {category}")
                    else:
                        other_social_links.append(link_soc)
                        print(f"Added {link_soc} to other_social_links")

    except Exception as e:
        print(f"Error processing social links: {e}")

    # Store social links
    company_info['company_social'] = {k: v for k, v in social_links_dict.items() if v}

    if other_social_links:
        company_info['company_social']['others'] = other_social_links

    print(f"After Social Links processing: {company_info.get('company_social', {})}")

    # Process company_social_temp into final structure
    if 'company_social_temp' in company_info and company_info['company_social_temp']:
        print("Processing company_social_temp...")
        main_website = company_info.get('website', '').lower()
        main_website_clean = main_website.split('?ref=')[0] if '?ref=' in main_website else main_website

        for temp_link in company_info['company_social_temp']:
            temp_link_clean = temp_link.lower().split('?ref=')[0] if '?ref=' in temp_link.lower() else temp_link.lower()

            if main_website_clean and temp_link_clean == main_website_clean:
                continue

            found_social = False
            temp_link_lower = temp_link.lower()

            if 'twitter.com/' in temp_link_lower or 'x.com/' in temp_link_lower:
                if 'twitter_id' not in company_info['company_social']:
                    company_info['company_social']['twitter_id'] = []
                elif not isinstance(company_info['company_social']['twitter_id'], list):
                    company_info['company_social']['twitter_id'] = [company_info['company_social']['twitter_id']]
                company_info['company_social']['twitter_id'].append(temp_link)
                found_social = True

            elif 'facebook.com/' in temp_link_lower:
                if 'facebook_id' not in company_info['company_social']:
                    company_info['company_social']['facebook_id'] = []
                elif not isinstance(company_info['company_social']['facebook_id'], list):
                    company_info['company_social']['facebook_id'] = [company_info['company_social']['facebook_id']]
                company_info['company_social']['facebook_id'].append(temp_link)
                found_social = True

            elif 'linkedin.com/' in temp_link_lower:
                if 'li_id' not in company_info['company_social']:
                    company_info['company_social']['li_id'] = []
                elif not isinstance(company_info['company_social']['li_id'], list):
                    company_info['company_social']['li_id'] = [company_info['company_social']['li_id']]
                company_info['company_social']['li_id'].append(temp_link)
                found_social = True

            elif 'instagram.com/' in temp_link_lower:
                if 'instagram_id' not in company_info['company_social']:
                    company_info['company_social']['instagram_id'] = []
                elif not isinstance(company_info['company_social']['instagram_id'], list):
                    company_info['company_social']['instagram_id'] = [company_info['company_social']['instagram_id']]
                company_info['company_social']['instagram_id'].append(temp_link)
                found_social = True

            elif 'github.com/' in temp_link_lower:
                if 'github_id' not in company_info['company_social']:
                    company_info['company_social']['github_id'] = []
                elif not isinstance(company_info['company_social']['github_id'], list):
                    company_info['company_social']['github_id'] = [company_info['company_social']['github_id']]
                company_info['company_social']['github_id'].append(temp_link)
                found_social = True

            if not found_social:
                if 'others' not in company_info['company_social']:
                    company_info['company_social']['others'] = []
                company_info['company_social']['others'].append(temp_link)

        del company_info['company_social_temp']

    # Final processing of social links
    if 'company_social' in company_info:
        social_copy = company_info['company_social'].copy()

        for key, value in social_copy.items():
            if isinstance(value, list) and key != 'others':
                if value:
                    if key == 'li_id':
                        linkedin_url = value[0] if isinstance(value, list) else value
                        if 'linkedin.com/' in str(linkedin_url).lower():
                            if '/company/' in linkedin_url:
                                handle = linkedin_url.split('/company/')[1].split('/')[0].split('?')[0]
                            elif '/in/' in linkedin_url:
                                handle = linkedin_url.split('/in/')[1].split('/')[0].split('?')[0]
                            else:
                                handle = linkedin_url
                            company_info['company_social'][key] = handle
                        else:
                            company_info['company_social'][key] = value[0]
                    else:
                        company_info['company_social'][key] = value[0]
                else:
                    del company_info['company_social'][key]

    # Extract team members
    try:
        links_and_texts = []

        # Click "Show all" buttons if present
        try:
            show_all_buttons = await page.select_all("*:contains('Show all')")
            if show_all_buttons:
                for button in show_all_buttons:
                    try:
                        await button.click()
                        await asyncio.sleep(1)
                    except:
                        pass
        except:
            pass

        # Get all maker cards
        maker_cards = await page.select_all("section[data-test*='maker-card-']")

        if maker_cards:
            for card in maker_cards:
                try:
                    card_links = await page.evaluate('''(card) => {
                        const links = [];
                        const anchors = card.querySelectorAll('a[href]');
                        anchors.forEach(a => {
                            if (a.href) links.push(a.href);
                        });
                        return links;
                    }''', card)

                    links_and_texts.extend(card_links)
                except:
                    continue

        links_of_profiles = list(set(links_and_texts))
        links_of_profiles = [link for link in links_of_profiles if '@deleted' not in link and '@' in link]
        profiles_infos = []

        for profile_link in links_of_profiles:
            try:
                await page.get(profile_link)
                await asyncio.sleep(3)

                profile_info = {}

                # Extract profile details
                try:
                    profile_title_elem = await page.select("div.text-18.font-light.text-light-gray.mb-1", timeout=5)
                    profile_title = await profile_title_elem.text if profile_title_elem else ""
                except:
                    profile_title = ""

                profile_id = profile_link.split("https://www.producthunt.com/@")[1] if "@" in profile_link else ""

                try:
                    profile_name_elem = await page.select("h1.text-24.font-semibold.text-dark-gray.mb-1", timeout=5)
                    profile_name = await profile_name_elem.text if profile_name_elem else ""
                except:
                    profile_name = ""

                profile_links = {}

                # Extract profile social links
                try:
                    await asyncio.sleep(1)
                    links_section = await page.select("h2:contains('Links') ~ div", timeout=10)

                    if links_section:
                        profile_link_data = await page.evaluate('''(section) => {
                            const links = [];
                            const anchors = section.querySelectorAll('a[href]');
                            anchors.forEach(a => {
                                const span = a.querySelector('span');
                                if (span && a.href) {
                                    links.push({category: span.textContent, href: a.href});
                                }
                            });
                            return links;
                        }''', links_section)

                        for link_data in profile_link_data:
                            profile_links[link_data['category']] = link_data['href']

                except Exception as e:
                    print(f"Error extracting profile links: {e}")
                    profile_links = {}

            except Exception as e:
                print(f"Error processing profile {profile_link}: {e}")
                continue

            # Process profile links
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
                    link_id = url_lower.split('linkedin.com/company/')[1].rstrip('/').split('?')[0]
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

    # Website cleanup
    website_url = company_info.get('website', '')
    if '?ref=producthunt' in website_url:
        website_url = website_url.replace('?ref=producthunt', '')

    company_info['website'] = website_url.strip()

    # Save to Firestore
    try:
        doc_id = each_link.split("/posts/")[1].split("#")[0]
    except:
        doc_id = each_link.split("/products/")[1].split("#")[0]

    if '?' in doc_id:
        doc_id = doc_id.split("?")[0]

    if 'company_social_temp' in company_info:
        del company_info['company_social_temp']

    company_info['created'] = datetime.utcnow()
    company_info['last_updated'] = datetime.utcnow()
    company_info['parallel_number'] = randint(1, 10)
    company_info['id'] = doc_id

    doc_ref = db.collection('ph').document(doc_id)
    doc_ref.set(company_info, merge=True)

    # Process LinkedIn for company
    if 'company_social' in company_info and 'li_id' in company_info['company_social']:
        linkedin_id = company_info['company_social']['li_id']
        if '/company/' in linkedin_id:
            linkedin_id = linkedin_id.split("/company/")[1].rstrip("/").split("?")[0]
        update_or_create_company_firestore_document(linkedin_id, db, doc_id)
        create_about_task(linkedin_id)
        print("created a company: ", linkedin_id)

    # Process LinkedIn for profiles
    for li_profile in profiles_infos:
        if 'li_id' in li_profile:
            li_id = li_profile['li_id']
            # Clean up LinkedIn ID
            for param in ['?trk', '&utm', '?utm', '?locale', '/?lipi']:
                if param in li_id:
                    li_id = li_id.split(param)[0]

            if '/' in li_id:
                li_id = li_id.split("/")[0]
            li_id = li_id.rstrip("/")

            li_profile['li_id'] = li_id
            update_or_create_profile_document(li_id, db, li_profile)
            create_ppl_task(li_id)
            print("created a profile: ", li_id)


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
