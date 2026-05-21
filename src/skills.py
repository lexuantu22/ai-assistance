"""
JIRA Skills Registry - Defines all capabilities the agent can perform.
Skills are injected into the AI system prompt so the LLM maps user queries to the right skill.
"""

SKILLS = {
    # ===== Query Skills =====
    "count_issues": {
        "category": "query",
        "name": "Đếm issues",
        "description": "Đếm số lượng issues (bug, task, story) theo điều kiện lọc",
        "intent_type": "count_issues",
        "output_format": "text",
        "examples": [
            "Có bao nhiêu bug đang open?",
            "Số lượng task chưa closed",
            "Đếm bug theo sprint",
        ],
    },
    "list_issues": {
        "category": "query",
        "name": "Liệt kê issues",
        "description": "Hiển thị danh sách chi tiết issues với key, status, summary, assignee, due date",
        "intent_type": "list_issues",
        "output_format": "table",
        "examples": [
            "Liệt kê các bug đang In Progress",
            "Cho xem danh sách task của Nguyen Van A",
            "List các issue đến hạn trong tuần này",
        ],
    },

    # ===== Analysis Skills =====
    "statistics_by_group": {
        "category": "analysis",
        "name": "Thống kê theo nhóm",
        "description": "Thống kê số lượng issues theo nhóm: status, priority, assignee, sprint, component, label",
        "intent_type": "statistics",
        "output_format": "table",
        "examples": [
            "Thống kê bug theo status",
            "Thống kê task theo priority",
            "Số lượng issue theo component",
        ],
    },
    "overdue_analysis": {
        "category": "analysis",
        "name": "Phân tích issues trễ hạn",
        "description": "Phân tích các issues bị trễ deadline (due date < hôm nay, chưa Done/Closed). Hiển thị chi tiết: key, summary, assignee, due date, số ngày trễ",
        "intent_type": "list_issues",
        "output_format": "table",
        "filters_hint": {"overdue": True},
        "examples": [
            "Bug nào đang bị trễ?",
            "Liệt kê task overdue",
            "Có bao nhiêu issue bị trễ deadline?",
        ],
    },
    "workload_analysis": {
        "category": "analysis",
        "name": "Phân tích khối lượng công việc",
        "description": "Phân tích workload theo assignee: số issues đang được assign, phân bố theo status. Dùng group_by=assignee",
        "intent_type": "statistics",
        "output_format": "table",
        "group_by_hint": "assignee",
        "examples": [
            "Ai đang có nhiều task nhất?",
            "Phân tích workload của team",
            "So sánh khối lượng công việc",
            "Mỗi người đang làm bao nhiêu bug?",
        ],
    },
    "resolution_time": {
        "category": "analysis",
        "name": "Phân tích thời gian xử lý",
        "description": "Phân tích thời gian từ khi tạo issue đến khi resolve. Chỉ áp dụng cho issues đã resolved/closed. Hiển thị avg, min, max resolution time",
        "intent_type": "statistics",
        "output_format": "table",
        "filters_hint": {"status": "closed"},
        "examples": [
            "Thời gian xử lý bug trung bình là bao lâu?",
            "Bug nào mất nhiều thời gian nhất để fix?",
            "Phân tích resolution time theo priority",
        ],
    },
    "created_vs_resolved": {
        "category": "analysis",
        "name": "So sánh tạo mới vs đã xử lý",
        "description": "So sánh số issues tạo mới và số issues đã resolved theo sprint hoặc thời gian. Giúp đánh giá khả năng xử lý của team",
        "intent_type": "statistics",
        "output_format": "table",
        "group_by_hint": "sprint",
        "examples": [
            "So sánh bug tạo mới và bug đã fix theo sprint",
            "Sprint nào resolve nhiều bug nhất?",
            "Tỷ lệ resolve bug qua các sprint",
        ],
    },
    "sprint_report": {
        "category": "analysis",
        "name": "Báo cáo sprint",
        "description": "Báo cáo tổng quan sprint: tổng issues, đã hoàn thành, còn lại, completion rate. Nếu không chỉ rõ sprint → dùng sprint hiện tại",
        "intent_type": "statistics",
        "output_format": "table",
        "filters_hint": {"sprint": "current"},
        "group_by_hint": "status",
        "examples": [
            "Báo cáo sprint hiện tại",
            "Sprint report",
            "Tiến độ sprint này thế nào?",
            "Sprint hiện tại đã hoàn thành bao nhiêu %?",
        ],
    },
    "defect_analysis": {
        "category": "analysis",
        "name": "Phân tích defect",
        "description": "Phân tích bug/defect theo defect_type, component, severity/priority. Giúp tìm root cause và vùng có nhiều lỗi",
        "intent_type": "statistics",
        "output_format": "table",
        "examples": [
            "Phân tích defect theo component",
            "Loại bug nào nhiều nhất?",
            "Thống kê defect theo severity",
            "Component nào có nhiều bug nhất?",
        ],
    },

    # ===== Visualization Skills =====
    "chart_distribution": {
        "category": "visualization",
        "name": "Biểu đồ phân bố",
        "description": "Vẽ biểu đồ bar hoặc pie hiển thị phân bố issues theo một tiêu chí (status, priority, assignee, component, sprint...)",
        "intent_type": "visualization",
        "output_format": "chart",
        "chart_type_hint": "bar",
        "examples": [
            "Vẽ biểu đồ bug theo status",
            "Biểu đồ tròn bug theo priority",
            "Chart phân bố task theo component",
        ],
    },
    "chart_trend": {
        "category": "visualization",
        "name": "Biểu đồ xu hướng",
        "description": "Vẽ biểu đồ line hiển thị xu hướng issues theo thời gian (sprint). Hữu ích để theo dõi trend bug/task qua các sprint",
        "intent_type": "visualization",
        "output_format": "chart",
        "chart_type_hint": "line",
        "group_by_hint": "sprint",
        "examples": [
            "Vẽ biểu đồ xu hướng bug theo sprint",
            "Trend bug qua các sprint",
            "Biểu đồ line task theo sprint",
        ],
    },

    # ===== Project Skills =====
    "project_summary": {
        "category": "project",
        "name": "Tổng quan dự án",
        "description": "Hiển thị tổng quan dự án: tổng issues, phân bố theo status (Open, In Progress, Done, Closed), tỷ lệ hoàn thành, issues trễ hạn. Khi user hỏi chung chung về dự án thì dùng skill này",
        "intent_type": "statistics",
        "output_format": "table",
        "group_by_hint": "status",
        "examples": [
            "Tổng quan dự án",
            "Tình hình dự án thế nào?",
            "Project overview",
            "Dự án đang ở đâu?",
        ],
    },
    "sprint_status": {
        "category": "project",
        "name": "Trạng thái sprint hiện tại",
        "description": "Hiển thị trạng thái sprint đang active: tên sprint, tổng issues, hoàn thành/còn lại, danh sách issues chưa done",
        "intent_type": "statistics",
        "output_format": "table",
        "filters_hint": {"sprint": "current"},
        "group_by_hint": "status",
        "examples": [
            "Sprint hiện tại thế nào?",
            "Trạng thái sprint",
            "Sprint đang chạy có gì?",
        ],
    },
}


def get_skills_prompt() -> str:
    """Generate skills description for the AI system prompt"""
    lines = ["Danh sách SKILLS có sẵn (chọn skill_id phù hợp nhất):"]
    
    categories = {
        "query": "📋 Truy vấn",
        "analysis": "📊 Phân tích",
        "visualization": "📈 Biểu đồ",
        "project": "🏗️ Dự án",
    }
    
    for cat_id, cat_name in categories.items():
        cat_skills = {k: v for k, v in SKILLS.items() if v["category"] == cat_id}
        if not cat_skills:
            continue
        lines.append(f"\n{cat_name}:")
        for skill_id, skill in cat_skills.items():
            examples_str = " | ".join(skill["examples"][:2])
            lines.append(f"  - {skill_id}: {skill['description']}")
            lines.append(f"    VD: {examples_str}")
    
    return "\n".join(lines)


def get_skill(skill_id: str) -> dict:
    """Get a skill definition by ID"""
    return SKILLS.get(skill_id)


def get_all_example_queries() -> list:
    """Get a flat list of all example queries from all skills"""
    examples = []
    for skill in SKILLS.values():
        examples.extend(skill.get("examples", []))
    return examples
