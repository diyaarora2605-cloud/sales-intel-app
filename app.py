"""
Sales Intelligence & Lead Generation App
-----------------------------------------
Find verified B2B contact info (emails) using the Hunter.io free API.

Free tier limits (Hunter.io):
- 25 domain/email searches per month
- 50 email verifications per month
These reset every month automatically, no credit card needed.
"""

import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# ---------------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------------
st.set_page_config(page_title="Lead Finder", page_icon="🎯", layout="wide")

st.title("🎯 Sales Lead Finder")
st.caption("Find verified B2B contacts, build a lead list, and export it — powered by Hunter.io")

# ---------------------------------------------------------
# API KEY HANDLING
# ---------------------------------------------------------
# We try to read the key from Streamlit "secrets" first (used when deployed).
# If it's not there, we ask the user to paste it in the sidebar (used for local testing).
api_key = st.secrets.get("HUNTER_API_KEY", None) if hasattr(st, "secrets") else None

with st.sidebar:
    st.header("⚙️ Settings")
    if not api_key:
        api_key = st.text_input("Hunter.io API Key", type="password",
                                 help="Get a free key at hunter.io/api-keys")
    else:
        st.success("API key loaded from secrets ✅")

    st.markdown("---")
    st.markdown("**Free plan:** 50 credits/month\n\n"
                 "- Domain Search / Email Finder = 1 credit per email found\n"
                 "- Email Verifier = 0.5 credit per check")
    st.markdown("[Get your free API key](https://hunter.io/api-keys)")

# Stop the app early with a friendly message if there's no key yet
if not api_key:
    st.info("👈 Paste your Hunter.io API key in the sidebar to get started.")
    st.stop()

# ---------------------------------------------------------
# SESSION STATE: this is where we keep the leads the user has saved,
# for as long as their browser tab is open.
# ---------------------------------------------------------
if "leads" not in st.session_state:
    st.session_state.leads = []  # each lead is a dictionary


def add_lead(lead: dict):
    """Add a lead to our saved list, avoiding exact duplicates."""
    if lead not in st.session_state.leads:
        st.session_state.leads.append(lead)
        st.toast(f"Saved {lead.get('email', 'lead')} ✅")


# ---------------------------------------------------------
# TABS
# ---------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "🏢 Find Company Emails",
    "👤 Find a Specific Person",
    "✅ Verify an Email",
    "💾 My Saved Leads",
])

