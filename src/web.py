"""
Web Server - Flask application for the chat interface
"""
import os
import secrets
import time
import yaml
import urllib3
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from dotenv import load_dotenv

from .chat_agent import ChatAgent
from .github_client import GitHubClient, GitHubClientError
from .gitlab_client import GitLabClient, GitLabClientError

# Suppress SSL warnings for verify=False usage
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Detect Vercel environment (Vercel sets VERCEL=1)
_IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))
# On Vercel: verify SSL (public certs OK). Locally: skip verify (corporate proxy may intercept).
_SSL_VERIFY = _IS_VERCEL  # True on Vercel, False locally

# Load environment variables
load_dotenv()

# Load configuration
def load_config():
    # Try multiple paths to support both local and serverless environments
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml'),
        os.path.join(os.getcwd(), 'config', 'settings.yaml'),
    ]
    for config_path in candidates:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
    return {}

# Initialize Flask app
app = Flask(__name__, static_folder='../static')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True)

# Load config once
config = load_config()

# Per-session agent store: {session_id: {"agent": ChatAgent, "last_access": timestamp}}
_user_agents = {}
_AGENT_TTL = 3600 * 4  # 4 hours


def _get_agent() -> ChatAgent:
    """Get or create a per-session ChatAgent (isolates JIRA creds, AI state, chat history)."""
    sid = session.get('sid')
    if not sid:
        sid = secrets.token_hex(16)
        session['sid'] = sid

    now = time.time()

    # Cleanup expired sessions (lazy, every request)
    expired = [k for k, v in _user_agents.items() if now - v["last_access"] > _AGENT_TTL]
    for k in expired:
        del _user_agents[k]

    if sid not in _user_agents:
        _user_agents[sid] = {"agent": ChatAgent(config), "last_access": now}
    else:
        _user_agents[sid]["last_access"] = now

    return _user_agents[sid]["agent"]


def _get_github_client() -> GitHubClient:
    """Create a per-request GitHubClient using token from Authorization header."""
    token = ""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    elif auth.startswith("token "):
        token = auth[6:]
    api_url = request.headers.get("X-GitHub-API-URL", "").strip() or "https://api.github.com"
    return GitHubClient(token=token, api_url=api_url, verify_ssl=_SSL_VERIFY)


def _get_gitlab_client() -> GitLabClient:
    """Create a per-request GitLabClient using token from Authorization header."""
    token = ""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    elif auth.startswith("token "):
        token = auth[6:]
    base_url = request.headers.get("X-GitLab-URL", "").strip() or "https://gitlab.com"
    return GitLabClient(token=token, base_url=base_url, verify_ssl=_SSL_VERIFY)


def _get_git_client(platform: str = None):
    """Get the appropriate git client based on platform parameter."""
    if platform is None:
        platform = request.args.get("platform", "").strip() or request.headers.get("X-Git-Platform", "github")
    if platform == "gitlab":
        return _get_gitlab_client(), "gitlab"
    return _get_github_client(), "github"


