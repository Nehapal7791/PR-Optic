"""
PR-Optic Enhanced Dashboard - Full PR Review Management

Features:
- Trigger PR reviews from UI
- Real-time review status monitoring
- Issue tracking by category
- Review history and analytics
- Category-based filtering

Run with: streamlit run dashboard_enhanced.py
"""

import streamlit as st
import httpx
import asyncio
from datetime import datetime
import pandas as pd

# Page config
st.set_page_config(
    page_title="PR-Optic Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API base URL
API_BASE = "http://localhost:8000"

# Category colors and emojis
CATEGORY_CONFIG = {
    "security": {"emoji": "🔐", "color": "#ff4444", "label": "Security"},
    "hardcoded_values": {"emoji": "🔧", "color": "#ff9800", "label": "Hardcoded Values"},
    "reusability": {"emoji": "♻️", "color": "#2196f3", "label": "Reusability"},
    "logic_errors": {"emoji": "🐛", "color": "#e91e63", "label": "Logic Errors"},
    "maintainability": {"emoji": "🏗️", "color": "#9c27b0", "label": "Maintainability"},
    "env_config": {"emoji": "⚙️", "color": "#ff5722", "label": "Environment Config"},
    "missing_abstractions": {"emoji": "🎨", "color": "#00bcd4", "label": "Missing Abstractions"},
}

SEVERITY_CONFIG = {
    "CRITICAL": {"emoji": "🔴", "color": "#d32f2f"},
    "MAJOR": {"emoji": "🟠", "color": "#f57c00"},
    "MINOR": {"emoji": "🟡", "color": "#fbc02d"},
}


# ============================================================================
# API Functions
# ============================================================================

async def fetch_repos():
    """Fetch repositories from API."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE}/api/repos?per_page=50")
        response.raise_for_status()
        return response.json()


async def fetch_pulls(owner: str, repo: str, state: str = "open"):
    """Fetch pull requests for a repository."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE}/api/repos/{owner}/{repo}/pulls?state={state}"
        )
        response.raise_for_status()
        return response.json()


async def fetch_pr_files(owner: str, repo: str, pr_number: int):
    """Fetch files changed in a PR."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE}/api/repos/{owner}/{repo}/pulls/{pr_number}/files"
        )
        response.raise_for_status()
        return response.json()


async def trigger_review(owner: str, repo: str, pull_number: int, post_to_github: bool = False):
    """Trigger a PR review.
    
    Args:
        owner: Repository owner
        repo: Repository name
        pull_number: PR number
        post_to_github: Whether to post comments to GitHub (default: False)
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE}/api/reviews",
            params={"post_to_github": post_to_github},
            json={
                "owner": owner,
                "repo": repo,
                "pull_number": pull_number
            }
        )
        response.raise_for_status()
        return response.json()


