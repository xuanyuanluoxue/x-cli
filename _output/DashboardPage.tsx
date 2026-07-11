import 'sparkdesign/style'

import {
  Avatar,
  Badge,
  Button,
  Card,
  DropdownMenu,
  Input,
  Progress,
  Select,
  Separator,
  Table,
  Tabs,
  Tag,
} from 'sparkdesign'
import {
  Bell,
  ChevronDown,
  Download,
  Filter,
  MoreHorizontal,
  Plus,
  Search,
  Settings,
} from '@ali/qoder-icon'
import type { FC, ReactNode } from 'react'

/* -------------------------------------------------------------------------- */
/*  Types                                                                      */
/* -------------------------------------------------------------------------- */

type Kpi = {
  label: string
  value: string
  delta: number
  trend: 'up' | 'down'
  hint: string
}

type OrderRow = {
  id: string
  customer: { name: string; email: string; avatar: string }
  product: string
  amount: number
  status: 'paid' | 'pending' | 'failed' | 'refunded'
  channel: string
  createdAt: string
}

/* -------------------------------------------------------------------------- */
/*  Seed data                                                                  */
/* -------------------------------------------------------------------------- */

const KPI: Kpi[] = [
  { label: '总收入', value: '¥ 1,284,560', delta: 12.4, trend: 'up', hint: '较上月' },
  { label: '新增订单', value: '3,482', delta: 4.1, trend: 'up', hint: '较上月' },
  { label: '活跃用户', value: '28,901', delta: -2.3, trend: 'down', hint: '较上月' },
  { label: '转化率', value: '4.82%', delta: 0.6, trend: 'up', hint: '较上月' },
]

const ORDERS: OrderRow[] = [
  {
    id: '#A-10482',
    customer: { name: '陈思远', email: 'siyuan@example.com', avatar: 'CS' },
    product: 'Pro 年费订阅',
    amount: 1299,
    status: 'paid',
    channel: '官网',
    createdAt: '2026-07-11 09:24',
  },
  {
    id: '#A-10481',
    customer: { name: '李婉君', email: 'wanjun@example.com', avatar: 'LW' },
    product: '企业席位 × 5',
    amount: 4950,
    status: 'pending',
    channel: '销售',
    createdAt: '2026-07-11 08:51',
  },
  {
    id: '#A-10480',
    customer: { name: '王浩然', email: 'haoran@example.com', avatar: 'WH' },
    product: 'API 调用包',
    amount: 599,
    status: 'paid',
    channel: '官网',
    createdAt: '2026-07-11 08:12',
  },
  {
    id: '#A-10479',
    customer: { name: '张雨晨', email: 'yuchen@example.com', avatar: 'ZY' },
    product: 'Team 月费',
    amount: 299,
    status: 'failed',
    channel: 'App',
    createdAt: '2026-07-11 07:40',
  },
  {
    id: '#A-10478',
    customer: { name: '刘诗涵', email: 'shihan@example.com', avatar: 'LS' },
    product: 'Pro 月费订阅',
    amount: 129,
    status: 'refunded',
    channel: '官网',
    createdAt: '2026-07-10 22:16',
  },
]

const STATUS_VARIANT: Record<OrderRow['status'], 'success' | 'warning' | 'destructive' | 'neutral'> = {
  paid: 'success',
  pending: 'warning',
  failed: 'destructive',
  refunded: 'neutral',
}

const STATUS_LABEL: Record<OrderRow['status'], string> = {
  paid: '已支付',
  pending: '待确认',
  failed: '失败',
  refunded: '已退款',
}

/* -------------------------------------------------------------------------- */
/*  Small building blocks                                                      */
/* -------------------------------------------------------------------------- */

const SectionHeader: FC<{ title: string; action?: ReactNode }> = ({ title, action }) => (
  <div className="flex items-center justify-between">
    <h3 className="text-sm font-medium text-neutral-900">{title}</h3>
    {action}
  </div>
)

const SparkArea: FC<{ data: number[]; color: string }> = ({ data, color }) => {
  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const w = 120
  const h = 36
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w
      const y = h - ((v - min) / range) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible">
      <polyline fill="none" stroke={color} strokeWidth={1.5} points={pts} />
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/*  KPI card                                                                   */
/* -------------------------------------------------------------------------- */

const KpiCard: FC<{ kpi: Kpi }> = ({ kpi }) => {
  const isUp = kpi.trend === 'up'
  const spark = [4, 6, 5, 8, 7, 9, 11, 10, 13, 12, 15]
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-neutral-500">{kpi.label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-neutral-900">{kpi.value}</p>
        </div>
        <SparkArea data={spark} color={isUp ? '#16a34a' : '#dc2626'} />
      </div>
      <div className="mt-4 flex items-center gap-2 text-xs">
        <Badge variant={isUp ? 'success' : 'destructive'}>
          {isUp ? '▲' : '▼'} {Math.abs(kpi.delta)}%
        </Badge>
        <span className="text-neutral-500">{kpi.hint}</span>
      </div>
    </Card>
  )
}

