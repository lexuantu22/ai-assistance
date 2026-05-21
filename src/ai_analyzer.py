"""
AI Analyzer - Analyzes user queries and generates responses using LLM
"""
import os
import json
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from typing import Optional, Literal, List, Dict, Any
import httpx
from openai import OpenAI, AzureOpenAI

from .skills import get_skills_prompt, get_skill, SKILLS


@dataclass
class QueryIntent:
    """Represents the parsed intent from user query"""
    intent_type: Literal[
        "count_issues",      # Count number of issues
        "list_issues",       # List issue details
        "statistics",        # Statistics/summary
        "visualization",     # Generate chart
        "comparison",        # Compare data
        "help",              # Help/unknown
    ]
    skill_id: Optional[str] = None  # Skill from skills registry
    issue_type: Optional[Literal["task", "bug", "story", "epic", "all"]] = None
    filters: Dict[str, Any] = field(default_factory=dict)
    time_range: Optional[Dict[str, Any]] = None
    group_by: Optional[str] = None
    output_format: Literal["text", "table", "chart"] = "text"
    chart_type: Optional[Literal["bar", "pie", "line"]] = None
    limit: int = 0
    sort_order: str = "desc"  # "desc" or "asc"
    use_previous_results: bool = False  # Use cached results from previous query