async def fetch_pr_status(owner: str, repo: str, pull_number: int):
    """Fetch PR review status."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE}/api/reviews/{owner}/{repo}/{pull_number}/status"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


# ============================================================================
# UI Helper Functions
# ============================================================================

def render_category_badge(category: str):
    """Render a category badge with emoji and color."""
    config = CATEGORY_CONFIG.get(category, {"emoji": "📌", "color": "#757575", "label": category})
    return f"{config['emoji']} **{config['label']}**"


def render_severity_badge(severity: str):
    """Render a severity badge."""
    config = SEVERITY_CONFIG.get(severity, {"emoji": "⚪", "color": "#9e9e9e"})
    return f"{config['emoji']} {severity}"


def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, AttributeError):
        return timestamp_str


# ============================================================================
# Main Dashboard
# ============================================================================

def main():
    # Header
    st.title("🔍 PR-Optic Dashboard")
    st.markdown("**AI-Powered GitHub PR Review Agent** - Trigger reviews, monitor status, and track issues")
    
    # Sidebar
    st.sidebar.header("⚙️ Settings")
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
        st.error("⚠️ **FastAPI server is not running.**\n\nStart it with:\n```bash\nuv run uvicorn src.main:app --reload --port 8000\n```")
        return
    
    # Sidebar filters
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Filters")
    
    # Main tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 Review PR",
        "📊 PR Status",
        "📚 Repositories",
        "📈 Analytics"
    ])
    
    # ========================================================================
    # Tab 1: Review PR
    # ========================================================================
    with tab1:
        st.header("🚀 Trigger PR Review")
        st.markdown("Start an AI-powered code review for any pull request")
        
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            review_owner = st.text_input(
                "Repository Owner",
                value=st.session_state.get('last_owner', ''),
                key="review_owner",
                help="GitHub username or organization"
            )
        
        with col2:
            review_repo = st.text_input(
                "Repository Name",
                value=st.session_state.get('last_repo', ''),
                key="review_repo",
                help="Repository name"
            )
        
        with col3:
            review_pr = st.number_input(
                "PR Number",
                min_value=1,
                value=st.session_state.get('last_pr', 1),
                key="review_pr",
                help="Pull request number"
            )
        
        # Quick fetch PR info
        col_a, col_b = st.columns([1, 3])
        
        with col_a:
            if st.button("🔍 Fetch PR Info", use_container_width=True):
                if review_owner and review_repo and review_pr:
                    with st.spinner("Fetching PR details..."):
                        try:
                            data = asyncio.run(fetch_pulls(review_owner, review_repo, "all"))
                            pr_info = next((p for p in data['pulls'] if p['number'] == review_pr), None)
                            
                            if pr_info:
                                st.session_state['pr_info'] = pr_info
                                st.success("✅ PR found!")
                            else:
                                st.error(f"❌ PR #{review_pr} not found")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
        
        # Display PR info if available
        if 'pr_info' in st.session_state:
            pr_info = st.session_state['pr_info']
            
            st.markdown("---")
            st.subheader("📋 PR Information")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("State", pr_info['state'].upper())
            with col2:
                st.metric("Author", pr_info['user']['login'])
            with col3:
                created = datetime.fromisoformat(pr_info['created_at'].replace('Z', '+00:00'))
                st.metric("Created", created.strftime('%Y-%m-%d'))
            
            st.markdown(f"**Title:** {pr_info['title']}")
            
            description = pr_info.get('body') or 'No description'
            with st.expander("📝 Description"):
                st.markdown(description)
            
            st.markdown(f"[🔗 View on GitHub]({pr_info['html_url']})")
        
        st.markdown("---")
        
        # Post to GitHub option
        post_to_github = st.checkbox(
            "📤 Post comments directly to GitHub",
            value=False,
            help="When enabled, review comments will be posted as inline comments on GitHub PR (like a senior engineer review)"
        )
        
        if post_to_github:
            st.info("💡 **Professional Style:** Comments will be posted without emojis, matching a senior engineer's review style with line-specific feedback.")
        
        # Review button
        col_review, col_status = st.columns([1, 1])
        
        with col_review:
            if st.button("🚀 **Start Review**", type="primary", use_container_width=True):
                if not review_owner or not review_repo or not review_pr:
                    st.error("❌ Please fill in all fields")
                else:
                    # Save for next time
                    st.session_state['last_owner'] = review_owner
                    st.session_state['last_repo'] = review_repo
                    st.session_state['last_pr'] = review_pr
                    
                    # Trigger review
                    progress_bar = st.progress(0, text="Initializing review...")
                    status_text = st.empty()
                    
                    try:
                        status_text.info("🔄 Fetching PR files...")
                        progress_bar.progress(20, text="Fetching PR files...")
                        
                        status_text.info("🤖 Analyzing code with AI...")
                        progress_bar.progress(40, text="AI analyzing code...")
                        
                        # Trigger review
                        result = asyncio.run(trigger_review(review_owner, review_repo, review_pr, post_to_github))
                        
                        progress_bar.progress(100, text="Review complete!")
                        
                        # Display results
                        st.success("✅ **Review Complete!**")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Status", result['status'].upper())
                        with col2:
                            st.metric("Score", result['score'].replace('_', ' ').title())
                        with col3:
                            st.metric("Issues Found", result['comments'])
                        with col4:
                            st.metric("Time", f"{result['processing_time']}s")
                        
                        st.info(f"**Summary:** {result['summary']}")
                        
                        # Store result for status tab
                        st.session_state['last_review_result'] = result
                        st.session_state['current_pr_id'] = f"{review_owner}/{review_repo}/{review_pr}"
                        
                    except httpx.HTTPStatusError as e:
                        progress_bar.empty()
                        if e.response.status_code == 404:
                            status_text.error(f"❌ PR #{review_pr} not found in {review_owner}/{review_repo}")
                        else:
                            status_text.error(f"❌ HTTP Error: {e.response.status_code}")
                    except Exception as e:
                        progress_bar.empty()
                        status_text.error(f"❌ Error: {str(e)}")
        
        with col_status:
            if st.button("📊 View Status", use_container_width=True):
                st.session_state['active_tab'] = 'status'
                st.session_state['status_owner'] = review_owner
                st.session_state['status_repo'] = review_repo
                st.session_state['status_pr'] = review_pr
                st.rerun()
    
    # ========================================================================
    # Tab 2: PR Status
    # ========================================================================
    with tab2:
        st.header("📊 PR Review Status")
        st.markdown("Monitor review progress and track issues")
        
        # Input for PR to check
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        
        with col1:
            status_owner = st.text_input(
                "Owner",
                value=st.session_state.get('status_owner', st.session_state.get('last_owner', '')),
                key="status_owner_input"
            )
        
        with col2:
            status_repo = st.text_input(
                "Repo",
                value=st.session_state.get('status_repo', st.session_state.get('last_repo', '')),
                key="status_repo_input"
            )
        
        with col3:
            status_pr = st.number_input(
                "PR #",
                min_value=1,
                value=st.session_state.get('status_pr', st.session_state.get('last_pr', 1)),
                key="status_pr_input"
            )
        
        with col4:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        
        if st.button("📊 Load Status", type="primary"):
            if status_owner and status_repo and status_pr:
                with st.spinner("Loading PR status..."):
                    try:
                        status = asyncio.run(fetch_pr_status(status_owner, status_repo, status_pr))
                        
                        if status:
                            st.session_state['pr_status'] = status
                            st.success("✅ Status loaded!")
                        else:
                            st.warning("⚠️ No review found for this PR. Trigger a review first.")
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
        
        # Display status if available
        if 'pr_status' in st.session_state:
            status = st.session_state['pr_status']
            
            st.markdown("---")
            
            # Overview metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                verdict_emoji = "✅" if status['verdict'] == "approve" else "⚠️"
                st.metric("Verdict", f"{verdict_emoji} {status['verdict'].replace('_', ' ').title()}")
            
            with col2:
                st.metric("Review Round", status['round'])
            
            with col3:
                st.metric("Open Issues", len(status['open_issues']))
            
            with col4:
                st.metric("Resolved", len(status['resolved_issues']))
            
            # Summary
            st.info(f"**Summary:** {status['summary']}")
            
            # Commit info
            st.markdown(f"**Commit:** `{status['commit_sha'][:8]}...` | **Last Updated:** {format_timestamp(status['last_updated'])}")
            
            st.markdown("---")
            
            # Issues section
            if status['open_issues']:
                st.subheader(f"🔴 Open Issues ({len(status['open_issues'])})")
                
                # Category filter
                categories = list(set(issue['category'] for issue in status['open_issues']))
                selected_categories = st.multiselect(
                    "Filter by Category",
                    options=categories,
                    default=categories,
                    format_func=lambda x: render_category_badge(x)
                )
                
                # Severity filter
                severities = list(set(issue['severity'] for issue in status['open_issues']))
                selected_severities = st.multiselect(
                    "Filter by Severity",
                    options=severities,
                    default=severities,
                    format_func=lambda x: render_severity_badge(x)
                )
                
                # Filter issues
                filtered_issues = [
                    issue for issue in status['open_issues']
                    if issue['category'] in selected_categories
                    and issue['severity'] in selected_severities
                ]
                
                # Group by category
                issues_by_category = {}
                for issue in filtered_issues:
                    cat = issue['category']
                    if cat not in issues_by_category:
                        issues_by_category[cat] = []
                    issues_by_category[cat].append(issue)
                
                # Display issues by category
                for category, issues in issues_by_category.items():
                    with st.expander(f"{render_category_badge(category)} - {len(issues)} issue(s)", expanded=True):
                        for issue in issues:
                            # Issue card
                            severity_badge = render_severity_badge(issue['severity'])
                            
                            st.markdown(f"**{severity_badge}** `{issue['filename']}:{issue['line']}`")
                            st.markdown(f"**Problem:** {issue['body']}")
                            
                            if issue.get('suggested_fix'):
                                with st.expander("💡 Suggested Fix"):
                                    st.code(issue['suggested_fix'], language="python")
                            
                            st.markdown(f"*Created: {format_timestamp(issue['created_at'])}*")
                            st.markdown("---")
            else:
                st.success("🎉 **No open issues!** All issues have been resolved.")
            
            # Resolved issues
            if status['resolved_issues']:
                st.markdown("---")
                st.subheader(f"✅ Resolved Issues ({len(status['resolved_issues'])})")
                
                with st.expander("View Resolved Issues"):
                    for issue in status['resolved_issues']:
                        st.markdown(f"- ~~{issue['filename']}:{issue['line']} - {issue['body']}~~")
    
    # ========================================================================
    # Tab 3: Repositories
    # ========================================================================
    with tab3:
        st.header("📚 Your Repositories")
        
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
            
            # Search
            search = st.text_input("🔍 Search repositories", "")
            
            # Filter repos
            if search:
                filtered_repos = [r for r in repos if search.lower() in r['full_name'].lower()]
            else:
                filtered_repos = repos[:20]  # Show first 20
            
            st.markdown(f"**Showing {len(filtered_repos)} repositories**")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Display repos
            for repo in filtered_repos:
                with st.expander(f"📁 {repo['full_name']}"):
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("⭐ Stars", repo.get('stargazers_count', 0))
                    with col2:
                        st.metric("🍴 Forks", repo.get('forks_count', 0))
                    with col3:
                        st.metric("📝 Issues", repo.get('open_issues_count', 0))
                    with col4:
                        private_badge = "🔒 Private" if repo.get('private') else "🌐 Public"
                        st.markdown(f"**{private_badge}**")
                    
                    st.markdown(f"**Description:** {repo.get('description', 'No description')}")
                    st.markdown(f"[🔗 View on GitHub]({repo['html_url']})")
                    
                    # Quick action to review PRs
                    if st.button(f"View PRs", key=f"view_prs_{repo['id']}"):
                        owner, repo_name = repo['full_name'].split('/')
                        st.session_state['last_owner'] = owner
                        st.session_state['last_repo'] = repo_name
                        st.session_state['active_tab'] = 'review'
                        st.rerun()
    
    # ========================================================================
    # Tab 4: Analytics
    # ========================================================================
    with tab4:
        st.header("📈 Review Analytics")
        st.markdown("Coming soon: Review statistics, trends, and insights")
        
        # Placeholder metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Reviews", "0", help="Total number of PR reviews performed")
        
        with col2:
            st.metric("Approved", "0", help="PRs approved without issues")
        
        with col3:
            st.metric("Changes Requested", "0", help="PRs with issues found")
        
        with col4:
            st.metric("Avg Issues/PR", "0", help="Average issues found per PR")
        
        st.markdown("---")
        
        # Category breakdown
        st.subheader("📊 Issues by Category")
        st.info("Analytics will be available after implementing review history tracking")
        
        # Placeholder chart data
        category_data = pd.DataFrame({
            'Category': list(CATEGORY_CONFIG.keys()),
            'Count': [0] * len(CATEGORY_CONFIG)
        })
        
        st.bar_chart(category_data.set_index('Category'))


if __name__ == "__main__":
    main()