# ===========================================================
# TAB 1: DOMAIN SEARCH — find all known emails at a company
# ===========================================================
with tab1:
    st.subheader("Find every known email at a company")
    st.write("Type a **domain** (e.g. `zara.com`) or just the **brand name** (e.g. `Zara`) — if you type a name, we'll show matching companies to pick from.")

    # Set up all the session-state variables this tab needs
    if "active_domain" not in st.session_state:
        st.session_state.active_domain = None
    if "domain_results" not in st.session_state:
        st.session_state.domain_results = []
    if "domain_org" not in st.session_state:
        st.session_state.domain_org = ""
    if "domain_offset" not in st.session_state:
        st.session_state.domain_offset = 0
    if "domain_total" not in st.session_state:
        st.session_state.domain_total = 0
    if "brand_suggestions" not in st.session_state:
        st.session_state.brand_suggestions = []

    query = st.text_input("Company domain or brand name", placeholder="e.g. zara.com  OR  Zara", key="domain_input")

    if st.button("Search", type="primary", key="domain_search_btn"):
        st.session_state.active_domain = None
        st.session_state.domain_results = []
        st.session_state.domain_offset = 0
        st.session_state.domain_total = 0
        st.session_state.brand_suggestions = []

        if not query:
            st.warning("Please enter a domain or brand name first.")
        elif "." in query:
            # Looks like a domain already (e.g. zara.com) - search Hunter directly
            st.session_state.active_domain = query.strip()
        else:
            # Looks like a brand name - look up matching companies first (free, no API cost)
            with st.spinner(f"Looking up companies matching '{query}'..."):
                try:
                    suggest_resp = requests.get(
                        "https://autocomplete.clearbit.com/v1/companies/suggest",
                        params={"query": query.strip()},
                        timeout=10,
                    )
                    suggestions = suggest_resp.json() if suggest_resp.status_code == 200 else []
                except requests.exceptions.RequestException:
                    suggestions = []

            if suggestions:
                st.session_state.brand_suggestions = suggestions
            else:
                # Not every brand is in Clearbit's database - this is especially common for
                # small local/regional businesses. Offer common domain-pattern guesses instead
                # so the user can still try Hunter directly on a likely domain.
                clean = query.strip().lower().replace(" ", "")
                guessed = [
                    {"name": f"{query.strip()} (guess)", "domain": f"{clean}.com"},
                    {"name": f"{query.strip()} (guess)", "domain": f"{clean}.in"},
                    {"name": f"{query.strip()} (guess)", "domain": f"{clean}.co.in"},
                ]
                st.session_state.brand_suggestions = guessed
                st.info(
                    f"'{query}' isn't in the free company database (common for smaller or local "
                    "brands — no free tool covers every business). Here are some likely domain "
                    "guesses to try, or type the exact domain yourself if you know it. "
                    "Good news: Hunter only charges credits for emails actually found, so a wrong guess costs nothing."
                )

    # Show brand-name suggestions to pick from, if we have any pending
    if st.session_state.brand_suggestions and not st.session_state.active_domain:
        st.write("**Which company did you mean?**")
        for i, company in enumerate(st.session_state.brand_suggestions[:8]):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(f"{company.get('name', 'Unknown')} — `{company.get('domain', '')}`")
            with c2:
                if st.button("Select", key=f"pick_company_{i}"):
                    st.session_state.active_domain = company.get("domain")
                    st.session_state.brand_suggestions = []
                    st.session_state.domain_results = []
                    st.session_state.domain_offset = 0
                    st.rerun()

    # Fetch (or fetch-next-page-of) Hunter results for the active domain
    def fetch_hunter_page(domain, offset):
        url = "https://api.hunter.io/v2/domain-search"
        params = {"domain": domain.strip(), "api_key": api_key, "limit": 10, "offset": offset}
        return requests.get(url, params=params)

    if st.session_state.active_domain and not st.session_state.domain_results:
        with st.spinner(f"Searching Hunter.io for {st.session_state.active_domain}..."):
            response = fetch_hunter_page(st.session_state.active_domain, 0)

        if response.status_code == 200:
            resp_json = response.json()
            data = resp_json.get("data", {})
            st.session_state.domain_results = data.get("emails", [])
            st.session_state.domain_org = data.get("organization") or st.session_state.active_domain
            st.session_state.domain_total = resp_json.get("meta", {}).get("results", len(st.session_state.domain_results))
            st.session_state.domain_offset = len(st.session_state.domain_results)
            if not st.session_state.domain_results:
                st.warning("No contacts found for this domain on the free plan.")
        elif response.status_code == 401:
            st.error("Invalid API key. Double check what you pasted in the sidebar.")
        elif response.status_code == 429:
            st.error("You've hit your monthly free-plan search limit. It resets next month.")
        else:
            st.error(f"Something went wrong (status {response.status_code}). Try again.")

    # Display whatever results we've accumulated so far
    if st.session_state.domain_results:
        emails = st.session_state.domain_results
        org = st.session_state.domain_org
        st.success(f"Showing {len(emails)} of {st.session_state.domain_total} known contact(s) at {org}")

        for idx, person in enumerate(emails):
            full_name = f"{person.get('first_name') or ''} {person.get('last_name') or ''}".strip()
            person_email = person.get("value", "")  # Hunter calls this field "value", not "email"
            person_phone = person.get("phone_number")
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"**{full_name or 'Unknown name'}**")
                st.write(person_email or "_(no email on file)_")
                if person_phone:
                    st.caption(f"📞 {person_phone}")
            with col2:
                st.write(person.get("position") or "—")
                st.caption(f"Confidence: {person.get('confidence', '—')}%")
            with col3:
                if st.button("💾 Save", key=f"save_{idx}"):
                    add_lead({
                        "name": full_name,
                        "email": person_email,
                        "phone": person_phone,
                        "position": person.get("position"),
                        "company": org,
                        "confidence": person.get("confidence"),
                        "source": "domain search",
                        "saved_on": datetime.now().strftime("%Y-%m-%d"),
                    })
            st.divider()

        # Pagination: only show "load more" if Hunter says there are more results available
        if st.session_state.domain_offset < st.session_state.domain_total:
            remaining = st.session_state.domain_total - st.session_state.domain_offset
            st.caption(f"⚠️ Loading more contacts uses ~1 credit per contact found (up to 10 credits) from your monthly Hunter.io quota. {remaining} more available.")
            if st.button("⬇️ Load 10 more contacts"):
                with st.spinner("Loading more..."):
                    next_response = fetch_hunter_page(st.session_state.active_domain, st.session_state.domain_offset)
                if next_response.status_code == 200:
                    more_emails = next_response.json().get("data", {}).get("emails", [])
                    st.session_state.domain_results.extend(more_emails)
                    st.session_state.domain_offset += len(more_emails)
                    st.rerun()
                elif next_response.status_code == 429:
                    st.error("Monthly free-plan search limit reached.")
                else:
                    st.error("Couldn't load more right now. Try again shortly.")

