import React, { useState, useEffect } from 'react';
import {
  Card, Table, Button, Tag, Space, Modal, Form, Input,
  message, Tooltip, Popconfirm, Row, Col, Empty
} from 'antd';
import {
  GithubOutlined, PlusOutlined, DeleteOutlined,
  SyncOutlined, EyeOutlined, ProjectOutlined,
  CodeOutlined, TeamOutlined, ApartmentOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getProjects, createProject, deleteProject } from '../services/api';

const Dashboard = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchProjects = async () => {
    try {
      setLoading(true);
      const { data } = await getProjects(1, 100);
      setProjects(data.items || []);
    } catch (err) {
      message.error('Failed to load projects');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProjects();
    // Auto-refresh every 10s for status updates
    const interval = setInterval(fetchProjects, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleCreate = async (values) => {
    try {
      setCreating(true);
      await createProject(values.name, values.description);
      message.success('Project added!');
      setModalOpen(false);
      form.resetFields();
      fetchProjects();
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to create project');
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteProject(id);
      message.success('Project deleted');
      fetchProjects();
    } catch (err) {
      message.error('Failed to delete project');
    }
  };

  const totalProjects = projects.length;

  const columns = [
    {
      title: 'Project Name',
      dataIndex: 'name',
      key: 'name',
      render: (name, record) => (
        <Space>
          <ProjectOutlined style={{ fontSize: 18, color: '#6366f1' }} />
          <a onClick={() => navigate(`/projects/${record.id}`)}
            style={{ fontWeight: 600, fontSize: 15 }}>
            {name}
          </a>
        </Space>
      ),
    },
    {
      title: 'Description',
      dataIndex: 'description',
      key: 'description',
      ellipsis: true,
      render: (desc) => <span style={{ opacity: 0.7, fontSize: 13 }}>{desc || 'No description'}</span>,
    },
    {
      title: 'Created At',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date) => new Date(date).toLocaleString('vi-VN'),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Space>
          <Tooltip title="View Dashboard">
            <Button
              type="primary"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => navigate(`/projects/${record.id}`)}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this project?"
            onConfirm={() => handleDelete(record.id)}
          >
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {/* Overview Cards */}
      <Row gutter={[20, 20]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <div className="stat-card gradient-primary animate-in">
            <div className="stat-icon"><ProjectOutlined /></div>
            <div className="stat-value">{totalProjects}</div>
            <div className="stat-label">Total Projects</div>
          </div>
        </Col>
      </Row>

      {/* Projects Table */}
      <Card
        title={
          <Space>
            <ProjectOutlined />
            <span style={{ fontWeight: 600 }}>Projects</span>
          </Space>
        }
        extra={
          <Space>
            <Button
              type="default"
              icon={<ProjectOutlined />}
              onClick={() => navigate('/reports')}
              style={{ borderRadius: 8 }}
            >
              Management Report
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setModalOpen(true)}
              style={{ borderRadius: 8 }}
            >
              Add Project
            </Button>
          </Space>
        }
        style={{ borderRadius: 16 }}
      >
        <Table
          dataSource={projects}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No projects yet. Add your first project!"
              />
            ),
          }}
        />
      </Card>

      {/* Add Project Modal */}
      <Modal
        title="Add Project"
        open={modalOpen}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            name="name"
            label="Project Name"
            rules={[{ required: true, message: 'Please enter a project name' }]}
          >
            <Input placeholder="E.g., Microservices ERP" size="large" />
          </Form.Item>
          <Form.Item name="description" label="Description (optional)">
            <Input.TextArea placeholder="A brief description" rows={3} />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={creating}
              block
              size="large"
              style={{ borderRadius: 8 }}
            >
              Add Project
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Dashboard;
