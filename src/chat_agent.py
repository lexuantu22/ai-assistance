"""
Chat Agent - Main orchestrator for the JIRA chat assistant
"""
import uuid
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .jira_client import JiraClient, JiraConnectionError
from .ai_analyzer import AIAnalyzer, AIAnalyzerError, QueryIntent
from .skills import get_skill, SKILLS


@dataclass
class ChatMessage:
    """Represents a chat message"""
    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    output_type: str = "text"  # "text", "table", "chart"
    table_data: Optional[List[Dict]] = None
    chart_config: Optional[Dict] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'output_type': self.output_type,
            'table_data': self.table_data,
            'chart_config': self.chart_config
        }


@dataclass
class ChatSession:
    """Represents a chat session with conversation history"""
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_message(self, role: str, content: str, output_type: str = "text",
                   table_data: List[Dict] = None, chart_config: Dict = None) -> ChatMessage:
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=datetime.now(),
            output_type=output_type,
            table_data=table_data,
            chart_config=chart_config
        )
        self.messages.append(message)
        return message
    
    def get_conversation_history(self, limit: int = 10) -> List[Dict]:
        """Get recent conversation history for context"""
        recent = self.messages[-limit:] if len(self.messages) > limit else self.messages
        return [{'role': m.role, 'content': m.content} for m in recent]


