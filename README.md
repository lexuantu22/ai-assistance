# JIRA Chat Agent

🎯 Chat agent để truy vấn dữ liệu JIRA bằng ngôn ngữ tự nhiên.

## Tính năng

- 💬 **Chat Interface**: Giao diện chat trực quan để hỏi đáp về dữ liệu JIRA
- 🔍 **Natural Language Query**: Hỏi bằng tiếng Việt hoặc tiếng Anh
- 📊 **Visualization**: Hiển thị kết quả dạng bảng, text, hoặc biểu đồ
- 🔄 **Context Awareness**: Nhớ context trong conversation
- 🤖 **AI-Powered**: Sử dụng GPT-4 để phân tích câu hỏi

## Cài đặt

### 1. Clone repository

```bash
git clone https://github.com/your-repo/jira-chat-agent.git
cd jira-chat-agent
```

### 2. Tạo virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

### 3. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 4. Cấu hình

Tạo file `.env` từ template:

```bash
cp .env.example .env
```

Chỉnh sửa `.env` với thông tin của bạn:

```env
JIRA_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_TOKEN=your-jira-api-token
OPENAI_API_KEY=sk-your-openai-api-key
```

Cập nhật `config/settings.yaml`:
- `project_key`: Key của project JIRA (ví dụ: "PROJ")
- `board_id`: ID của Scrum/Kanban board

## Sử dụng

### Web Interface

```bash
python -m src.main web
```

Truy cập http://localhost:5000

### CLI Mode

```bash
python -m src.main chat
```

### Test JIRA Connection

```bash
python -m src.main test
```

## Ví dụ câu hỏi

- "Có bao nhiêu bug đang open?"
- "Liệt kê các task đang bị trễ"
- "Thống kê bug theo sprint"
- "Vẽ biểu đồ bug theo priority"
- "Bug nào đến hạn trong tuần này?"
- "Ai đang có nhiều task nhất?"
- "So sánh số lượng bug giữa sprint 10 và sprint 11"

## API Endpoints

### POST /api/chat

Gửi message và nhận response từ AI.

```json
// Request
{
    "message": "Có bao nhiêu bug đang open?",
    "session_id": "optional-session-id"
}

// Response
{
    "session_id": "abc123",
    "response": {
        "content": "Hiện có **15 bugs** đang ở trạng thái Open.",
        "output_type": "text",
        "table_data": null,
        "chart_config": null
    }
}
```

### GET /api/suggestions

Lấy danh sách câu hỏi gợi ý.

### GET /api/health

Health check endpoint.

## Cấu trúc project

```
jira-chat-agent/
├── config/
│   └── settings.yaml       # Configuration file
├── src/
│   ├── __init__.py
│   ├── main.py             # Entry point, CLI commands
│   ├── web.py              # Flask web server
│   ├── chat_agent.py       # Main orchestrator
│   ├── jira_client.py      # JIRA API wrapper
│   └── ai_analyzer.py      # LLM integration
├── static/
│   ├── index.html          # Main UI
│   ├── style.css           # Styling
│   └── app.js              # Frontend logic
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## License

MIT License
