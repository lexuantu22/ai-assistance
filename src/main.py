"""
Main entry point for JIRA Chat Agent
"""
import os
import sys
import argparse
import yaml
from dotenv import load_dotenv


def load_config():
    """Load configuration from settings.yaml"""
    candidates = [
        os.path.join(os.path.dirname(__file__), '..', 'config', 'settings.yaml'),
        os.path.join(os.getcwd(), 'config', 'settings.yaml'),
    ]
    for config_path in candidates:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
    return {}


def run_web_server(config: dict, host: str = None, port: int = None, debug: bool = False):
    """Run the web server"""
    from .web import app
    
    web_config = config.get('web', {})
    app.run(
        host=host or web_config.get('host', '0.0.0.0'),
        port=port or web_config.get('port', 5000),
        debug=debug or web_config.get('debug', False)
    )


def run_cli_chat(config: dict):
    """Run interactive CLI chat"""
    from .chat_agent import ChatAgent
    
    agent = ChatAgent(config)
    session_id = None
    
    print("=" * 60)
    print("🎯 JIRA Chat Agent - Interactive Mode")
    print("=" * 60)
    print("Nhập câu hỏi của bạn hoặc 'quit' để thoát.")
    print("Gõ 'clear' để xóa lịch sử chat.")
    print("Gõ 'help' để xem gợi ý câu hỏi.")
    print("=" * 60)
    print()
    
    while True:
        try:
            user_input = input("👤 Bạn: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Tạm biệt!")
                break
            
            if user_input.lower() == 'clear':
                if session_id:
                    agent.clear_session(session_id)
                session_id = None
                print("✅ Đã xóa lịch sử chat.\n")
                continue
            
            if user_input.lower() == 'help':
                print("\n📝 Gợi ý câu hỏi:")
                for suggestion in agent.get_suggestions():
                    print(f"   • {suggestion}")
                print()
                continue
            
            # Send message to agent
            result = agent.chat(user_input, session_id)
            session_id = result['session_id']
            response = result['response']
            
            print(f"\n🤖 Assistant: {response['content']}")
            
            # Display table if present
            if response.get('output_type') == 'table' and response.get('table_data'):
                print("\n" + format_table(response['table_data']))
            
            # Display chart info if present
            if response.get('output_type') == 'chart' and response.get('chart_config'):
                print("\n📊 [Chart data available - view in web interface for visualization]")
                chart_data = response['chart_config'].get('data', {})
                labels = chart_data.get('labels', [])
                values = chart_data.get('datasets', [{}])[0].get('data', [])
                for label, value in zip(labels, values):
                    print(f"   • {label}: {value}")
            
            print()
            
        except KeyboardInterrupt:
            print("\n\n👋 Tạm biệt!")
            break
        except Exception as e:
            print(f"\n❌ Lỗi: {str(e)}\n")


def format_table(data: list) -> str:
    """Format table data as ASCII table"""
    if not data:
        return ""
    
    # Get column headers
    headers = list(data[0].keys())
    
    # Calculate column widths
    widths = {h: len(h) for h in headers}
    for row in data:
        for h in headers:
            widths[h] = max(widths[h], len(str(row.get(h, ''))))
    
    # Limit column widths
    max_width = 30
    widths = {h: min(w, max_width) for h, w in widths.items()}
    
    # Build table
    lines = []
    
    # Header
    header_line = " | ".join(h.ljust(widths[h])[:widths[h]] for h in headers)
    lines.append(header_line)
    lines.append("-" * len(header_line))
    
    # Rows
    for row in data:
        row_line = " | ".join(str(row.get(h, '')).ljust(widths[h])[:widths[h]] for h in headers)
        lines.append(row_line)
    
    return "\n".join(lines)


def main():
    """Main entry point"""
    # Load environment variables
    load_dotenv()
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='JIRA Chat Agent')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Web server command
    web_parser = subparsers.add_parser('web', help='Run web server')
    web_parser.add_argument('--host', default=None, help='Host to bind to')
    web_parser.add_argument('--port', type=int, default=None, help='Port to bind to')
    web_parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    # CLI chat command
    chat_parser = subparsers.add_parser('chat', help='Run interactive CLI chat')
    
    # Test connection command
    test_parser = subparsers.add_parser('test', help='Test JIRA connection')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    if args.command == 'web':
        print("🚀 Starting web server...")
        run_web_server(config, args.host, args.port, args.debug)
    
    elif args.command == 'chat':
        run_cli_chat(config)
    
    elif args.command == 'test':
        from .jira_client import JiraClient
        client = JiraClient(config)
        if client.test_connection():
            print("✅ JIRA connection successful!")
        else:
            print("❌ JIRA connection failed!")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