class AIAnalyzer:
    """Analyzes user queries and generates responses using LLM"""
    
    SYSTEM_PROMPT = None  # Built dynamically with skills

    @classmethod
    def _build_system_prompt(cls) -> str:
        """Build system prompt with skills registry injected"""
        skills_text = get_skills_prompt()
        return f"""Bạn là một AI assistant chuyên phân tích dữ liệu JIRA.
Nhiệm vụ: Phân tích câu hỏi và trả về JSON duy nhất, KHÔNG giải thích.

{skills_text}

Quy tắc:
- skill_id: PHẢI chọn 1 skill_id từ danh sách trên phù hợp nhất với câu hỏi
- intent_type: count_issues, list_issues, statistics, visualization, help
- issue_type: task, bug, story, epic, all
- filters: status, priority, assignee, sprint, labels, overdue, due_this_week
- output_format: text, table, chart
- chart_type: bar, pie, line (nếu là visualization)
- group_by: sprint, status, priority, assignee, component, label, defect_type (nếu cần group)
- limit: số lượng kết quả tối đa (mặc định 0 = hiển thị hết)
  + Nếu hỏi "nhiều nhất", "cao nhất", "top 1" -> limit: 1
  + Nếu hỏi "ít nhất", "thấp nhất" -> limit: 1, sort_order: "asc"
  + Nếu hỏi "top 3" -> limit: 3
  + Nếu hỏi "top 5" -> limit: 5
  + Nếu hỏi "thống kê", "liệt kê tất cả" -> limit: 0 (hiển thị hết)
- sort_order: "desc" (mặc định) hoặc "asc" (cho "ít nhất", "thấp nhất")
- use_previous_results: true/false
  + Nếu câu hỏi tham chiếu kết quả trước ("đã liệt kê", "kết quả trên", "trong số đó") -> true
  + Nếu là câu hỏi mới hoàn toàn -> false

Quan trọng:
- Câu xã giao ("ok", "cảm ơn", "thanks", "đúng rồi") -> skill_id: null, intent_type: "help"
- "tổng quan dự án", "project overview" -> skill_id: "project_summary"
- "phân tích workload", "ai có nhiều task nhất" -> skill_id: "workload_analysis"
- "báo cáo sprint", "sprint report" -> skill_id: "sprint_report"
- "phân tích defect", "bug theo component" -> skill_id: "defect_analysis"
- "thời gian xử lý", "resolution time" -> skill_id: "resolution_time"
- "xu hướng", "trend" -> skill_id: "chart_trend"
- "bị trễ", "overdue" -> skill_id: "overdue_analysis"

Status mapping:
- "chưa closed", "not closed", "chưa đóng" -> status: "not_closed"
- "open", "mở" -> status: "open"
- "closed", "đã đóng", "done" -> status: "closed"
- "in progress", "đang làm" -> status: "in progress"

CHỈ trả về JSON:
{{
    "skill_id": "...",
    "intent_type": "...",
    "issue_type": "...",
    "filters": {{...}},
    "output_format": "...",
    "chart_type": "...",
    "group_by": "...",
    "limit": 0,
    "sort_order": "desc",
    "use_previous_results": false
}}"""

    RESPONSE_PROMPT = """Dựa trên dữ liệu JIRA sau, hãy tạo response phù hợp cho câu hỏi của người dùng.

Câu hỏi: {question}

Dữ liệu:
{data}

Yêu cầu:
- Trả lời ngắn gọn, rõ ràng
- Sử dụng markdown formatting nếu cần
- Nếu output_format là "table", trả về data dưới dạng JSON array trong field "table_data"
- Nếu output_format là "chart", trả về chart config trong field "chart_config"

Trả về JSON với format:
{
    "content": "Nội dung text response",
    "output_type": "text|table|chart",
    "table_data": [...] hoặc null,
    "chart_config": {...} hoặc null
}"""

    def __init__(self, config: dict):
        """
        Initialize AI Analyzer
        
        Config needs:
        - ai.provider: "openai" or "azure"
        - ai.api_key: API key
        - ai.model: Model name (default "gpt-4")
        """
        self._config = config
        ai_config = config.get('ai', {})
        self.provider = ai_config.get('provider', 'openai')
        self.model = ai_config.get('model', 'gpt-4')
        self.temperature = ai_config.get('temperature', 0.3)
        self.max_tokens = ai_config.get('max_tokens', 2000)
        
        # Use httpx client with SSL verification disabled (for corporate proxies)
        self._http_client = httpx.Client(verify=False)

        if self.provider == 'github':
            # GitHub Models API
            github_config = config.get('github', {})
            self.client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=os.getenv('GITHUB_TOKEN', github_config.get('token', '')),
                http_client=self._http_client
            )
            self.model = github_config.get('model', 'gpt-4o')
        elif self.provider == 'azure':
            azure_config = config.get('azure', {})
            self.client = AzureOpenAI(
                azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT', azure_config.get('endpoint', '')),
                api_key=os.getenv('AZURE_OPENAI_KEY', azure_config.get('api_key', '')),
                api_version=azure_config.get('api_version', '2024-02-15-preview'),
                http_client=self._http_client
            )
            self.model = azure_config.get('deployment_name', 'gpt-4')
        else:
            self.client = OpenAI(
                api_key=os.getenv('OPENAI_API_KEY', ai_config.get('api_key', '')),
                http_client=self._http_client
            )
    
    def update_token(self, token: str):
        """Update the API token at runtime (e.g. from UI login)"""
        if not token:
            return
        if self.provider == 'github':
            self.client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=token,
                http_client=self._http_client
            )
        elif self.provider == 'azure':
            azure_config = self._config.get('azure', {})
            self.client = AzureOpenAI(
                azure_endpoint=azure_config.get('endpoint', os.getenv('AZURE_OPENAI_ENDPOINT', '')),
                api_key=token,
                api_version=azure_config.get('api_version', '2024-02-15-preview'),
                http_client=self._http_client
            )
        else:  # openai
            self.client = OpenAI(api_key=token, http_client=self._http_client)

    def switch_provider(self, provider: str, token: str = '', model: str = ''):
        """Switch LLM provider at runtime"""
        if provider not in ('github', 'openai', 'azure'):
            return
        self.provider = provider
        if model:
            self.model = model
        elif provider == 'github':
            self.model = self._config.get('github', {}).get('model', 'gpt-4o')
        elif provider == 'azure':
            self.model = self._config.get('azure', {}).get('deployment_name', 'gpt-4')
        else:
            self.model = self._config.get('ai', {}).get('model', 'gpt-4o')
        if token:
            self.update_token(token)

    def set_model(self, model: str):
        """Override the current model for subsequent requests"""
        if model and isinstance(model, str):
            self.model = model

    CONVERSATIONAL_PROMPT = """Bạn là một AI assistant thân thiện, chuyên hỗ trợ phân tích dữ liệu JIRA.
Khi người dùng hỏi câu không liên quan đến JIRA (chào hỏi, hỏi thăm, cảm ơn, tán gẫu...), hãy trả lời tự nhiên và thân thiện đúng ngữ cảnh câu hỏi.
Sau đó có thể nhắc nhẹ rằng bạn có thể giúp họ với dữ liệu JIRA nếu cần.
Trả lời ngắn gọn, đúng ngữ cảnh. Dùng tiếng Việt."""

    def generate_conversational_response(self, message: str, conversation_history: list = None) -> str:
        """Generate a natural conversational response for non-JIRA questions"""
        return self._call_llm_with_history(
            self.CONVERSATIONAL_PROMPT, 
            message, 
            conversation_history
        )

    def _call_llm(self, system_prompt: str, user_prompt: str, json_mode: bool = False) -> str:
        """Make a call to the LLM"""
        try:
            params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            
            # Add JSON response format if requested
            if json_mode:
                params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            raise AIAnalyzerError(f"LLM call failed: {type(e).__name__}: {str(e)}")
    
    def _call_llm_with_history(self, system_prompt: str, user_prompt: str, 
                                conversation_history: List[Dict] = None, 
                                json_mode: bool = False) -> str:
        """Make a call to the LLM with conversation history for context"""
        try:
            messages = [{"role": "system", "content": system_prompt}]
            
            # Add conversation history (last 10 messages)
            if conversation_history:
                history = conversation_history[-10:]  # Limit to 10 messages
                for msg in history:
                    messages.append({
                        "role": msg.get('role', 'user'),
                        "content": msg.get('content', '')
                    })
            
            # Add current user prompt
            messages.append({"role": "user", "content": user_prompt})
            
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens
            }
            
            # Add JSON response format if requested
            if json_mode:
                params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**params)
            return response.choices[0].message.content
        except Exception as e:
            raise AIAnalyzerError(f"LLM call failed: {str(e)}")
    
    def _parse_json_response(self, response: str) -> dict:
        """Parse JSON from LLM response, handling markdown code blocks"""
        if not response:
            raise AIAnalyzerError("Empty response from LLM")
            
        # Remove markdown code blocks if present
        response = response.strip()
        if response.startswith('```'):
            lines = response.split('\n')
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith('```')]
            response = '\n'.join(lines).strip()
        
        # Try to parse directly
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON object from the response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Last resort: try to fix common JSON issues
        try:
            # Remove trailing commas before closing braces
            fixed = re.sub(r',\s*}', '}', response)
            fixed = re.sub(r',\s*]', ']', fixed)
            return json.loads(fixed)
        except json.JSONDecodeError:
            raise AIAnalyzerError(f"Failed to parse LLM response as JSON: {response[:200]}")
    
    def analyze_query(self, user_message: str, context: dict = None) -> QueryIntent:
        """
        Analyze user query and return QueryIntent
        
        Context contains: conversation_history, current_sprint, last_results, last_response_data
        """
        context = context or {}
        
        # Build context information
        context_info = ""
        if context.get('current_sprint'):
            context_info += f"\nSprint hiện tại: {context['current_sprint']}"
        if context.get('last_query_type'):
            context_info += f"\nQuery trước: {context['last_query_type']}"
        if context.get('last_filters'):
            context_info += f"\nFilters trước: {json.dumps(context['last_filters'], ensure_ascii=False)}"
        
        # Add last response data summary for follow-up questions
        if context.get('last_response_data'):
            last_data = context['last_response_data']
            context_info += f"\nKết quả trước: {last_data.get('summary', '')}"
            if last_data.get('issue_count'):
                context_info += f" ({last_data['issue_count']} issues)"
        
        # Check if this is a follow-up question
        follow_up_keywords = ['trong đó', 'trong số đó', 'lọc tiếp', 'thêm điều kiện', 
                              'chi tiết hơn', 'cụ thể hơn', 'những cái', 'các issue đó',
                              'kết quả trên', 'từ kết quả', 'dựa trên']
        is_follow_up = any(kw in user_message.lower() for kw in follow_up_keywords)
        
        follow_up_note = ""
        if is_follow_up and context.get('last_filters'):
            follow_up_note = "\n\n**ĐÂY LÀ CÂU HỎI FOLLOW-UP**: Kế thừa filters từ query trước và thêm điều kiện mới."
        
        user_prompt = f"""Phân tích câu hỏi sau và trích xuất intent:

Câu hỏi: {user_message}
{context_info}{follow_up_note}

Chú ý:
- "sprint hiện tại" hoặc "sprint này" = sprint đang active
- "bị trễ" hoặc "overdue" = due_date < today và status không phải Done
- "đến hạn trong tuần" = due_date trong 7 ngày tới
- Nếu hỏi "liệt kê" hoặc "cho xem" -> list_issues
- Nếu hỏi "bao nhiêu" hoặc "số lượng" -> count_issues
- Nếu hỏi "vẽ biểu đồ" hoặc "chart" -> visualization
- Nếu cần group data (ví dụ: "theo sprint", "theo status") -> thêm group_by
- Nếu hỏi "thống kê" -> statistics với group_by tương ứng
- Nếu là follow-up question, kế thừa filters từ query trước
- PHẢI chọn skill_id từ danh sách skills có sẵn

Trả về CHỈ JSON, không giải thích gì thêm."""

        # Build system prompt dynamically with skills
        if self.__class__.SYSTEM_PROMPT is None:
            self.__class__.SYSTEM_PROMPT = self._build_system_prompt()

        # Use conversation history for better context understanding
        conversation_history = context.get('conversation_history', [])
        response = self._call_llm_with_history(self.SYSTEM_PROMPT, user_prompt, 
                                                conversation_history, json_mode=True)
        result = self._parse_json_response(response)
        
        # Apply skill hints if skill_id is present
        skill_id = result.get('skill_id')
        skill_def = get_skill(skill_id) if skill_id else None
        
        intent_type = result.get('intent_type', 'help')
        group_by = result.get('group_by')
        filters = result.get('filters', {})
        output_format = result.get('output_format', 'text')
        chart_type = result.get('chart_type')
        
        # Use skill definition to fill in defaults the LLM may have missed
        if skill_def:
            if not intent_type or intent_type == 'help':
                intent_type = skill_def.get('intent_type', intent_type)
            if not group_by and skill_def.get('group_by_hint'):
                group_by = skill_def['group_by_hint']
            if not output_format or output_format == 'text':
                output_format = skill_def.get('output_format', output_format)
            if not chart_type and skill_def.get('chart_type_hint'):
                chart_type = skill_def['chart_type_hint']
            # Merge filter hints (don't override explicit user filters)
            if skill_def.get('filters_hint'):
                for k, v in skill_def['filters_hint'].items():
                    if k not in filters:
                        filters[k] = v
        
        return QueryIntent(
            intent_type=intent_type,
            skill_id=skill_id,
            issue_type=result.get('issue_type'),
            filters=filters,
            time_range=result.get('time_range'),
            group_by=group_by,
            output_format=output_format,
            chart_type=chart_type,
            limit=result.get('limit', 0),
            sort_order=result.get('sort_order', 'desc'),
            use_previous_results=result.get('use_previous_results', False)
        )
    
    def generate_jql(self, intent: QueryIntent, project_key: str, current_sprint: str = None) -> str:
        """Generate JQL query from QueryIntent"""
        conditions = [f"project = {project_key}"]
        
        # Issue type filter
        if intent.issue_type and intent.issue_type != 'all':
            type_map = {
                'bug': 'Bug',
                'task': 'Task',
                'story': 'Story',
                'epic': 'Epic'
            }
            conditions.append(f"type = {type_map.get(intent.issue_type, intent.issue_type)}")
        
        filters = intent.filters
        
        # Status filter - map common aliases to JIRA status categories
        if filters.get('status'):
            status = filters['status']
            status_lower = status.lower() if isinstance(status, str) else status
            
            # Map common status aliases
            # Define completed statuses constant
            COMPLETED_STATUSES = '"Closed", "Done", "Cancelled", "Release", "Released"'
            status_category_map = {
                'open': 'statusCategory != Done',
                'not_closed': f'status NOT IN ({COMPLETED_STATUSES})',
                'not closed': f'status NOT IN ({COMPLETED_STATUSES})',
                'chưa closed': f'status NOT IN ({COMPLETED_STATUSES})',
                'chưa đóng': f'status NOT IN ({COMPLETED_STATUSES})',
                'closed': f'status IN ({COMPLETED_STATUSES})',
                'done': 'statusCategory = Done',
                'in progress': 'status = "In Progress"',
                'đang làm': 'status = "In Progress"',
                'to do': 'status = "To Do"',
                'todo': 'status = "To Do"',
                'resolved': 'status = "Resolved"',
            }
            
            if isinstance(status_lower, str) and status_lower in status_category_map:
                conditions.append(status_category_map[status_lower])
            elif isinstance(status, list):
                status_str = ', '.join([f'"{s}"' for s in status])
                conditions.append(f"status IN ({status_str})")
            else:
                conditions.append(f'status = "{status}"')
        
        # Priority filter
        if filters.get('priority'):
            priority = filters['priority']
            if isinstance(priority, list):
                priority_str = ', '.join([f'"{p}"' for p in priority])
                conditions.append(f"priority IN ({priority_str})")
            else:
                conditions.append(f'priority = "{priority}"')
        
        # Assignee filter
        if filters.get('assignee'):
            conditions.append(f'assignee = "{filters["assignee"]}"')
        
        # Sprint filter
        if filters.get('sprint'):
            sprint = filters['sprint']
            if sprint in ['current', 'active', 'hiện tại', 'này']:
                conditions.append("sprint in openSprints()")
            elif sprint in ['all', 'toàn bộ', 'tất cả', 'every']:
                pass  # No sprint filter = all issues across all sprints
            else:
                conditions.append(f'sprint = "{sprint}"')
        elif filters.get('current_sprint') or (current_sprint and not filters.get('all_sprints')):
            # Default to current sprint if not specified
            pass  # Don't add sprint filter by default to allow broader queries
        
        # Define completed statuses for filtering
        COMPLETED_STATUSES = '"Closed", "Done", "Cancelled", "Release", "Released"'
        
        # Overdue filter
        if filters.get('overdue'):
            conditions.append("duedate < now()")
            conditions.append(f'status NOT IN ({COMPLETED_STATUSES})')
        
        # Due this week filter - exclude closed/done bugs
        if filters.get('due_this_week'):
            conditions.append("duedate >= startOfWeek() AND duedate <= endOfWeek()")
            # Only show active bugs (not closed/done/cancelled/released)
            if not filters.get('status'):
                conditions.append(f'status NOT IN ({COMPLETED_STATUSES})')
        
        # Due in N days filter - exclude closed/done bugs
        if filters.get('due_in_days'):
            days = filters['due_in_days']
            conditions.append(f"duedate <= {days}d")
            # Only show active bugs (not closed/done/cancelled/released)
            if not filters.get('status'):
                conditions.append(f'status NOT IN ({COMPLETED_STATUSES})')
        
        # Labels filter
        if filters.get('labels'):
            labels = filters['labels']
            if isinstance(labels, list):
                for label in labels:
                    conditions.append(f'labels = "{label}"')
            else:
                conditions.append(f'labels = "{labels}"')
        
        jql = ' AND '.join(conditions)
        
        # Add ordering
        jql += " ORDER BY created DESC"
        
        return jql
    
    def generate_response(self, intent: QueryIntent, issues: list, context: dict = None) -> dict:
        """
        Generate response from data
        
        Returns dict with:
        - content: str - Text response
        - output_type: "text" | "table" | "chart"
        - table_data: list | None
        - chart_config: dict | None
        """
        context = context or {}
        
        # Prepare data summary for LLM
        if not issues:
            return {
                "content": "Không tìm thấy kết quả phù hợp với yêu cầu của bạn.",
                "output_type": "text",
                "table_data": None,
                "chart_config": None
            }
        
        # Convert issues to dict format
        issues_data = [issue.to_dict() if hasattr(issue, 'to_dict') else issue for issue in issues]
        
        # For simple count queries, we can respond directly
        if intent.intent_type == 'count_issues' and not intent.group_by:
            count = len(issues_data)
            issue_type_text = {
                'bug': 'bug',
                'task': 'task',
                'story': 'story',
                'all': 'issue'
            }.get(intent.issue_type, 'issue')
            
            content = f"Có **{count} {issue_type_text}{'s' if count != 1 else ''}**"
            
            # Add filter context
            if intent.filters.get('status'):
                content += f" với status **{intent.filters['status']}**"
            if intent.filters.get('overdue'):
                content += " đang **bị trễ (overdue)**"
            if intent.filters.get('sprint'):
                content += f" trong **{intent.filters['sprint']}**"
            
            content += "."
            
            # Add status breakdown
            status_counts = {}
            for issue in issues_data:
                status = issue.get('status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            if len(status_counts) > 1:
                content += "\n\nPhân bố theo status:"
                for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
                    content += f"\n• {status}: {cnt}"
            
            return {
                "content": content,
                "output_type": "text",
                "table_data": None,
                "chart_config": None
            }
        
        # For count with group_by, return table
        if intent.intent_type == 'count_issues' and intent.group_by:
            group_by = intent.group_by
            
            # Group data (handle list fields like components)
            grouped = {}
            for issue in issues_data:
                if group_by in ('component', 'components'):
                    components = issue.get('components', []) or []
                    if not components:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for comp in components:
                            grouped[comp] = grouped.get(comp, 0) + 1
                elif group_by in ('label', 'labels'):
                    labels = issue.get('labels', []) or []
                    if not labels:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for label in labels:
                            grouped[label] = grouped.get(label, 0) + 1
                else:
                    key = issue.get(group_by) or 'Unknown'
                    grouped[key] = grouped.get(key, 0) + 1
            
            # Sort by count (respect sort_order)
            reverse = intent.sort_order != 'asc'
            sorted_items = sorted(grouped.items(), key=lambda x: x[1], reverse=reverse)
            
            # Apply limit for grouped results (0 = show all)
            if intent.limit > 0 and intent.limit < len(sorted_items):
                sorted_items = sorted_items[:intent.limit]
            
            # Build table data
            display_group = 'component' if group_by in ('component', 'components') else \
                           'label' if group_by in ('label', 'labels') else group_by
            table_data = []
            for key, count in sorted_items:
                table_data.append({
                    display_group: key,
                    'count': count
                })
            
            issue_type_text = intent.issue_type or 'issues'
            if intent.limit == 1:
                rank = "nhiều nhất" if reverse else "ít nhất"
                content = f"{display_group.title()} có {issue_type_text} {rank}: **{sorted_items[0][0]}** ({sorted_items[0][1]})"
            else:
                content = f"Số lượng {issue_type_text} theo {display_group} (Tổng: {len(issues_data)})"
            
            return {
                "content": content,
                "output_type": "table",
                "table_data": table_data,
                "chart_config": None
            }
        
        # For list queries, return table
        if intent.intent_type == 'list_issues':
            limit = intent.limit if intent.limit > 0 else 50
            limited_issues = issues_data[:limit]
            
            table_data = []
            for issue in limited_issues:
                # Format dates
                due_date = issue.get('due_date', '')[:10] if issue.get('due_date') else '-'
                created_date = issue.get('created_date', '')[:10] if issue.get('created_date') else '-'
                
                # Format components as comma-separated string
                components = issue.get('components', [])
                components_str = ', '.join(components) if components else '-'
                
                table_data.append({
                    'key': issue.get('key'),
                    'status': issue.get('status'),
                    'summary': issue.get('summary', '')[:60],
                    'assignee': issue.get('assignee') or 'Unassigned',
                    'reporter': issue.get('reporter') or '-',
                    'component': components_str,
                    'defect_type': issue.get('defect_type') or '-',
                    'due_date': due_date,
                    'sprint': issue.get('sprint') or '-',
                    'created_date': created_date
                })
            
            content = f"Danh sách {len(table_data)}"
            if len(issues_data) > len(table_data):
                content += f" (trong tổng số {len(issues_data)})"
            
            issue_type_text = intent.issue_type or 'issue'
            content += f" {issue_type_text}s:"
            
            return {
                "content": content,
                "output_type": "table",
                "table_data": table_data,
                "chart_config": None
            }
        
        # For visualization, generate chart config
        if intent.intent_type == 'visualization':
            group_by = intent.group_by or 'status'
            chart_type = intent.chart_type or 'bar'
            
            # Group data (handle list fields like components)
            grouped = {}
            for issue in issues_data:
                if group_by in ('component', 'components'):
                    components = issue.get('components', []) or []
                    if not components:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for comp in components:
                            grouped[comp] = grouped.get(comp, 0) + 1
                elif group_by in ('label', 'labels'):
                    labels = issue.get('labels', []) or []
                    if not labels:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for label in labels:
                            grouped[label] = grouped.get(label, 0) + 1
                else:
                    key = issue.get(group_by) or 'Unknown'
                    grouped[key] = grouped.get(key, 0) + 1
            
            # Sort by count (respect sort_order)
            reverse = intent.sort_order != 'asc'
            sorted_items = sorted(grouped.items(), key=lambda x: x[1], reverse=reverse)
            
            # Apply limit for grouped results (0 = show all)
            if intent.limit > 0 and intent.limit < len(sorted_items):
                sorted_items = sorted_items[:intent.limit]
            labels = [item[0] for item in sorted_items]
            values = [item[1] for item in sorted_items]
            
            # Generate colors
            colors = [
                '#4CAF50', '#2196F3', '#FFC107', '#F44336', '#9C27B0',
                '#00BCD4', '#FF9800', '#795548', '#607D8B', '#E91E63'
            ]
            
            chart_config = {
                "type": chart_type,
                "data": {
                    "labels": labels,
                    "datasets": [{
                        "label": f"{intent.issue_type or 'Issues'} by {group_by}",
                        "data": values,
                        "backgroundColor": colors[:len(values)]
                    }]
                },
                "options": {
                    "responsive": True,
                    "plugins": {
                        "legend": {"display": chart_type == 'pie'},
                        "title": {
                            "display": True,
                            "text": f"Distribution by {group_by.title()}"
                        }
                    }
                }
            }
            
            content = f"Biểu đồ {intent.issue_type or 'issues'} theo {group_by}:"
            
            return {
                "content": content,
                "output_type": "chart",
                "table_data": None,
                "chart_config": chart_config
            }
        
        # For statistics, generate table format
        if intent.intent_type == 'statistics':
            group_by = intent.group_by or 'sprint'
            
            # Group data (handle list fields like components)
            grouped = {}
            for issue in issues_data:
                if group_by in ('component', 'components'):
                    components = issue.get('components', []) or []
                    if not components:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for comp in components:
                            grouped[comp] = grouped.get(comp, 0) + 1
                elif group_by in ('label', 'labels'):
                    labels = issue.get('labels', []) or []
                    if not labels:
                        grouped['Unknown'] = grouped.get('Unknown', 0) + 1
                    else:
                        for label in labels:
                            grouped[label] = grouped.get(label, 0) + 1
                else:
                    key = issue.get(group_by) or 'Unknown'
                    grouped[key] = grouped.get(key, 0) + 1
            
            # Sort by count (respect sort_order)
            reverse = intent.sort_order != 'asc'
            sorted_items = sorted(grouped.items(), key=lambda x: x[1], reverse=reverse)
            
            # Apply limit for grouped results (0 = show all)
            if intent.limit > 0 and intent.limit < len(sorted_items):
                sorted_items = sorted_items[:intent.limit]
            
            # Build table data
            table_data = []
            for key, count in sorted_items:
                table_data.append({
                    group_by: key,
                    'count': count
                })
            
            issue_type_text = intent.issue_type or 'issues'
            if intent.limit == 1:
                rank = "nhiều nhất" if reverse else "ít nhất"
                content = f"Thống kê {issue_type_text} theo {group_by}: {rank} là **{sorted_items[0][0]}** ({sorted_items[0][1]})"
            else:
                content = f"Thống kê {issue_type_text} theo {group_by} (Tổng: {len(issues_data)})"
            
            return {
                "content": content,
                "output_type": "table",
                "table_data": table_data,
                "chart_config": None
            }
        
        # For other/help, return a simple response
        return {
            "content": f"Tìm thấy **{len(issues_data)}** kết quả phù hợp với yêu cầu của bạn.",
            "output_type": "text",
            "table_data": None,
            "chart_config": None
        }


class AIAnalyzerError(Exception):
    """Raised when AI analysis fails"""
    pass
