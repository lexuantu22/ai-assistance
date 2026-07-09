import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Table, Typography, Space, Button, DatePicker, Select, Tag
} from 'antd';
import {
  ArrowLeftOutlined, TeamOutlined, ProjectOutlined, LineChartOutlined, CodeOutlined
} from '@ant-design/icons';
import dayjs from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { getReportDevelopers, getReportProjects, getProjects } from '../services/api';

const { Title, Text } = Typography;
const { Option } = Select;

const Reports = () => {
  const navigate = useNavigate();
  
  const [dateRange, setDateRange] = useState([dayjs().subtract(1, 'month'), dayjs()]);
  const [selectedProjects, setSelectedProjects] = useState([]);
  
  const [projectsList, setProjectsList] = useState([]);
  const [developers, setDevelopers] = useState([]);
  const [projectStats, setProjectStats] = useState([]);
  
  const [loading, setLoading] = useState(false);

  // Fetch list of projects for the filter dropdown
  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await getProjects(1, 100);
        setProjectsList(res.data.items);
      } catch (err) {
        console.error("Failed to load projects", err);
      }
    };
    fetchProjects();
  }, []);

  // Fetch report data
  const fetchReports = async () => {
    setLoading(true);
    try {
      const params = {};
      if (dateRange && dateRange.length === 2) {
        params.start_date = dateRange[0].toISOString();
        params.end_date = dateRange[1].toISOString();
      }
      if (selectedProjects.length > 0) {
        params.project_ids = selectedProjects;
      }

      const [devRes, projRes] = await Promise.all([
        getReportDevelopers(params),
        getReportProjects(params)
      ]);
      
      setDevelopers(devRes.data.items || []);
      setProjectStats(projRes.data || []);
    } catch (err) {
      console.error("Failed to fetch reports", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateRange, selectedProjects]);

  const devColumns = [
    { title: 'Developer', dataIndex: 'name', key: 'name', render: (n) => <Text strong>{n}</Text> },
    { title: 'Email', dataIndex: 'email', key: 'email', render: (e) => <span style={{ opacity: 0.7 }}>{e}</span> },
    { 
      title: 'Projects', 
      dataIndex: 'project_names', 
      key: 'projects',
      render: (projects) => (
        <Space wrap>
          {projects.map(p => <Tag color="blue" key={p}>{p}</Tag>)}
        </Space>
      )
    },
    { title: 'Total Commits', dataIndex: 'commit_count', key: 'commits', sorter: (a, b) => a.commit_count - b.commit_count, defaultSortOrder: 'descend' },
    { title: 'Lines Added', dataIndex: 'total_added', key: 'added', sorter: (a, b) => (a.total_added || 0) - (b.total_added || 0), render: (v) => <Text type="success">+{v?.toLocaleString()}</Text> },
    { title: 'Lines Deleted', dataIndex: 'total_deleted', key: 'deleted', sorter: (a, b) => (a.total_deleted || 0) - (b.total_deleted || 0), render: (v) => <Text type="danger">-{v?.toLocaleString()}</Text> },
  ];

  const projColumns = [
    { title: 'Project Name', dataIndex: 'project_name', key: 'name', render: (n) => <Text strong>{n}</Text> },
    { title: 'Total Commits', dataIndex: 'total_commits', key: 'commits', sorter: (a, b) => a.total_commits - b.total_commits, defaultSortOrder: 'descend' },
    { title: 'Active Developers', dataIndex: 'active_developers', key: 'devs' },
    { title: 'Lines Added', dataIndex: 'total_added', key: 'added', sorter: (a, b) => (a.total_added || 0) - (b.total_added || 0), render: (v) => <Text type="success">+{v?.toLocaleString()}</Text> },
    { title: 'Lines Deleted', dataIndex: 'total_deleted', key: 'deleted', sorter: (a, b) => (a.total_deleted || 0) - (b.total_deleted || 0), render: (v) => <Text type="danger">-{v?.toLocaleString()}</Text> },
  ];

  const topDevs = [...developers].slice(0, 15).reverse();
  const developerComparisonOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: ['Lines Added', 'Lines Deleted'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    yAxis: { type: 'category', data: topDevs.map(d => d.name) },
    xAxis: { type: 'value', name: 'Lines' },
    series: [
      {
        name: 'Lines Added',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] },
        data: topDevs.map(d => d.total_added)
      },
      {
        name: 'Lines Deleted',
        type: 'bar',
        stack: 'total',
        itemStyle: { color: '#ef4444', borderRadius: [4, 0, 0, 4] },
        data: topDevs.map(d => d.total_deleted)
      }
    ]
  };

  const projectComparisonOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: projectStats.map(p => p.project_name), axisLabel: { interval: 0, rotate: 15 } },
    yAxis: { type: 'value', name: 'Commits' },
    series: [
      {
        name: 'Total Commits',
        type: 'bar',
        itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
        data: projectStats.map(p => p.total_commits)
      }
    ]
  };

  const totalCommits = projectStats.reduce((sum, p) => sum + p.total_commits, 0);
  const totalProjects = projectStats.length;
  const totalDevs = developers.length;
  const totalLinesAdded = projectStats.reduce((sum, p) => sum + p.total_added, 0);

  return (
    <div className="animate-in">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 16 }}>
        <Space size="middle">
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
            Back
          </Button>
          <Title level={3} style={{ margin: 0 }}>Management Dashboard</Title>
        </Space>
        
        <Space size="large" wrap>
          <Space>
            <Text strong>Filter by Projects:</Text>
            <Select
              mode="multiple"
              allowClear
              placeholder="All Projects"
              style={{ minWidth: 250 }}
              value={selectedProjects}
              onChange={setSelectedProjects}
              maxTagCount="responsive"
            >
              {projectsList.map(p => (
                <Option key={p.id} value={p.id}>{p.name}</Option>
              ))}
            </Select>
          </Space>
          
          <Space>
            <Text strong>Date Range:</Text>
            <DatePicker.RangePicker 
              value={dateRange} 
              onChange={(dates) => setDateRange(dates)} 
              allowClear={false}
              size="large"
            />
          </Space>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <div className="stat-card gradient-primary">
            <div className="stat-icon"><ProjectOutlined /></div>
            <div className="stat-value">{totalProjects}</div>
            <div className="stat-label">Active Projects</div>
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="stat-card gradient-success">
            <div className="stat-icon"><TeamOutlined /></div>
            <div className="stat-value">{totalDevs}</div>
            <div className="stat-label">Active Developers</div>
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="stat-card gradient-info">
            <div className="stat-icon"><LineChartOutlined /></div>
            <div className="stat-value">{totalCommits.toLocaleString()}</div>
            <div className="stat-label">Total Commits</div>
          </div>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <div className="stat-card gradient-warning">
            <div className="stat-icon"><CodeOutlined /></div>
            <div className="stat-value">+{totalLinesAdded.toLocaleString()}</div>
            <div className="stat-label">Lines Added</div>
          </div>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card 
            title={<Space><ProjectOutlined /> Project Commit Comparison</Space>}
            style={{ borderRadius: 16 }}
            loading={loading}
          >
            <ReactECharts option={projectComparisonOption} style={{ height: 400 }} />
          </Card>
        </Col>

        <Col xs={24} xl={12}>
          <Card 
            title={<Space><TeamOutlined /> Developer Code Churn (Top 15)</Space>}
            style={{ borderRadius: 16 }}
            loading={loading}
          >
            <ReactECharts option={developerComparisonOption} style={{ height: 400 }} />
          </Card>
        </Col>

        <Col xs={24}>
          <Card 
            title={<Space><TeamOutlined /> Top Developers (Cross-Project)</Space>}
            style={{ borderRadius: 16 }}
          >
            <Table
              dataSource={developers}
              columns={devColumns}
              rowKey="id"
              loading={loading}
              pagination={{ pageSize: 10 }}
            />
          </Card>
        </Col>
        
        <Col xs={24}>
          <Card 
            title={<Space><LineChartOutlined /> Project Metrics Overview</Space>}
            style={{ borderRadius: 16 }}
          >
            <Table
              dataSource={projectStats}
              columns={projColumns}
              rowKey="project_id"
              loading={loading}
              pagination={false}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default Reports;