/* -------------------------------------------------------------------------- */
/*  Sidebar + topbar                                                           */
/* -------------------------------------------------------------------------- */

const NAV = [
  { label: '概览', active: true },
  { label: '订单' },
  { label: '用户' },
  { label: '商品' },
  { label: '营销' },
  { label: '报表' },
]

const Sidebar: FC = () => (
  <aside className="hidden w-56 shrink-0 border-r border-neutral-200 bg-neutral-50/40 px-4 py-6 md:block">
    <div className="mb-8 flex items-center gap-2 px-2">
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-neutral-900 text-xs font-semibold text-white">
        S
      </div>
      <span className="text-sm font-semibold tracking-tight">Spark Admin</span>
    </div>
    <p className="mb-2 px-2 text-[11px] uppercase tracking-wider text-neutral-400">主导航</p>
    <nav className="flex flex-col gap-1">
      {NAV.map((n) => (
        <a
          key={n.label}
          className={`rounded-md px-3 py-2 text-sm transition-colors ${
            n.active
              ? 'bg-neutral-900 text-white'
              : 'text-neutral-600 hover:bg-neutral-100 hover:text-neutral-900'
          }`}
        >
          {n.label}
        </a>
      ))}
    </nav>
    <Separator className="my-6" />
    <p className="mb-2 px-2 text-[11px] uppercase tracking-wider text-neutral-400">设置</p>
    <a className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-neutral-600 hover:bg-neutral-100">
      <Settings className="h-4 w-4" /> 偏好
    </a>
  </aside>
)

const Topbar: FC = () => (
  <header className="flex h-14 items-center gap-4 border-b border-neutral-200 px-6">
    <div className="flex-1">
      <Input
        size="sm"
        placeholder="搜索订单、用户、商品…"
        icon={<Search className="h-4 w-4" />}
        className="max-w-md"
      />
    </div>
    <Button variant="ghost" size="icon" aria-label="通知">
      <Bell className="h-4 w-4" />
    </Button>
    <DropdownMenu>
      <DropdownMenu.Trigger asChild>
        <button className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-neutral-100">
          <Avatar fallback="XV" size="sm" />
          <span className="text-sm font-medium">Xavier</span>
          <ChevronDown className="h-4 w-4 text-neutral-500" />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content align="end">
        <DropdownMenu.Item>个人资料</DropdownMenu.Item>
        <DropdownMenu.Item>账户设置</DropdownMenu.Item>
        <DropdownMenu.Separator />
        <DropdownMenu.Item>退出登录</DropdownMenu.Item>
      </DropdownMenu.Content>
    </DropdownMenu>
  </header>
)

/* -------------------------------------------------------------------------- */
/*  Orders table                                                               */
/* -------------------------------------------------------------------------- */

