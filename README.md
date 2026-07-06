# Git Analytics Dashboard

Hệ thống phân tích Git Repository toàn diện.

## Tính năng

- 📊 **Dashboard** - Tổng quan dữ liệu Git với biểu đồ trực quan
- 👥 **Developer Report** - Thống kê chi tiết từng developer
- 📁 **File & Folder Report** - Phân tích file/folder được sửa nhiều nhất
- 🔤 **Language Report** - Phân bố ngôn ngữ lập trình
- 🔄 **Sync** - Đồng bộ commit mới mà không clone lại
- 📥 **Export** - Xuất CSV, Excel, PDF

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 |
| Database | PostgreSQL |
| Queue | Celery, Redis |
| Git Parser | PyDriller, GitPython |
| Frontend | React, Vite, Ant Design, Apache ECharts |
| Auth | JWT |
| Deploy | Docker, Docker Compose |

## Cài đặt & Chạy

### Yêu cầu
- Docker & Docker Compose
- Git

### Quick Start

```bash
# Clone repository
git clone <repo-url>
cd git-analytics-dashboard

# Copy env
cp .env.example .env

# Chỉnh sửa .env với thông tin database, JWT secret, etc.

# Khởi chạy toàn bộ hệ thống
docker-compose up -d --build

# Truy cập
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Mô tả |
|--------|---------|-------|
| POST | `/api/projects` | Thêm project mới |
| GET | `/api/projects` | Danh sách projects |
| GET | `/api/projects/{id}` | Chi tiết project |
| DELETE | `/api/projects/{id}` | Xóa project |
| POST | `/api/projects/{id}/sync` | Sync project |
| GET | `/api/projects/{id}/developers` | Developers của project |
| GET | `/api/projects/{id}/commits` | Commits của project |
| GET | `/api/projects/{id}/statistics` | Thống kê project |
| GET | `/api/projects/{id}/languages` | Phân bố ngôn ngữ |
| GET | `/api/projects/{id}/files` | File report |
| GET | `/api/projects/{id}/folders` | Folder report |

## Kiến trúc

```
git-analytics-dashboard/
├── backend/
│   ├── app/
│   │   ├── api/            # REST API Routes
│   │   ├── core/           # Config, Security, Exceptions
│   │   ├── models/         # SQLAlchemy Models
│   │   ├── schemas/        # Pydantic DTOs
│   │   ├── repositories/   # Data Access Layer
│   │   ├── services/       # Business Logic
│   │   ├── jobs/           # Celery Tasks
│   │   ├── parsers/        # Git Parsing (PyDriller)
│   │   ├── statistics/     # Aggregation Logic
│   │   ├── utils/          # Helpers
│   │   └── database/       # DB Connection
│   ├── migrations/         # Alembic
│   ├── tests/              # Pytest
│   ├── main.py
│   └── celery_app.py
├── frontend/               # React + Vite
├── docker-compose.yml
└── README.md
```

## License

MIT
