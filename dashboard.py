"""
PR-Optic Dashboard - Monitor GitHub PR Reviews

Run with: streamlit run dashboard.py
"""

import streamlit as st
import httpx
import asyncio
from datetime import datetime

# Page config
st.set_page_config(
    page_title="PR-Optic Dashboard",
    page_icon="🔍",
    layout="wide"
)

# API base URL
API_BASE = "http://localhost:8000"


async def fetch_repos():
    """Fetch repositories from API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_BASE}/api/repos?per_page=50")
        response.raise_for_status()
        return response.json()


async def fetch_pulls(owner: str, repo: str, state: str = "open"):
    """Fetch pull requests for a repository."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE}/api/repos/{owner}/{repo}/pulls?state={state}"
        )
        response.raise_for_status()
        return response.json()


async def fetch_pr_files(owner: str, repo: str, pr_number: int):
    """Fetch files changed in a PR."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE}/api/repos/{owner}/{repo}/pulls/{pr_number}/files"
        )
        response.raise_for_status()
        return response.json()


def main():
    st.title("🔍 PR-Optic Dashboard")
    st.markdown("**AI-Powered GitHub PR Review Agent**")
    
    # Sidebar
    st.sidebar.header("Settings")
    api_status = st.sidebar.empty()
    
    # Check API health
    try:
        response = httpx.get(f"{API_BASE}/health", timeout=2)
        if response.status_code == 200:
            api_status.success("✅ API Connected")
        else:
            api_status.error("❌ API Error")
    except Exception:
        api_status.error("❌ API Offline")
        st.error("⚠️ FastAPI server is not running. Start it with: `uv run uvicorn src.main:app --reload --port 8000`")
        return
    
    # Main content
    tab1, tab2, tab3 = st.tabs(["📚 Repositories", "🔄 Pull Requests", "📊 Review Stats"])
    
    with tab1:
        st.header("Your Repositories")
        
        if st.button("🔄 Refresh Repos"):
            with st.spinner("Fetching repositories..."):
                try:
                    data = asyncio.run(fetch_repos())
                    st.session_state['repos'] = data['repos']
                    st.success(f"✅ Loaded {data['count']} repositories")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        
        if 'repos' in st.session_state:
            repos = st.session_state['repos']
            
            # Display repos in a table
            for repo in repos[:10]:  # Show first 10
                with st.expander(f"📁 {repo['full_name']}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Stars", repo.get('stargazers_count', 0))
                    with col2:
                        st.metric("Forks", repo.get('forks_count', 0))
                    with col3:
                        st.metric("Open Issues", repo.get('open_issues_count', 0))
                    
                    st.markdown(f"**Description:** {repo.get('description', 'No description')}")
                    st.markdown(f"**URL:** [{repo['html_url']}]({repo['html_url']})")
                    st.markdown(f"**Private:** {'Yes' if repo.get('private') else 'No'}")
    
    with tab2:
        st.header("Pull Requests")
        
        # Input for owner/repo
        col1, col2 = st.columns(2)
        with col1:
            owner = st.text_input("Repository Owner", value="octocat")
        with col2:
            repo = st.text_input("Repository Name", value="Hello-World")
        
        state = st.selectbox("PR State", ["open", "closed", "all"])
        
        if st.button("🔍 Fetch Pull Requests"):
            with st.spinner(f"Fetching PRs from {owner}/{repo}..."):
                try:
                    data = asyncio.run(fetch_pulls(owner, repo, state))
                    st.session_state['pulls'] = data['pulls']
                    st.session_state['current_repo'] = f"{owner}/{repo}"
                    st.success(f"✅ Found {data['count']} pull requests")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        st.error(f"❌ Repository {owner}/{repo} not found")
                    elif e.response.status_code == 401:
                        st.error("❌ Invalid GitHub token. Check your .env file")
                    else:
                        st.error(f"❌ Error: {e}")
                except Exception as e:
                    st.error(f"❌ Error: {e}")
        
        if 'pulls' in st.session_state:
            pulls = st.session_state['pulls']
            
            if not pulls:
                st.info("No pull requests found")
            else:
                for pr in pulls:
                    with st.expander(f"#{pr['number']} - {pr['title']}"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.markdown(f"**State:** {pr['state']}")
                        with col2:
                            st.markdown(f"**Author:** {pr['user']['login']}")
                        with col3:
                            created = datetime.fromisoformat(pr['created_at'].replace('Z', '+00:00'))
                            st.markdown(f"**Created:** {created.strftime('%Y-%m-%d')}")
                        
                        description = pr.get('body') or 'No description'
                        st.markdown(f"**Description:** {description[:200]}...")
                        st.markdown(f"**URL:** [{pr['html_url']}]({pr['html_url']})")
                        
                        # Button to view files
                        if st.button(f"📄 View Files", key=f"files_{pr['number']}"):
                            with st.spinner("Fetching files..."):
                                try:
                                    owner_name, repo_name = st.session_state['current_repo'].split('/')
                                    files_data = asyncio.run(fetch_pr_files(owner_name, repo_name, pr['number']))
                                    
                                    st.markdown(f"**{files_data['count']} files changed**")
                                    for file in files_data['files']:
                                        st.markdown(f"- `{file['filename']}` (+{file['additions']} -{file['deletions']})")
                                        if file['patch']:
                                            with st.expander("View Diff"):
                                                st.code(file['patch'], language="diff")
                                except Exception as e:
                                    st.error(f"Error fetching files: {e}")
    
    with tab3:
        st.header("Review Statistics")
        st.info("📊 Review stats will be available after implementing the review state store")
        
        # Placeholder metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Reviews", "0")
        with col2:
            st.metric("Approved", "0")
        with col3:
            st.metric("Changes Requested", "0")
        with col4:
            st.metric("Pending", "0")


if __name__ == "__main__":
    main()