const OrdersTable: FC = () => (
  <Card className="p-5">
    <SectionHeader
      title="最近订单"
      action={
        <div className="flex items-center gap-2">
          <Input size="sm" placeholder="筛选…" icon={<Search className="h-4 w-4" />} className="w-48" />
          <Select size="sm" defaultValue="all">
            <Select.Item value="all">全部状态</Select.Item>
            <Select.Item value="paid">已支付</Select.Item>
            <Select.Item value="pending">待确认</Select.Item>
            <Select.Item value="failed">失败</Select.Item>
          </Select>
          <Button variant="outline" size="sm">
            <Filter className="h-4 w-4" /> 筛选
          </Button>
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4" /> 导出
          </Button>
        </div>
      }
    />
    <div className="mt-4">
      <Table>
        <Table.Header>
          <Table.Row>
            <Table.Head>订单号</Table.Head>
            <Table.Head>客户</Table.Head>
            <Table.Head>商品</Table.Head>
            <Table.Head className="text-right">金额</Table.Head>
            <Table.Head>状态</Table.Head>
            <Table.Head>渠道</Table.Head>
            <Table.Head>时间</Table.Head>
            <Table.Head className="w-10" />
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {ORDERS.map((o) => (
            <Table.Row key={o.id}>
              <Table.Cell className="font-mono text-xs text-neutral-600">{o.id}</Table.Cell>
              <Table.Cell>
                <div className="flex items-center gap-3">
                  <Avatar fallback={o.customer.avatar} size="sm" />
                  <div className="leading-tight">
                    <p className="text-sm font-medium text-neutral-900">{o.customer.name}</p>
                    <p className="text-xs text-neutral-500">{o.customer.email}</p>
                  </div>
                </div>
              </Table.Cell>
              <Table.Cell className="text-sm text-neutral-700">{o.product}</Table.Cell>
              <Table.Cell className="text-right tabular-nums text-sm">
                ¥ {o.amount.toLocaleString()}
              </Table.Cell>
              <Table.Cell>
                <Tag variant={STATUS_VARIANT[o.status]}>{STATUS_LABEL[o.status]}</Tag>
              </Table.Cell>
              <Table.Cell className="text-sm text-neutral-600">{o.channel}</Table.Cell>
              <Table.Cell className="text-xs text-neutral-500">{o.createdAt}</Table.Cell>
              <Table.Cell>
                <Button variant="ghost" size="icon" aria-label="更多">
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table>
    </div>
  </Card>
)

/* -------------------------------------------------------------------------- */
/*  Side panels                                                                */
/* -------------------------------------------------------------------------- */

const ActivityFeed: FC = () => {
  const items = [
    { who: '系统', what: '完成了每日结算', when: '10 分钟前', tone: 'neutral' },
    { who: '陈思远', what: '升级到 Pro 年费', when: '32 分钟前', tone: 'success' },
    { who: '张雨晨', what: '支付失败（卡余额不足）', when: '1 小时前', tone: 'destructive' },
    { who: '李婉君', what: '提交了企业席位申请', when: '2 小时前', tone: 'warning' },
  ] as const
  return (
    <Card className="p-5">
      <SectionHeader title="实时动态" action={<Button variant="link" size="sm">查看全部</Button>} />
      <ol className="mt-4 space-y-4">
        {items.map((it, i) => (
          <li key={i} className="flex gap-3">
            <Avatar fallback={it.who[0]} size="sm" />
            <div className="flex-1 text-sm">
              <p>
                <span className="font-medium text-neutral-900">{it.who}</span>{' '}
                <span className="text-neutral-600">{it.what}</span>
              </p>
              <p className="text-xs text-neutral-500">{it.when}</p>
            </div>
          </li>
        ))}
      </ol>
    </Card>
  )
}

const StorageUsage: FC = () => (
  <Card className="p-5">
    <SectionHeader title="存储用量" />
    <div className="mt-4 space-y-4">
      {[
        { label: '数据库', value: 72, color: 'bg-neutral-900' },
        { label: '对象存储', value: 48, color: 'bg-neutral-700' },
        { label: '日志', value: 86, color: 'bg-orange-500' },
      ].map((b) => (
        <div key={b.label}>
          <div className="mb-1 flex justify-between text-xs text-neutral-600">
            <span>{b.label}</span>
            <span>{b.value}%</span>
          </div>
          <Progress value={b.value} className={b.color} />
        </div>
      ))}
    </div>
    <Button variant="outline" size="sm" className="mt-5 w-full">
      管理用量
    </Button>
  </Card>
)

/* -------------------------------------------------------------------------- */
/*  Page                                                                       */
/* -------------------------------------------------------------------------- */

const DashboardPage: FC = () => (
  <div className="flex min-h-screen bg-white text-neutral-900">
    <Sidebar />
    <div className="flex min-w-0 flex-1 flex-col">
      <Topbar />

      <main className="flex-1 overflow-auto px-6 py-6">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">概览</h1>
            <p className="mt-1 text-sm text-neutral-500">
              欢迎回来，Xavier — 这是今日的运营快照。
            </p>
          </div>
          <div className="flex gap-2">
            <Tabs defaultValue="7d">
              <Tabs.List>
                <Tabs.Trigger value="24h">24 小时</Tabs.Trigger>
                <Tabs.Trigger value="7d">7 天</Tabs.Trigger>
                <Tabs.Trigger value="30d">30 天</Tabs.Trigger>
              </Tabs.List>
            </Tabs>
            <Button>
              <Plus className="h-4 w-4" /> 新建订单
            </Button>
          </div>
        </div>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {KPI.map((k) => (
            <KpiCard key={k.label} kpi={k} />
          ))}
        </section>

        <section className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <OrdersTable />
          </div>
          <div className="space-y-4">
            <ActivityFeed />
            <StorageUsage />
          </div>
        </section>
      </main>
    </div>
  </div>
)

export default DashboardPage