@app.route('/')
def index():
    """Serve the main chat interface"""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files (skip API routes)"""
    if filename.startswith('api/'):
        return jsonify({'error': 'Not found'}), 404
    return send_from_directory(app.static_folder, filename)


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    Chat endpoint
    
    Request body:
    {
        "message": "user's question",
        "session_id": "optional session id",
        "model": "optional model name override"
    }
    
    Response:
    {
        "session_id": "...",
        "response": {
            "content": "...",
            "output_type": "text|table|chart",
            "table_data": [...] or null,
            "chart_config": {...} or null
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        message = data.get('message', '').strip()
        session_id = data.get('session_id')
        model = data.get('model')
        output_mode = data.get('output_mode')  # auto, chart, report
        ai_api_key = (data.get('ai_api_key') or '').strip()
        
        agent = _get_agent()
        import sys
        print(f"[CHAT] message={message[:50]!r}, ai_api_key={'YES' if ai_api_key else 'EMPTY'}, provider={agent.ai_analyzer.provider}", file=sys.stderr, flush=True)
        
        if not message:
            return jsonify({'error': 'Message is required'}), 400
        
        if len(message) > 1000:
            return jsonify({'error': 'Message too long (max 1000 characters)'}), 400
        
        # Update AI token from UI if provided
        if ai_api_key:
            agent.ai_analyzer.update_token(ai_api_key)
        else:
            print("[CHAT] WARNING: No AI token in request body!", file=sys.stderr, flush=True)
        
        result = agent.chat(message, session_id, model=model, output_mode=output_mode)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Failed to process request: {str(e)}'}), 500


@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """List all chat sessions"""
    return jsonify({'sessions': _get_agent().list_sessions()})


@app.route('/api/provider', methods=['POST'])
def switch_provider():
    """Switch AI provider at runtime"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        provider = (data.get('provider') or '').strip().lower()
        token = (data.get('token') or '').strip()
        model = (data.get('model') or '').strip()
        
        if provider not in ('github', 'openai', 'azure'):
            return jsonify({'error': 'Provider must be github, openai, or azure'}), 400
        
        agent = _get_agent()
        agent.ai_analyzer.switch_provider(provider, token, model)
        
        return jsonify({
            'success': True,
            'provider': agent.ai_analyzer.provider,
            'model': agent.ai_analyzer.model
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/ai/verify', methods=['POST'])
def ai_verify():
    """Verify an AI API key by testing connection. For GitHub provider, also validates as GitHub token."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        provider = (data.get('provider') or '').strip().lower()
        token = (data.get('token') or '').strip()
        
        if not token:
            return jsonify({'error': 'API Key là bắt buộc'}), 400
        if provider not in ('github', 'openai', 'azure'):
            return jsonify({'error': 'Provider không hợp lệ'}), 400
        
        if provider == 'github':
            # Validate as GitHub token
            client = GitHubClient(token=token, verify_ssl=_SSL_VERIFY, api_url='https://api.github.com')
            if not client.test_connection():
                return jsonify({'error': 'Token không hợp lệ'}), 401
            user = client.get_user_info()
            # Also update the AI analyzer
            _get_agent().ai_analyzer.switch_provider('github', token)
            return jsonify({
                'success': True,
                'provider': 'github',
                'username': user.get('login', ''),
                'avatar_url': user.get('avatar_url', ''),
            })
        else:
            # For OpenAI/Azure, try a lightweight API call to verify the key
            agent = _get_agent()
            agent.ai_analyzer.switch_provider(provider, token)
            try:
                agent.ai_analyzer.client.models.list()
            except Exception as e:
                # Any error means the key is invalid for this provider
                return jsonify({'error': 'API Key không hợp lệ cho provider này'}), 401
            return jsonify({
                'success': True,
                'provider': provider,
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/models', methods=['GET'])
def list_models():
    """List available AI models"""
    agent = _get_agent()
    provider = agent.ai_analyzer.provider
    current_model = agent.ai_analyzer.model
    
    if provider == 'github':
        models = [
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'description': 'Nhanh và thông minh'},
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'description': 'Nhanh, tiết kiệm'},
            {'id': 'gpt-4.1', 'name': 'GPT-4.1', 'description': 'Mới nhất, mạnh nhất'},
            {'id': 'gpt-4.1-mini', 'name': 'GPT-4.1 Mini', 'description': 'Nhẹ, nhanh'},
            {'id': 'gpt-4.1-nano', 'name': 'GPT-4.1 Nano', 'description': 'Siêu nhẹ'},
            {'id': 'o4-mini', 'name': 'o4 Mini', 'description': 'Suy luận nhanh'},
            {'id': 'o3-mini', 'name': 'o3 Mini', 'description': 'Suy luận tốt'},
            {'id': 'claude-3.5-sonnet', 'name': 'Claude 3.5 Sonnet', 'description': 'Premium - Nhanh và thông minh', 'premium': True},
            {'id': 'claude-sonnet-4', 'name': 'Claude Sonnet 4', 'description': 'Premium - Cân bằng tốc độ & chất lượng', 'premium': True},
            {'id': 'claude-opus-4', 'name': 'Claude Opus 4', 'description': 'Premium - Mạnh nhất của Anthropic', 'premium': True},
        ]
    elif provider == 'azure':
        deployment = config.get('azure', {}).get('deployment_name', 'gpt-4')
        models = [{'id': deployment, 'name': deployment, 'description': 'Azure deployment'}]
    else:
        models = [
            {'id': 'gpt-4o', 'name': 'GPT-4o', 'description': 'Nhanh và thông minh'},
            {'id': 'gpt-4o-mini', 'name': 'GPT-4o Mini', 'description': 'Nhanh, tiết kiệm'},
            {'id': 'gpt-4-turbo', 'name': 'GPT-4 Turbo', 'description': 'Mạnh mẽ'},
            {'id': 'gpt-3.5-turbo', 'name': 'GPT-3.5 Turbo', 'description': 'Nhanh nhất'},
        ]
    
    return jsonify({'models': models, 'current': current_model})


@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """Get chat history for a session"""
    history = _get_agent().get_session_history(session_id)
    
    if history is None:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify(history)


@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """Delete a session"""
    if _get_agent().clear_session(session_id):
        return '', 204
    return jsonify({'error': 'Session not found'}), 404


@app.route('/api/suggestions', methods=['GET'])
def get_suggestions():
    """Get suggested queries"""
    return jsonify({'suggestions': _get_agent().get_suggestions()})


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    # Test JIRA connection
    jira_ok = False
    try:
        jira_ok = _get_agent().jira_client.test_connection()
    except:
        pass
    
    return jsonify({
        'status': 'healthy',
        'jira_connected': jira_ok
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get public configuration for frontend"""
    agent = _get_agent()
    return jsonify({
        'jira_url': agent.jira_client.base_url,
        'project_key': agent.jira_client.project_key,
        'logged_in': bool(agent.jira_client.username and agent.jira_client.base_url),
        'username': agent.jira_client.username or None,
        'ai_provider': agent.ai_analyzer.provider
    })


@app.route('/api/login', methods=['POST'])
def login():
    """Login to JIRA with username/password"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        url = (data.get('url') or '').strip().rstrip('/')
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()
        project_key = (data.get('project_key') or '').strip()
        
        if not url or not username or not password:
            return jsonify({'error': 'URL, username và password là bắt buộc'}), 400
        
        # Update credentials
        agent = _get_agent()
        agent.jira_client.update_credentials(url, username, password)
        
        # Test connection
        if not agent.jira_client.test_connection():
            # Revert on failure
            agent.jira_client.update_credentials('', '', '')
            return jsonify({'error': 'Không thể kết nối JIRA. Kiểm tra lại thông tin đăng nhập.'}), 401
        
        # Update project key if provided
        if project_key:
            agent.jira_client.set_project_key(project_key)
            agent.project_key = project_key
        
        return jsonify({
            'success': True,
            'username': username,
            'jira_url': url,
            'project_key': agent.jira_client.project_key
        })
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout from JIRA"""
    _get_agent().jira_client.update_credentials('', '', '')
    return jsonify({'success': True})


@app.route('/api/projects', methods=['GET'])
def list_projects():
    """List JIRA projects accessible by logged-in user"""
    try:
        projects = _get_agent().jira_client.get_projects()
        return jsonify({'projects': projects})
    except Exception as e:
        return jsonify({'error': str(e), 'projects': []}), 500


@app.route('/api/project', methods=['POST'])
def set_project():
    """Change the active JIRA project key"""
    try:
        data = request.get_json()
        project_key = (data.get('project_key') or '').strip().upper()
        
        if not project_key:
            return jsonify({'error': 'Project key là bắt buộc'}), 400
        
        agent = _get_agent()
        agent.jira_client.set_project_key(project_key)
        agent.project_key = project_key
        
        return jsonify({
            'success': True,
            'project_key': project_key
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===== GitHub LOC Report Endpoints =====

@app.route('/api/github/connect', methods=['POST'])
def github_connect():
    """Validate a GitHub/GitLab token and return user info (token is NOT stored server-side)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        token = (data.get('token') or '').strip()
        platform = (data.get('platform') or 'github').strip()

        if not token:
            return jsonify({'error': 'Token là bắt buộc'}), 400

        if platform == 'gitlab':
            base_url = (data.get('base_url') or '').strip() or 'https://gitlab.com'
            client = GitLabClient(token=token, base_url=base_url, verify_ssl=_SSL_VERIFY)
            if not client.test_connection():
                return jsonify({'error': f'Token không hợp lệ hoặc không kết nối được tới {base_url}. Kiểm tra lại.'}), 401
            user = client.get_user_info()
            return jsonify({
                'success': True,
                'platform': 'gitlab',
                'username': user.get('login', ''),
                'name': user.get('name', ''),
                'avatar_url': user.get('avatar_url', ''),
                'base_url': base_url,
            })
        else:
            api_url = (data.get('api_url') or '').strip() or 'https://api.github.com'
            org = (data.get('org') or '').strip()
            repo = (data.get('repo') or '').strip()
            client = GitHubClient(token=token, api_url=api_url, verify_ssl=_SSL_VERIFY)
            if not client.test_connection():
                return jsonify({'error': 'Token không hợp lệ hoặc không kết nối được tới GitHub API. Kiểm tra lại.'}), 401
            user = client.get_user_info()
            return jsonify({
                'success': True,
                'platform': 'github',
                'username': user.get('login', ''),
                'name': user.get('name', ''),
                'avatar_url': user.get('avatar_url', ''),
                'api_url': api_url,
                'org': org,
                'repo': repo,
            })
    except Exception as e:
        import traceback, sys
        traceback.print_exc(file=sys.stderr)
        return jsonify({'error': str(e)}), 500


@app.route('/api/github/status', methods=['GET'])
def github_status():
    """Check GitHub/GitLab connection status using token from Authorization header."""
    client, platform = _get_git_client()
    connected = client.test_connection()
    result = {'connected': connected, 'platform': platform}
    if connected:
        try:
            user = client.get_user_info()
            result['username'] = user.get('login', '')
            result['name'] = user.get('name', '')
            result['avatar_url'] = user.get('avatar_url', '')
        except Exception:
            pass
    return jsonify(result)


@app.route('/api/github/repos', methods=['GET'])
def github_repos():
    """List repos for an owner (org or user)"""
    client, platform = _get_git_client()
    owner = request.args.get('owner', '').strip()
    try:
        if owner:
            repos = client.search_repos(owner)
        else:
            repos = client.list_repos()
        return jsonify({'repos': repos, 'platform': platform})
    except (GitHubClientError, GitLabClientError) as e:
        return jsonify({'error': str(e), 'repos': []}), 500


@app.route('/api/github/branches', methods=['GET'])
def github_branches():
    """List branches for a repository"""
    client, platform = _get_git_client()
    owner = request.args.get('owner', '').strip()
    repo = request.args.get('repo', '').strip()
    if not owner or not repo:
        return jsonify({'error': 'owner and repo are required'}), 400
    try:
        branches = client.get_branches(owner, repo)
        return jsonify({'branches': branches, 'platform': platform})
    except (GitHubClientError, GitLabClientError) as e:
        return jsonify({'error': str(e), 'branches': []}), 500


@app.route('/api/github/loc-report', methods=['POST'])
def github_loc_report():
    """Generate LOC report per member (supports GitHub and GitLab)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        owner = (data.get('owner') or '').strip()
        repo = (data.get('repo') or '').strip()
        since = (data.get('since') or '').strip() or None
        until = (data.get('until') or '').strip() or None
        branch = (data.get('branch') or '').strip() or None
        mode = (data.get('mode') or 'fast').strip()
        split_test = bool(data.get('split_test', False))
        platform = (data.get('platform') or '').strip()

        if not owner or not repo:
            return jsonify({'error': 'owner và repo là bắt buộc'}), 400

        client, platform = _get_git_client(platform or None)

        if platform == 'gitlab':
            report = client.get_loc_report_fast(owner, repo, since=since, until=until, branch=branch, split_test=split_test)
        else:
            if mode == 'detailed':
                report = client.get_loc_report(owner, repo, since=since, until=until, branch=branch)
            else:
                report = client.get_loc_report_fast(owner, repo, since=since, until=until, branch=branch, split_test=split_test)

        report['platform'] = platform
        return jsonify(report)

    except (GitHubClientError, GitLabClientError) as e:
        return jsonify({'error': str(e)}), 500
    except ValueError as e:
        return jsonify({'error': f'Invalid date format: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


@app.route('/api/github/member-commits', methods=['POST'])
def github_member_commits():
    """Get commit list for a specific member (supports GitHub and GitLab)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        owner = (data.get('owner') or '').strip()
        repo = (data.get('repo') or '').strip()
        author = (data.get('author') or '').strip()
        since = (data.get('since') or '').strip() or None
        until = (data.get('until') or '').strip() or None
        branch = (data.get('branch') or '').strip() or None
        split_test = bool(data.get('split_test', False))
        platform = (data.get('platform') or '').strip()

        if not owner or not repo or not author:
            return jsonify({'error': 'owner, repo và author là bắt buộc'}), 400

        client, platform = _get_git_client(platform or None)
        commits = client.get_member_commits(
            owner, repo, author, since=since, until=until, branch=branch,
            split_test=split_test,
        )

        return jsonify({
            'author': author,
            'repo': f"{owner}/{repo}",
            'since': since,
            'until': until,
            'branch': branch,
            'split_test': split_test,
            'platform': platform,
            'total': len(commits),
            'commits': commits,
        })

    except (GitHubClientError, GitLabClientError) as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': f'Failed to fetch commits: {str(e)}'}), 500


@app.route('/github-loc')
def github_loc_page():
    """Serve the GitHub LOC report page"""
    return send_from_directory(app.static_folder, 'github_loc.html')


def create_app():
    """Application factory"""
    return app


if __name__ == '__main__':
    web_config = config.get('web', {})
    app.run(
        host=web_config.get('host', '0.0.0.0'),
        port=web_config.get('port', 5000),
        debug=web_config.get('debug', False)
    )