# ===========================================================
# TAB 2: EMAIL FINDER — find one specific person's email
# ===========================================================
with tab2:
    st.subheader("Find one person's email address")
    st.write("If you know someone's name and where they work, this finds their likely email.")

    col1, col2, col3 = st.columns(3)
    with col1:
        first_name = st.text_input("First name", key="fn")
    with col2:
        last_name = st.text_input("Last name", key="ln")
    with col3:
        person_domain = st.text_input("Company domain", key="person_domain", placeholder="e.g. stripe.com")

    if st.button("Find email", type="primary", key="finder_btn"):
        if not (first_name and last_name and person_domain):
            st.warning("Please fill in first name, last name, and company domain.")
        else:
            with st.spinner("Searching..."):
                url = "https://api.hunter.io/v2/email-finder"
                params = {
                    "domain": person_domain.strip(),
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "api_key": api_key,
                }
                response = requests.get(url, params=params)

            if response.status_code == 200:
                data = response.json().get("data", {})
                found_email = data.get("email")
                if found_email:
                    st.success(f"Found: **{found_email}**")
                    st.caption(f"Confidence score: {data.get('score', '—')}%")
                    if st.button("💾 Save this lead"):
                        add_lead({
                            "name": f"{first_name} {last_name}",
                            "email": found_email,
                            "position": data.get("position"),
                            "company": person_domain,
                            "confidence": data.get("score"),
                            "source": "email finder",
                            "saved_on": datetime.now().strftime("%Y-%m-%d"),
                        })
                else:
                    st.warning("No email found for this person.")
            elif response.status_code == 401:
                st.error("Invalid API key.")
            elif response.status_code == 429:
                st.error("Monthly free-plan limit reached.")
            else:
                st.error(f"Something went wrong (status {response.status_code}).")

# ===========================================================
# TAB 3: EMAIL VERIFIER — check if an email is real/deliverable
# ===========================================================
with tab3:
    st.subheader("Verify if an email is real and deliverable")
    email_to_check = st.text_input("Email address", placeholder="e.g. name@company.com")

    if st.button("Verify email", type="primary", key="verify_btn"):
        if not email_to_check:
            st.warning("Please enter an email address.")
        else:
            with st.spinner("Verifying..."):
                url = "https://api.hunter.io/v2/email-verifier"
                params = {"email": email_to_check.strip(), "api_key": api_key}
                response = requests.get(url, params=params)

            if response.status_code == 200:
                data = response.json().get("data", {})
                status = data.get("status", "unknown")
                score = data.get("score", "—")

                if status == "valid":
                    st.success(f"✅ Valid email (confidence: {score}%)")
                elif status == "invalid":
                    st.error(f"❌ Invalid email (confidence: {score}%)")
                else:
                    st.warning(f"⚠️ Status: {status} (confidence: {score}%)")
            elif response.status_code == 401:
                st.error("Invalid API key.")
            elif response.status_code == 429:
                st.error("Monthly free-plan limit reached.")
            else:
                st.error(f"Something went wrong (status {response.status_code}).")

# ===========================================================
# TAB 4: SAVED LEADS — view, export, manage your lead list
# ===========================================================
with tab4:
    st.subheader("Your saved leads")

    if not st.session_state.leads:
        st.info("No leads saved yet. Find some contacts in the other tabs and hit 💾 Save.")
    else:
        df = pd.DataFrame(st.session_state.leads)
        st.dataframe(df, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download as CSV",
                data=csv,
                file_name=f"leads_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        with col2:
            if st.button("🗑️ Clear all saved leads"):
                st.session_state.leads = []
                st.rerun()

    st.markdown("---")
    st.caption(
        "⚠️ Note: leads are only kept while this browser tab is open (or until the app "
        "goes to sleep on the free hosting tier). Download your CSV to keep them permanently."
    )
