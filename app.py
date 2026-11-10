        last_name = st.text_input("Last name", key="ln")
    with col3:
        person_domain = st.text_input("Company domain", key="person_domain", placeholder="e.g. stripe.com")

    if st.button("Find email", type="primary", key="finder_btn"):
        if not (first_name and last_name and person_domain):
            st.warning("Please fill in first name, last name, and company domain.")
        elif require_api_key():
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
        elif require_api_key():
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
