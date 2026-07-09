import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Card, Tabs, Row, Col, Table, Typography, Space, Button, Tag, Descriptions,
  message, Spin, Empty, Modal, Form, Input, Popconfirm, Tooltip, DatePicker, Switch
} from 'antd';
import {
  ArrowLeftOutlined, CodeOutlined, FileAddOutlined, FileExcelOutlined,
  TeamOutlined, FileOutlined, ApartmentOutlined, SyncOutlined, GithubOutlined, PlusOutlined, DeleteOutlined, EditOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import ReactECharts from 'echarts-for-react';
import {
  getProject,
  getProjectStatistics,
  getProjectDevelopers,
  getProjectLanguages,
  getProjectFiles,
  getProjectFolders,
  getRepositories,
  addRepository,
  syncRepository,
  deleteRepository,
  updateRepositoryBranch,
  updateDeveloperExclusion
} from '../services/api';

const { Title, Text } = Typography;

const statusColors = {
  pending: 'default',
  cloning: 'processing',
  parsing: 'warning',
  calculating: 'cyan',
  completed: 'success',
  failed: 'error',
  syncing: 'processing',
};

const ProjectDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState(null);
  const [repositories, setRepositories] = useState([]);
  const [overview, setOverview] = useState({});
  const [daily, setDaily] = useState([]);
  const [monthly, setMonthly] = useState([]);
  const [developers, setDevelopers] = useState([]);
  const [languages, setLanguages] = useState([]);
  const [files, setFiles] = useState([]);
  const [folders, setFolders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [dateRange, setDateRange] = useState([dayjs().subtract(1, 'month'), dayjs()]);

  const [repoModalOpen, setRepoModalOpen] = useState(false);
  const [creatingRepo, setCreatingRepo] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    try {
      const params = {};
      if (dateRange && dateRange.length === 2) {
        params.start_date = dateRange[0].toISOString();
        params.end_date = dateRange[1].toISOString();
      }
      
      // Parallel requests
      const [
        projRes,
        repoRes,
        statRes,
        devRes,
        langRes,
        fileRes,
        folderRes
      ] = await Promise.all([
        getProject(id),
        getRepositories(id),
        getProjectStatistics(id, params).catch(() => ({ data: {} })),
        getProjectDevelopers(id, params).catch(() => ({ data: { items: [] } })),
        getProjectLanguages(id, params).catch(() => ({ data: [] })),
        getProjectFiles(id, params).catch(() => ({ data: [] })),
        getProjectFolders(id, params).catch(() => ({ data: [] })),
      ]);

      setProject(projRes.data);
      setRepositories(repoRes.data?.items || []);

      if (statRes.data.overview) {
        setOverview(statRes.data.overview);
        setDaily(statRes.data.daily || []);
        setMonthly(statRes.data.monthly || []);
      }
      setDevelopers(devRes.data?.items || []);
      setLanguages(langRes.data || []);
      setFiles(fileRes.data || []);
      setFolders(folderRes.data || []);
    } catch (err) {
      message.error('Failed to load project details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Auto-refresh for background jobs
    return () => clearInterval(interval);
  }, [id, dateRange]);

  const handleAddRepo = async (values) => {
    try {
      setCreatingRepo(true);
      await addRepository(id, values.git_url, values.name, values.access_token, values.branch);
      message.success('Repository added! Cloning will start automatically.');
      setRepoModalOpen(false);
      form.resetFields();
      fetchData();
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to add repository');
    } finally {
      setCreatingRepo(false);
    }
  };

  const handleSyncRepo = async (repoId) => {
    try {
      await syncRepository(repoId);
      message.success('Sync started!');
      fetchData();
    } catch (err) {
      message.error(err.response?.data?.message || 'Failed to sync');
    }
  };

  const handleEditBranch = (repo) => {
    Modal.prompt({
      title: 'Edit Branch',
      content: 'Enter the new branch name to analyze (this will delete old data for this repo and start fresh):',
      initialValue: repo.default_branch || 'main',
      onOk: async (branch) => {
        if (!branch) return;
        try {
          await updateRepositoryBranch(repo.id, branch);
          message.success('Branch updated. Re-cloning repository...');
          fetchData();
        } catch (err) {
          message.error(err.response?.data?.message || 'Failed to update branch');
        }
      }
    });
  };

  const handleDeleteRepo = async (repoId) => {
    try {
      await deleteRepository(repoId);
      message.success('Repository deleted');
      fetchData();
    } catch (err) {
      message.error('Failed to delete repository');
    }
  };


  if (loading && !project) {
    return (
      <div style={{ textAlign: 'center', padding: 100 }}>
        <Spin size="large" />
      </div>
    );
  }

  // "?"?"? Charts Options "?"?"?
  const commitLineOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: daily.map(d => new Date(d.date).toLocaleDateString()) },
    yAxis: { type: 'value' },
    series: [{
      data: daily.map(d => d.total_commits),
      type: 'line',
      smooth: true,
      areaStyle: { opacity: 0.1 },
      itemStyle: { color: '#6366f1' }
    }]
  };

  const locAreaOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['Added', 'Deleted'] },
    xAxis: { type: 'category', data: daily.map(d => new Date(d.date).toLocaleDateString()) },
    yAxis: { type: 'value' },
    series: [
      {
        name: 'Added',
        data: daily.map(d => d.added_lines),
        type: 'line',
        smooth: true,
        itemStyle: { color: '#10b981' }
      },
      {
        name: 'Deleted',
        data: daily.map(d => d.deleted_lines),
        type: 'line',
        smooth: true,
        itemStyle: { color: '#ef4444' }
      }
    ]
  };

  const monthlyBarOption = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: monthly.map(m => `${m.month}/${m.year}`) },
    yAxis: { type: 'value' },
    series: [{
      data: monthly.map(m => m.total_commits),
      type: 'bar',
      itemStyle: { color: '#8b5cf6', borderRadius: [4, 4, 0, 0] }
    }]
  };

  const langPieOption = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} files ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
      label: { show: true, formatter: '{b} ({d}%)' },
      data: languages.map(l => ({ value: l.file_count, name: l.language }))
    }]
  };

  const topDevOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: [...developers].slice(0, 10).reverse().map(d => d.name) },
    series: [{
      type: 'bar',
      data: [...developers].slice(0, 10).reverse().map(d => d.commit_count),
      itemStyle: { color: '#3b82f6', borderRadius: [0, 4, 4, 0] }
    }]
  };

  // "?"?"? Tables Columns "?"?"?
  const repoColumns = [
    {
      title: 'Repository Name',
      dataIndex: 'name',
      key: 'name',
      render: (name) => <span style={{ fontWeight: 600 }}>{name}</span>,
    },
    {
      title: 'Git URL',
      dataIndex: 'git_url',
      key: 'git_url',
      ellipsis: true,
      render: (url) => <span style={{ opacity: 0.7 }}>{url}</span>,
    },
    {
      title: 'Branch',
      dataIndex: 'default_branch',
      key: 'branch',
      width: 100,
      render: (branch) => <Tag color="blue">{branch || 'main'}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 130,
      render: (status) => (
        <Tag
          color={statusColors[status]}
          icon={['cloning', 'parsing', 'calculating', 'syncing'].includes(status) ? <SyncOutlined spin /> : null}
        >
          {status.toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Last Sync',
      dataIndex: 'last_sync',
      key: 'last_sync',
      width: 180,
      render: (date) => date ? new Date(date).toLocaleString('vi-VN') : '-',
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 100,
      render: (_, record) => (
        <Space>
          <Tooltip title="Edit Branch">
            <Button
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEditBranch(record)}
            />
          </Tooltip>
          <Tooltip title="Sync">
            <Button
              size="small"
              icon={<SyncOutlined />}
              onClick={() => handleSyncRepo(record.id)}
              disabled={['cloning', 'parsing', 'syncing', 'calculating'].includes(record.status)}
            />
          </Tooltip>
          <Popconfirm
            title="Delete this repository?"
            onConfirm={() => handleDeleteRepo(record.id)}
          >
            <Tooltip title="Delete">
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const devColumns = [
    { title: 'Developer', dataIndex: 'name', key: 'name', render: (n) => <b>{n}</b> },
    { title: 'Email', dataIndex: 'email', key: 'email', render: (e) => <span style={{ opacity: 0.7 }}>{e}</span> },
    { title: 'Commits', dataIndex: 'commit_count', key: 'commits', sorter: (a, b) => a.commit_count - b.commit_count, defaultSortOrder: 'descend' },
    { title: 'Lines Added', dataIndex: 'total_added', key: 'added', render: (v) => <Text type="success">+{v?.toLocaleString()}</Text> },
    { title: 'Lines Deleted', dataIndex: 'total_deleted', key: 'deleted', render: (v) => <Text type="danger">-{v?.toLocaleString()}</Text> },
    {
      title: 'Include in Stats',
      key: 'action',
      render: (_, record) => {
        const isExcluded = record.is_excluded;
        return (
          <Tooltip title={isExcluded ? "Data currently excluded globally. Click to include." : "Data currently included. Click to exclude."}>
            <Switch 
              checked={!isExcluded} 
              onChange={async (checked) => {
                try {
                  await updateDeveloperExclusion(record.id, !checked);
                  message.success(`Developer stats ${checked ? 'included' : 'excluded'} successfully.`);
                  fetchData();
                } catch (error) {
                  message.error('Failed to update developer exclusion.');
                }
              }} 
            />
          </Tooltip>
        );
      }
    },
    { title: 'Net Lines', dataIndex: 'net_lines', key: 'net', render: (v) => <Text strong>{v?.toLocaleString()}</Text> },
    { title: 'First Commit', dataIndex: 'first_commit', key: 'first', render: (d) => d ? new Date(d).toLocaleDateString('vi-VN') : '-' },
    { title: 'Last Commit', dataIndex: 'last_commit', key: 'last', render: (d) => d ? new Date(d).toLocaleDateString('vi-VN') : '-' },
  ];

  const fileColumns = [
    { title: '#', key: 'idx', width: 50, render: (_, __, i) => i + 1 },
    { title: 'File', dataIndex: 'filename', key: 'filename', ellipsis: true },
    { title: 'Folder', dataIndex: 'folder', key: 'folder', width: 150 },
    { title: 'Commits', dataIndex: 'commit_count', key: 'commits', sorter: (a, b) => a.commit_count - b.commit_count, defaultSortOrder: 'descend' },
    { title: 'Added', dataIndex: 'added_lines', key: 'added', render: (v) => <Text type="success">+{v?.toLocaleString()}</Text> },
    { title: 'Deleted', dataIndex: 'deleted_lines', key: 'deleted', render: (v) => <Text type="danger">-{v?.toLocaleString()}</Text> },
  ];

  const folderColumns = [
    { title: 'Folder', dataIndex: 'folder', key: 'folder' },
    { title: 'Commits', dataIndex: 'commit_count', key: 'commits', sorter: (a, b) => a.commit_count - b.commit_count, defaultSortOrder: 'descend' },
    { title: 'Added', dataIndex: 'added_lines', key: 'added', render: (v) => <Text type="success">+{v?.toLocaleString()}</Text> },
    { title: 'Deleted', dataIndex: 'deleted_lines', key: 'deleted', render: (v) => <Text type="danger">-{v?.toLocaleString()}</Text> },
  ];

  const tabItems = [
    {
      key: 'overview',
      label: 'Overview',
      children: (
        <>
          {/* Stat Cards */}
          <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-primary animate-in">
                <div className="stat-icon"><CodeOutlined /></div>
                <div className="stat-value">{overview.total_commits?.toLocaleString() || 0}</div>
                <div className="stat-label">Total Commits</div>
              </div>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-success animate-in">
                <div className="stat-icon"><FileAddOutlined /></div>
                <div className="stat-value">{overview.total_added_lines?.toLocaleString() || 0}</div>
                <div className="stat-label">Lines Added</div>
              </div>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-danger animate-in">
                <div className="stat-icon"><FileExcelOutlined /></div>
                <div className="stat-value">{overview.total_deleted_lines?.toLocaleString() || 0}</div>
                <div className="stat-label">Lines Deleted</div>
              </div>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-info animate-in">
                <div className="stat-icon"><TeamOutlined /></div>
                <div className="stat-value">{overview.total_developers || 0}</div>
                <div className="stat-label">Contributors</div>
              </div>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-primary animate-in">
                <div className="stat-icon"><FileOutlined /></div>
                <div className="stat-value">{overview.total_files_changed?.toLocaleString() || 0}</div>
                <div className="stat-label">Files Changed</div>
              </div>
            </Col>
            <Col xs={24} sm={12} lg={4}>
              <div className="stat-card gradient-success animate-in">
                <div className="stat-icon"><ApartmentOutlined /></div>
                <div className="stat-value">{languages.length}</div>
                <div className="stat-label">Languages</div>
              </div>
            </Col>
          </Row>

          {/* Charts */}
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={12}>
              <Card className="chart-card" title="Commits per Day" style={{ borderRadius: 16 }}>
                <ReactECharts option={commitLineOption} style={{ height: 320 }} />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card className="chart-card" title="Lines Added / Deleted" style={{ borderRadius: 16 }}>
                <ReactECharts option={locAreaOption} style={{ height: 320 }} />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card className="chart-card" title="Commits per Month" style={{ borderRadius: 16 }}>
                <ReactECharts option={monthlyBarOption} style={{ height: 320 }} />
              </Card>
            </Col>
            <Col xs={24} lg={12}>
              <Card className="chart-card" title="Language Distribution" style={{ borderRadius: 16 }}>
                <ReactECharts option={langPieOption} style={{ height: 320 }} />
              </Card>
            </Col>
            <Col xs={24}>
              <Card className="chart-card" title="Top Developers (by commits)" style={{ borderRadius: 16 }}>
                <ReactECharts option={topDevOption} style={{ height: 350 }} />
              </Card>
            </Col>
          </Row>
        </>
      ),
    },
    {
      key: 'repositories',
      label: `Repositories (${repositories.length})`,
      children: (
        <Card
          title="Repositories"
          extra={
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setRepoModalOpen(true)}>
              Add Repository
            </Button>
          }
          style={{ borderRadius: 16 }}
        >
          <Table
            dataSource={repositories}
            columns={repoColumns}
            rowKey="id"
            pagination={{ pageSize: 10 }}
            locale={{
              emptyText: <Empty description="No repositories added to this project yet." />
            }}
          />
        </Card>
      ),
    },
    {
      key: 'developers',
      label: `Developers (${developers.length})`,
      children: (
        <Card style={{ borderRadius: 16 }}>
          <Table
            dataSource={developers}
            columns={devColumns}
            rowKey="id"
            pagination={{ pageSize: 20 }}
            scroll={{ x: 1200 }}
          />
        </Card>
      ),
    },
    {
      key: 'files',
      label: `Files (${files.length})`,
      children: (
        <Card title="Top 100 Most Modified Files" style={{ borderRadius: 16 }}>
          <Table
            dataSource={files}
            columns={fileColumns}
            rowKey="filename"
            pagination={{ pageSize: 20 }}
            scroll={{ x: 900 }}
          />
        </Card>
      ),
    },
    {
      key: 'folders',
      label: `Folders (${folders.length})`,
      children: (
        <Card title="Top Folders" style={{ borderRadius: 16 }}>
          <Table
            dataSource={folders}
            columns={folderColumns}
            rowKey="folder"
            pagination={{ pageSize: 20 }}
          />
        </Card>
      ),
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 16 }}>
        <Space size="middle">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
            Back
          </Button>
          <Title level={4} style={{ margin: 0 }}>{project?.name}</Title>
        </Space>
        <Space>
          <Text strong>Filter by Date:</Text>
          <DatePicker.RangePicker 
            value={dateRange} 
            onChange={(dates) => setDateRange(dates)} 
            allowClear={false}
            size="large"
          />
        </Space>
      </div>

      {/* Project Info */}
      <Card style={{ borderRadius: 16, marginBottom: 24 }}>
        <Descriptions column={{ xs: 1, sm: 2, lg: 4 }}>
          <Descriptions.Item label="Description">{project?.description || 'N/A'}</Descriptions.Item>
          <Descriptions.Item label="Created">
            {new Date(project?.created_at).toLocaleString('vi-VN')}
          </Descriptions.Item>
          <Descriptions.Item label="Total Repositories">
            {repositories.length}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabItems}
        size="large"
      />

      {/* Add Repository Modal */}
      <Modal
        title="Add Git Repository"
        open={repoModalOpen}
        onCancel={() => { setRepoModalOpen(false); form.resetFields(); }}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleAddRepo}>
          <Form.Item
            name="git_url"
            label="Git URL"
            rules={[
              { required: true, message: 'Please enter a git URL' },
              {
                pattern: /^https?:\/\/[\w.\-]+(\/[\w.\-]+)+(\.git)?$/,
                message: 'Invalid URL format. Example: https://github.com/owner/repo.git or https://gitlab.com/group/repo.git',
              },
            ]}
          >
            <Input
              placeholder="https://github.com/owner/repo.git"
              size="large"
              prefix={<GithubOutlined />}
            />
          </Form.Item>
          <Form.Item name="name" label="Repository Name (optional)">
            <Input placeholder="Auto-detected from URL" size="large" />
          </Form.Item>
          <Form.Item
            name="access_token"
            label="Personal Access Token"
            tooltip="Required only for private repositories"
          >
            <Input.Password placeholder="ghp_xxxxxxxxxxxx" />
          </Form.Item>
          <Form.Item
            name="branch"
            label="Branch"
            tooltip="Branch to analyze (defaults to main if not specified)"
          >
            <Input placeholder="main" />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              loading={creatingRepo}
              block
              size="large"
              style={{ borderRadius: 8 }}
            >
              Add Repository
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ProjectDetail;