class ChatAgent:
    """Main orchestrator for the JIRA chat assistant"""
    
    def __init__(self, config: dict):
        """
        Initialize Chat Agent
        
        Config should contain jira and ai configuration
        """
        self.config = config
        self.jira_client = JiraClient(config)
        self.ai_analyzer = AIAnalyzer(config)
        self.sessions: Dict[str, ChatSession] = {}
        
        # Get project key from config
        self.project_key = config.get('jira', {}).get('project_key', 'PROJ')
    
    def get_or_create_session(self, session_id: str = None) -> ChatSession:
        """Get existing session or create new one"""
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        
        new_session_id = session_id or str(uuid.uuid4())
        session = ChatSession(session_id=new_session_id)
        
        # Initialize context with current sprint info
        try:
            current_sprint = self.jira_client.get_current_sprint()
            if current_sprint:
                session.context['current_sprint'] = current_sprint.get('name')
        except:
            pass
        
        self.sessions[new_session_id] = session
        return session
    
    def chat(self, message: str, session_id: str = None, model: str = None, output_mode: str = None) -> Dict[str, Any]:
        """
        Main entry point for chat interaction
        
        Args:
            message: User's message
            session_id: Optional session ID for context continuity
            model: Optional model name override
            output_mode: Optional output mode override (chart, report)
            
        Returns:
            Dict with session_id and response data
        """
        # Apply model override if provided
        if model:
            self.ai_analyzer.set_model(model)
        # Validate input
        if not message or not message.strip():
            return {
                'session_id': session_id or str(uuid.uuid4()),
                'response': {
                    'content': 'Vui lòng nhập câu hỏi của bạn.',
                    'output_type': 'text',
                    'table_data': None,
                    'chart_config': None
                }
            }
        
        # Get or create session
        session = self.get_or_create_session(session_id)
        
        # Add user message to history
        session.add_message('user', message)
        
        try:
            # Step 1: Analyze user query with conversation history (limit 10)
            context = {
                'current_sprint': session.context.get('current_sprint'),
                'last_query_type': session.context.get('last_query_type'),
                'last_filters': session.context.get('last_filters'),
                'last_response_data': session.context.get('last_response_data'),
                'conversation_history': session.get_conversation_history(limit=10)
            }
            
            intent = self.ai_analyzer.analyze_query(message, context)
            
            # Apply output_mode override
            if output_mode == 'chart':
                intent.intent_type = 'visualization'
                intent.output_format = 'chart'
                if not intent.chart_type:
                    intent.chart_type = 'bar'
                if not intent.group_by:
                    intent.group_by = 'status'
            elif output_mode == 'report':
                if intent.intent_type in ('help', 'count_issues'):
                    intent.intent_type = 'statistics'
                intent.output_format = 'table'
                if not intent.group_by and intent.intent_type == 'statistics':
                    intent.group_by = 'status'
            
            # Handle conversational/help intent without querying JIRA
            if intent.intent_type == 'help' and not intent.group_by and not intent.filters:
                conversational_reply = self.ai_analyzer.generate_conversational_response(
                    message, 
                    context.get('conversation_history', [])
                )
                response = {
                    'content': conversational_reply,
                    'output_type': 'text',
                    'table_data': None,
                    'chart_config': None
                }
                session.add_message('assistant', response['content'])
                return {
                    'session_id': session.session_id,
                    'response': response
                }
            
            # Step 2: Get data - use cached results or fetch from JIRA
            if intent.use_previous_results and session.context.get('last_table_data'):
                # Use cached table data from previous query
                cached_table = session.context['last_table_data']
                response = self._process_cached_results(intent, cached_table, message)
            else:
                # Generate JQL and fetch from JIRA
                jql = self.ai_analyzer.generate_jql(
                    intent, 
                    self.project_key,
                    session.context.get('current_sprint')
                )
                
                # Fetch issues from JIRA - use higher limit for statistics
                max_results = 500 if intent.intent_type in ['statistics', 'visualization', 'count_issues'] else 100
                issues = self.jira_client.search_issues(jql, max_results=max_results)
                
                # Step 3: Generate response — try skill-specific handler first
                response_context = {
                    'original_question': message,
                    'current_sprint': session.context.get('current_sprint')
                }
                
                skill_handler = self._get_skill_handler(intent.skill_id)
                if skill_handler:
                    response = skill_handler(intent, issues, response_context)
                else:
                    response = self.ai_analyzer.generate_response(intent, issues, response_context)
                
                # Update issue count
                session.context['last_results_count'] = len(issues)
            
            # Step 4: Update session context with last response data for follow-up questions
            session.context['last_query_type'] = intent.intent_type
            session.context['last_filters'] = intent.filters
            session.context['last_issue_type'] = intent.issue_type
            
            # Cache table data for follow-up questions on previous results
            if response.get('table_data'):
                session.context['last_table_data'] = response['table_data']
            
            # Cache response data for follow-up prompts (summary of results)
            session.context['last_response_data'] = {
                'summary': response['content'][:500] if response.get('content') else '',
                'issue_count': session.context.get('last_results_count', 0),
                'output_type': response.get('output_type', 'text'),
                'has_table': response.get('table_data') is not None,
                'has_chart': response.get('chart_config') is not None,
                'filters_used': intent.filters,
                'issue_type': intent.issue_type
            }
            
            # Add assistant message to history
            session.add_message(
                'assistant',
                response['content'],
                output_type=response.get('output_type', 'text'),
                table_data=response.get('table_data'),
                chart_config=response.get('chart_config')
            )
            
            return {
                'session_id': session.session_id,
                'response': response
            }
            
        except JiraConnectionError as e:
            error_response = {
                'content': f'❌ Không thể kết nối đến JIRA. Vui lòng kiểm tra cấu hình.\n\nLỗi: {str(e)}',
                'output_type': 'text',
                'table_data': None,
                'chart_config': None
            }
            session.add_message('assistant', error_response['content'])
            return {
                'session_id': session.session_id,
                'response': error_response
            }
            
        except AIAnalyzerError as e:
            error_response = {
                'content': f'❌ Lỗi khi xử lý câu hỏi. Vui lòng thử lại.\n\nLỗi: {str(e)}',
                'output_type': 'text',
                'table_data': None,
                'chart_config': None
            }
            session.add_message('assistant', error_response['content'])
            return {
                'session_id': session.session_id,
                'response': error_response
            }
            
        except Exception as e:
            error_response = {
                'content': f'❌ Đã xảy ra lỗi không mong muốn. Vui lòng thử lại.\n\nLỗi: {str(e)}',
                'output_type': 'text',
                'table_data': None,
                'chart_config': None
            }
            session.add_message('assistant', error_response['content'])
            return {
                'session_id': session.session_id,
                'response': error_response
            }
    
    def get_session_history(self, session_id: str) -> Optional[Dict]:
        """Get chat history for a session"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return {
            'session_id': session.session_id,
            'messages': [m.to_dict() for m in session.messages],
            'created_at': session.created_at.isoformat()
        }
    
    def _process_cached_results(self, intent, cached_table: List[Dict], question: str) -> Dict:
        """Process a follow-up question using cached table data from previous results"""
        if not cached_table:
            return {
                "content": "Không có dữ liệu trước đó để tham chiếu.",
                "output_type": "text",
                "table_data": None,
                "chart_config": None
            }
        
        # Find the numeric column (count, value, etc.)
        count_key = None
        group_key = None
        for key in cached_table[0]:
            if key in ('count', 'value', 'total'):
                count_key = key
            else:
                group_key = key
        
        if not count_key or not group_key:
            # Fallback: pass to LLM
            return self.ai_analyzer.generate_response_from_data(
                question, cached_table
            )
        
        # Sort cached results
        reverse = intent.sort_order != 'asc'
        sorted_data = sorted(cached_table, key=lambda x: x.get(count_key, 0), reverse=reverse)
        
        # Apply limit
        if intent.limit > 0 and intent.limit < len(sorted_data):
            sorted_data = sorted_data[:intent.limit]
        
        # Generate response
        if intent.limit == 1 and sorted_data:
            rank = "nhiều nhất" if reverse else "ít nhất"
            item = sorted_data[0]
            content = f"{group_key.title()} có {rank}: **{item[group_key]}** ({item[count_key]})"
        else:
            content = f"Kết quả lọc từ dữ liệu trước ({len(sorted_data)} kết quả):"
        
        return {
            "content": content,
            "output_type": "table" if len(sorted_data) > 1 else "text",
            "table_data": sorted_data if len(sorted_data) > 1 else None,
            "chart_config": None
        }
    
    # ===== Skill Handlers =====
    
    def _get_skill_handler(self, skill_id: str):
        """Return the handler function for a skill, or None to use default"""
        handlers = {
            'overdue_analysis': self._handle_overdue_analysis,
            'workload_analysis': self._handle_workload_analysis,
            'resolution_time': self._handle_resolution_time,
            'created_vs_resolved': self._handle_created_vs_resolved,
            'sprint_report': self._handle_sprint_report,
            'project_summary': self._handle_project_summary,
        }
        return handlers.get(skill_id)
    
    def _handle_overdue_analysis(self, intent, issues, context) -> Dict:
        """Specialized handler for overdue issues analysis"""
        if not issues:
            return {"content": "Không có issue nào bị trễ hạn. 🎉", "output_type": "text", "table_data": None, "chart_config": None}
        
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        today = date.today()
        
        table_data = []
        for issue in issues_data:
            due_str = issue.get('due_date', '')[:10] if issue.get('due_date') else None
            if not due_str:
                continue
            try:
                due_date = datetime.strptime(due_str, '%Y-%m-%d').date()
                days_overdue = (today - due_date).days
            except ValueError:
                days_overdue = 0
            
            if days_overdue > 0:
                table_data.append({
                    'key': issue.get('key'),
                    'summary': issue.get('summary', '')[:50],
                    'status': issue.get('status'),
                    'assignee': issue.get('assignee') or 'Unassigned',
                    'due_date': due_str,
                    'days_overdue': days_overdue,
                    'priority': issue.get('priority', '-'),
                })
        
        # Sort by days_overdue descending
        table_data.sort(key=lambda x: x['days_overdue'], reverse=True)
        
        if not table_data:
            return {"content": "Không có issue nào bị trễ hạn. 🎉", "output_type": "text", "table_data": None, "chart_config": None}
        
        # Summary
        total = len(table_data)
        max_overdue = table_data[0]['days_overdue']
        avg_overdue = sum(r['days_overdue'] for r in table_data) / total
        
        content = f"⚠️ **{total} issues bị trễ hạn**\n\n"
        content += f"• Trễ nhiều nhất: **{max_overdue} ngày** ({table_data[0]['key']})\n"
        content += f"• Trung bình: **{avg_overdue:.0f} ngày**\n"
        
        # Breakdown by assignee
        by_assignee = {}
        for r in table_data:
            by_assignee[r['assignee']] = by_assignee.get(r['assignee'], 0) + 1
        if len(by_assignee) > 1:
            content += "\nTheo assignee:"
            for name, cnt in sorted(by_assignee.items(), key=lambda x: -x[1]):
                content += f"\n• {name}: {cnt}"
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def _handle_workload_analysis(self, intent, issues, context) -> Dict:
        """Specialized handler for workload analysis by assignee"""
        if not issues:
            return {"content": "Không có dữ liệu issues để phân tích workload.", "output_type": "text", "table_data": None, "chart_config": None}
        
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        
        # Group by assignee with status breakdown
        workload = {}
        for issue in issues_data:
            assignee = issue.get('assignee') or 'Unassigned'
            status = issue.get('status', 'Unknown')
            if assignee not in workload:
                workload[assignee] = {'total': 0, 'statuses': {}}
            workload[assignee]['total'] += 1
            workload[assignee]['statuses'][status] = workload[assignee]['statuses'].get(status, 0) + 1
        
        # Sort by total descending
        sorted_workload = sorted(workload.items(), key=lambda x: x[1]['total'], reverse=True)
        
        # Apply limit
        if intent.limit > 0 and intent.limit < len(sorted_workload):
            sorted_workload = sorted_workload[:intent.limit]
        
        table_data = []
        for assignee, data in sorted_workload:
            row = {'assignee': assignee, 'total': data['total']}
            for status, cnt in sorted(data['statuses'].items()):
                row[status] = cnt
            table_data.append(row)
        
        total_issues = len(issues_data)
        team_size = len(workload)
        avg = total_issues / team_size if team_size > 0 else 0
        
        content = f"📊 **Phân tích Workload** ({total_issues} issues, {team_size} người)\n\n"
        content += f"• Trung bình: **{avg:.1f} issues/người**\n"
        if sorted_workload:
            content += f"• Nhiều nhất: **{sorted_workload[0][0]}** ({sorted_workload[0][1]['total']} issues)\n"
            if len(sorted_workload) > 1:
                content += f"• Ít nhất: **{sorted_workload[-1][0]}** ({sorted_workload[-1][1]['total']} issues)"
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def _handle_resolution_time(self, intent, issues, context) -> Dict:
        """Specialized handler for resolution time analysis"""
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        
        # Filter only resolved issues with both dates
        resolved = []
        for issue in issues_data:
            created = issue.get('created_date')
            resolved_dt = issue.get('resolved_date')
            if created and resolved_dt:
                try:
                    c = datetime.fromisoformat(created)
                    r = datetime.fromisoformat(resolved_dt)
                    days = (r - c).days
                    resolved.append({
                        'key': issue.get('key'),
                        'summary': issue.get('summary', '')[:50],
                        'priority': issue.get('priority', '-'),
                        'assignee': issue.get('assignee') or 'Unassigned',
                        'created_date': created[:10],
                        'resolved_date': resolved_dt[:10],
                        'resolution_days': max(days, 0),
                    })
                except (ValueError, TypeError):
                    continue
        
        if not resolved:
            return {"content": "Không có issues đã resolved để phân tích thời gian xử lý.", "output_type": "text", "table_data": None, "chart_config": None}
        
        # Sort by resolution time
        reverse = intent.sort_order != 'asc'
        resolved.sort(key=lambda x: x['resolution_days'], reverse=reverse)
        
        if intent.limit > 0 and intent.limit < len(resolved):
            table_data = resolved[:intent.limit]
        else:
            table_data = resolved
        
        # Statistics
        all_days = [r['resolution_days'] for r in resolved]
        avg_days = sum(all_days) / len(all_days)
        min_days = min(all_days)
        max_days = max(all_days)
        
        content = f"⏱️ **Phân tích thời gian xử lý** ({len(resolved)} issues đã resolved)\n\n"
        content += f"• Trung bình: **{avg_days:.1f} ngày**\n"
        content += f"• Nhanh nhất: **{min_days} ngày**\n"
        content += f"• Lâu nhất: **{max_days} ngày**"
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def _handle_created_vs_resolved(self, intent, issues, context) -> Dict:
        """Specialized handler for created vs resolved comparison by sprint"""
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        
        group_by = intent.group_by or 'sprint'
        
        # Gather created and resolved counts per group
        created_counts = {}
        resolved_counts = {}
        
        for issue in issues_data:
            group_key = issue.get(group_by) or 'Unknown'
            created_counts[group_key] = created_counts.get(group_key, 0) + 1
            if issue.get('resolved_date'):
                resolved_counts[group_key] = resolved_counts.get(group_key, 0) + 1
        
        all_groups = sorted(set(list(created_counts.keys()) + list(resolved_counts.keys())))
        
        table_data = []
        for group in all_groups:
            created = created_counts.get(group, 0)
            resolved = resolved_counts.get(group, 0)
            rate = (resolved / created * 100) if created > 0 else 0
            table_data.append({
                group_by: group,
                'created': created,
                'resolved': resolved,
                'resolve_rate': f"{rate:.0f}%",
            })
        
        total_created = sum(created_counts.values())
        total_resolved = sum(resolved_counts.values())
        overall_rate = (total_resolved / total_created * 100) if total_created > 0 else 0
        
        content = f"📈 **Created vs Resolved** (theo {group_by})\n\n"
        content += f"• Tổng tạo mới: **{total_created}** | Đã resolve: **{total_resolved}**\n"
        content += f"• Tỷ lệ resolve: **{overall_rate:.0f}%**"
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def _handle_sprint_report(self, intent, issues, context) -> Dict:
        """Specialized handler for sprint report"""
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        
        if not issues_data:
            return {"content": "Không tìm thấy issues trong sprint.", "output_type": "text", "table_data": None, "chart_config": None}
        
        total = len(issues_data)
        sprint_name = context.get('current_sprint') or 'Current Sprint'
        
        # Count by status
        status_counts = {}
        for issue in issues_data:
            status = issue.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        done_statuses = {'Done', 'Closed', 'Resolved', 'Release', 'Released', 'Cancelled'}
        completed = sum(cnt for st, cnt in status_counts.items() if st in done_statuses)
        remaining = total - completed
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        # Count overdue
        today = date.today()
        overdue_count = 0
        for issue in issues_data:
            due_str = issue.get('due_date', '')[:10] if issue.get('due_date') else None
            status = issue.get('status', '')
            if due_str and status not in done_statuses:
                try:
                    if datetime.strptime(due_str, '%Y-%m-%d').date() < today:
                        overdue_count += 1
                except ValueError:
                    pass
        
        content = f"🏃 **Sprint Report: {sprint_name}**\n\n"
        content += f"• Tổng issues: **{total}**\n"
        content += f"• Hoàn thành: **{completed}** ({completion_rate:.0f}%)\n"
        content += f"• Còn lại: **{remaining}**\n"
        if overdue_count > 0:
            content += f"• ⚠️ Trễ hạn: **{overdue_count}**\n"
        content += "\nPhân bố theo status:"
        for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
            pct = cnt / total * 100
            content += f"\n• {status}: {cnt} ({pct:.0f}%)"
        
        # Table data for status breakdown
        table_data = []
        for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
            table_data.append({'status': status, 'count': cnt, 'percent': f"{cnt/total*100:.0f}%"})
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def _handle_project_summary(self, intent, issues, context) -> Dict:
        """Specialized handler for project overview"""
        issues_data = [i.to_dict() if hasattr(i, 'to_dict') else i for i in issues]
        
        if not issues_data:
            return {"content": "Không tìm thấy issues trong dự án.", "output_type": "text", "table_data": None, "chart_config": None}
        
        total = len(issues_data)
        today = date.today()
        
        # Status counts
        status_counts = {}
        for issue in issues_data:
            status = issue.get('status', 'Unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        done_statuses = {'Done', 'Closed', 'Resolved', 'Release', 'Released', 'Cancelled'}
        completed = sum(cnt for st, cnt in status_counts.items() if st in done_statuses)
        in_progress = status_counts.get('In Progress', 0)
        
        # Type counts
        type_counts = {}
        for issue in issues_data:
            itype = issue.get('issue_type', 'Unknown')
            type_counts[itype] = type_counts.get(itype, 0) + 1
        
        # Overdue count
        overdue_count = 0
        for issue in issues_data:
            due_str = issue.get('due_date', '')[:10] if issue.get('due_date') else None
            status = issue.get('status', '')
            if due_str and status not in done_statuses:
                try:
                    if datetime.strptime(due_str, '%Y-%m-%d').date() < today:
                        overdue_count += 1
                except ValueError:
                    pass
        
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        content = f"🏗️ **Tổng quan dự án**\n\n"
        content += f"• Tổng issues: **{total}**\n"
        content += f"• Hoàn thành: **{completed}** ({completion_rate:.0f}%)\n"
        content += f"• Đang thực hiện: **{in_progress}**\n"
        content += f"• Còn lại: **{total - completed}**\n"
        if overdue_count > 0:
            content += f"• ⚠️ Trễ hạn: **{overdue_count}**\n"
        
        content += "\n**Theo loại issue:**"
        for itype, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            content += f"\n• {itype}: {cnt}"
        
        content += "\n\n**Theo status:**"
        for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
            content += f"\n• {status}: {cnt}"
        
        # Table: status breakdown
        table_data = []
        for status, cnt in sorted(status_counts.items(), key=lambda x: -x[1]):
            table_data.append({'status': status, 'count': cnt, 'percent': f"{cnt/total*100:.0f}%"})
        
        return {"content": content, "output_type": "table", "table_data": table_data, "chart_config": None}
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions with summary info, newest first"""
        sessions = []
        for sid, s in self.sessions.items():
            # Use first user message as title
            title = 'New Chat'
            for m in s.messages:
                if m.role == 'user':
                    title = m.content[:60] + ('...' if len(m.content) > 60 else '')
                    break
            sessions.append({
                'session_id': sid,
                'title': title,
                'created_at': s.created_at.isoformat(),
                'message_count': len(s.messages)
            })
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return sessions

    def clear_session(self, session_id: str) -> bool:
        """Clear/delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False
    
    def get_suggestions(self) -> List[str]:
        """Get suggested queries for the user"""
        return [
            "Tổng quan dự án",
            "Có bao nhiêu bug đang open?",
            "Liệt kê task đang bị trễ",
            "Phân tích workload của team",
            "Báo cáo sprint hiện tại",
            "Vẽ biểu đồ bug theo status",
        ]
