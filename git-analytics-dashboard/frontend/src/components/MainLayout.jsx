import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Switch, Space, Typography } from 'antd';
import {
  DashboardOutlined,
  GithubOutlined,
  BulbOutlined,
  BulbFilled,
  LogoutOutlined,
} from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

const MainLayout = ({ children, isDark, setIsDark }) => {
  const { logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: '/',
      icon: <DashboardOutlined />,
      label: 'Dashboard',
    },
    {
      key: '/reports',
      icon: <BulbOutlined />,
      label: 'Global Reports',
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={260}
        theme="dark"
        style={{
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 100,
        }}
      >
        <div className="sidebar-logo">
          <div className="logo-icon">
            <GithubOutlined />
          </div>
          {!collapsed && (
            <span className="logo-text">Git Analytics</span>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8 }}
        />
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 260, transition: 'margin-left 0.2s' }}>
        <Header
          style={{
            padding: 0,
            position: 'sticky',
            top: 0,
            zIndex: 99,
            backdropFilter: 'blur(10px)',
            borderBottom: '1px solid rgba(255,255,255,0.06)',
          }}
        >
          <div className="header-content">
            <span className="header-title">
              {location.pathname === '/' ? 'Dashboard' : 'Project Detail'}
            </span>
            <Space size="middle">
              <Switch
                checked={isDark}
                onChange={setIsDark}
                checkedChildren={<BulbFilled />}
                unCheckedChildren={<BulbOutlined />}
              />
              <span 
                onClick={logout} 
                style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500, color: '#ef4444' }}
              >
                <LogoutOutlined /> Logout
              </span>
            </Space>
          </div>
        </Header>

        <Content style={{ padding: 24, minHeight: 'calc(100vh - 64px)' }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
