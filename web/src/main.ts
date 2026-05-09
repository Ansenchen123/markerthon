import Chart from 'chart.js/auto';
import {
  getDashboardData,
  loginGovernment,
  type DashboardData,
  type EnterpriseCounts,
  type MonthlyUsage,
  type RegionDistribution,
  type StoreDetail,
  type TopStores,
} from './api';

const today = new Date();

let selectedYear = today.getFullYear();
let selectedMonth = today.getMonth() + 1;
let selectedStoreName = '青山茶飲';
let usageTrendChart: Chart | null = null;
let enterpriseChart: Chart | null = null;
let regionChart: Chart | null = null;

function formatNumber(value: number | undefined) {
  return (value ?? 0).toLocaleString('zh-TW');
}

function formatPercent(value: number | undefined, digits = 2) {
  return `${((value ?? 0) * 100).toFixed(digits)}%`;
}

function formatMonth(month: string) {
  return month.replace('-', '/');
}

function icon(name: string) {
  const paths: Record<string, string> = {
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1"/><rect x="13" y="4" width="7" height="7" rx="1"/><rect x="4" y="13" width="7" height="7" rx="1"/><rect x="13" y="13" width="7" height="7" rx="1"/>',
    pin: '<path d="M12 21s7-5.3 7-11a7 7 0 0 0-14 0c0 5.7 7 11 7 11Z"/><circle cx="12" cy="10" r="2.2"/>',
    store: '<path d="M4 10h16l-1.5-5h-13L4 10Z"/><path d="M6 10v9h12v-9"/><path d="M9 19v-5h6v5"/>',
    chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 4-4 3 3 5-7"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7"/><path d="M10 21h4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 10v6M12 7h.01"/>',
    cup: '<path d="M8 8h8l-.7 12H8.7L8 8Z"/><path d="M7 4h10"/><path d="M9 4l1 4M15 4l-1 4"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/>',
  };

  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] ?? ''}</svg>`;
}

function renderSidebar() {
  return `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><span></span></div>
        <div>
          <strong>環保餐具使用管理平台</strong>
          <small>政府管理後台</small>
        </div>
      </div>
      <nav class="side-nav">
        <button class="nav-item is-active" type="button">${icon('grid')}<span>總覽儀表板</span></button>
        <button class="nav-item" type="button">${icon('chart')}<span>每月使用情況</span></button>
        <button class="nav-item" type="button">${icon('users')}<span>企業加入數量</span></button>
        <button class="nav-item" type="button">${icon('pin')}<span>地區數量分布</span></button>
        <button class="nav-item" type="button">${icon('cup')}<span>Top 10 商家</span></button>
        <button class="nav-item" type="button">${icon('store')}<span>特定店家查詢</span></button>
      </nav>
      <div class="sidebar-footer">
        <div>© 2024 環境部 資源循環署</div>
        <div>All rights reserved.</div>
      </div>
    </aside>
  `;
}

function renderTopbar(month: string) {
  const period = `${formatMonth(month)}/01 ~ ${formatMonth(month)}/31`;

  return `
    <header class="topbar">
      <div class="title-row">
        <button class="ghost-button" type="button" aria-label="展開選單">${icon('menu')}</button>
        <h1>總覽儀表板</h1>
        <span class="status-dot" aria-hidden="true"></span>
      </div>
      <form class="toolbar" id="periodForm">
        <label class="filter date-filter">
          ${icon('calendar')}
          <input name="year" type="number" value="${selectedYear}" min="2020" max="2100" aria-label="年份" />
          <span>/</span>
          <input name="month" type="number" value="${selectedMonth}" min="1" max="12" aria-label="月份" />
        </label>
        <button class="filter" type="submit"><span>${period}</span></button>
        <button class="filter" type="button">${icon('pin')}<span>全台灣</span>${icon('chevron')}</button>
        <button class="ghost-button has-badge" type="button" aria-label="通知">${icon('bell')}</button>
        <button class="profile" type="button"><span>政府</span>${icon('chevron')}</button>
      </form>
    </header>
  `;
}

function renderMonthlyUsageCard(data: MonthlyUsage) {
  return `
    <section class="panel chart-panel monthly-panel">
      <div class="panel-head">
        <h2>整體借出 / 收回情形 ${icon('info')}</h2>
        <div class="api-pill">year=${selectedYear} month=${selectedMonth}</div>
      </div>
      <div class="chart-legend">
        <span class="current"></span>借出 issuedCount
        <span class="previous"></span>回收 returnedCount
      </div>
      <div class="chart-box"><canvas id="usageTrendChart"></canvas></div>
      <div class="metric-row">
        <div><span>借出總數</span><strong>${formatNumber(data.issuedCount)}</strong></div>
        <div><span>回收總數</span><strong>${formatNumber(data.returnedCount)}</strong></div>
        <div><span>未歸還</span><strong>${formatNumber(data.remainingCount)}</strong></div>
        <div><span>回收率</span><strong class="up">${formatPercent(data.recoveryRate)}</strong></div>
        <div><span>活躍租借單</span><strong>${formatNumber(data.activeInvoiceCount)}</strong></div>
        <div><span>部分歸還</span><strong>${formatNumber(data.partialReturnedInvoiceCount)}</strong></div>
        <div><span>已歸還單</span><strong>${formatNumber(data.returnedInvoiceCount)}</strong></div>
        <div><span>逾期 / 異常</span><strong>${formatNumber(data.overdueCount)} / ${formatNumber(data.abnormalCount)}</strong></div>
      </div>
    </section>
  `;
}

function renderEnterpriseCard(data: EnterpriseCounts) {
  return `
    <section class="panel enterprise-panel">
      <div class="panel-head">
        <h2>企業加入統計 ${icon('info')}</h2>
        <div class="api-pill">企業統計</div>
      </div>
      <div class="enterprise-layout">
        <div class="chart-small"><canvas id="enterpriseChart"></canvas></div>
        <div class="stat-stack">
          <div><span>本月新增企業</span><strong>${formatNumber(data.monthJoinedCount)}</strong></div>
          <div><span>累計企業總數</span><strong>${formatNumber(data.totalEnterpriseCount)}</strong></div>
          <div><span>資料月份</span><strong>${data.month}</strong></div>
        </div>
      </div>
    </section>
  `;
}

function renderRegionCard(data: RegionDistribution) {
  return `
    <section class="panel region-panel">
      <div class="panel-head">
        <h2>地區企業數量分布 ${icon('info')}</h2>
        <div class="api-pill">region</div>
      </div>
      <div class="region-layout">
        <div class="chart-small"><canvas id="regionChart"></canvas></div>
        <table>
          <thead>
            <tr><th>地區</th><th>企業數</th><th>占比</th></tr>
          </thead>
          <tbody>
            ${data.regions.map(region => `
              <tr>
                <td>${region.region}</td>
                <td>${formatNumber(region.enterpriseCount)}</td>
                <td>${formatPercent(region.enterpriseCount / Math.max(data.totalEnterpriseCount, 1))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

function renderTopStoresCard(data: TopStores) {
  return `
    <section class="panel table-panel">
      <div class="panel-head">
        <h2>循環容器使用 Top 10 商家 ${icon('info')}</h2>
        <div class="api-pill">limit=10 all categories</div>
      </div>
      <table>
        <thead>
          <tr><th>排名</th><th>商家名稱</th><th>地區</th><th>借出</th><th>回收</th><th>未歸還</th><th>回收率</th></tr>
        </thead>
        <tbody>
          ${data.rankings.map(store => `
            <tr>
              <td>${store.rank}</td>
              <td>${store.storeName}</td>
              <td>${store.region}</td>
              <td>${formatNumber(store.issuedCount)}</td>
              <td>${formatNumber(store.returnedCount)}</td>
              <td>${formatNumber(store.remainingCount)}</td>
              <td class="up">${formatPercent(store.recoveryRate)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </section>
  `;
}

function renderStoreCard(data: StoreDetail | null, stores: TopStores) {
  return `
    <section class="panel search-panel">
      <div class="panel-head">
        <h2>特定店家使用明細 ${icon('info')}</h2>
        <div class="api-pill">storeName=${selectedStoreName || '-'}</div>
      </div>
      <form class="search-row" id="storeSearch">
        <input name="storeName" type="text" value="${selectedStoreName}" placeholder="輸入店家名稱" />
        <button type="submit">查詢</button>
      </form>
      <div class="chips">
        ${stores.rankings.slice(0, 5).map(store => `<button type="button" data-store-name="${store.storeName}">${store.storeName}</button>`).join('')}
      </div>
      ${data ? `
        <div class="store-result">
          <div class="store-icon">${icon('cup')}</div>
          <div>
            <strong>${data.store.name}</strong>
            <p>${data.store.region}｜代碼 ${data.store.code}｜最後活動 ${data.lastActivityAt ? new Date(data.lastActivityAt).toLocaleString('zh-TW') : '-'}</p>
            <dl>
              <div><dt>借出</dt><dd>${formatNumber(data.issuedCount)}</dd></div>
              <div><dt>回收</dt><dd>${formatNumber(data.returnedCount)}</dd></div>
              <div><dt>未歸還</dt><dd>${formatNumber(data.remainingCount)}</dd></div>
              <div><dt>回收率</dt><dd>${formatPercent(data.recoveryRate)}</dd></div>
              <div><dt>杯借 / 還</dt><dd>${formatNumber(data.cupIssuedCount)} / ${formatNumber(data.cupReturnedCount)}</dd></div>
              <div><dt>餐盒借 / 還</dt><dd>${formatNumber(data.mealBoxIssuedCount)} / ${formatNumber(data.mealBoxReturnedCount)}</dd></div>
              <div><dt>跨店回收</dt><dd>${formatNumber(data.crossStoreRecoveredCount)}</dd></div>
              <div><dt>逾期 / 異常</dt><dd>${formatNumber(data.overdueCount)} / ${formatNumber(data.abnormalCount)}</dd></div>
            </dl>
          </div>
        </div>
      ` : `
        <div class="store-result empty">
          <div class="store-icon">${icon('store')}</div>
          <div>
            <strong>尚未取得店家資料</strong>
            <p>請輸入有效的店家名稱，系統會查詢該商家的使用狀況。</p>
          </div>
        </div>
      `}
    </section>
  `;
}

function initCharts(data: DashboardData) {
  usageTrendChart?.destroy();
  enterpriseChart?.destroy();
  regionChart?.destroy();

  const trendCanvas = document.querySelector<HTMLCanvasElement>('#usageTrendChart');
  if (trendCanvas) {
    usageTrendChart = new Chart(trendCanvas, {
      type: 'line',
      data: {
        labels: data.monthlyUsage.daily.map(day => day.statDate.slice(5).replace('-', '/')),
        datasets: [
          {
            label: '借出',
            data: data.monthlyUsage.daily.map(day => day.issuedCount),
            borderColor: '#10987b',
            backgroundColor: '#10987b',
            pointRadius: 2.5,
            borderWidth: 3,
            tension: 0.28,
          },
          {
            label: '回收',
            data: data.monthlyUsage.daily.map(day => day.returnedCount),
            borderColor: '#9aaad0',
            backgroundColor: '#9aaad0',
            borderDash: [6, 6],
            pointRadius: 2,
            borderWidth: 2.5,
            tension: 0.28,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#e6ecee' }, ticks: { color: '#6b7d82', maxTicksLimit: 8 } },
          y: { beginAtZero: true, grid: { color: '#e6ecee' }, ticks: { color: '#6b7d82' } },
        },
      },
    });
  }

  const enterpriseCanvas = document.querySelector<HTMLCanvasElement>('#enterpriseChart');
  if (enterpriseCanvas) {
    const joined = data.enterpriseCounts.monthJoinedCount;
    const existing = Math.max(data.enterpriseCounts.totalEnterpriseCount - joined, 0);

    enterpriseChart = new Chart(enterpriseCanvas, {
      type: 'doughnut',
      data: {
        labels: ['本月新增', '既有企業'],
        datasets: [{ data: [joined, existing], backgroundColor: ['#10987b', '#cfe4df'], borderWidth: 0 }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, color: '#53676b' } } },
      },
    });
  }

  const regionCanvas = document.querySelector<HTMLCanvasElement>('#regionChart');
  if (regionCanvas) {
    regionChart = new Chart(regionCanvas, {
      type: 'bar',
      data: {
        labels: data.regionDistribution.regions.map(region => region.region),
        datasets: [
          {
            label: '企業數',
            data: data.regionDistribution.regions.map(region => region.enterpriseCount),
            backgroundColor: '#62c0a7',
            borderRadius: 4,
          },
        ],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, grid: { color: '#e6ecee' }, ticks: { color: '#6b7d82' } },
          y: { grid: { display: false }, ticks: { color: '#53676b' } },
        },
      },
    });
  }
}

async function renderDashboard() {
  const app = document.querySelector<HTMLDivElement>('#app');
  if (!app) return;

  app.innerHTML = `
    ${renderSidebar()}
    <main class="dashboard">
      <div class="dashboard-loading">登入並載入 API 資料中...</div>
    </main>
  `;

  try {
    await loginGovernment();
    const data = await getDashboardData({
      year: selectedYear,
      month: selectedMonth,
      storeName: selectedStoreName,
    });
    const dashboard = document.querySelector<HTMLElement>('.dashboard');
    if (!dashboard) return;

    dashboard.innerHTML = `
      ${renderTopbar(data.monthlyUsage.month)}
      <div class="content api-content">
        <div class="grid api-grid">
          ${renderMonthlyUsageCard(data.monthlyUsage)}
          ${renderEnterpriseCard(data.enterpriseCounts)}
          ${renderRegionCard(data.regionDistribution)}
          ${renderTopStoresCard(data.topStores)}
          ${renderStoreCard(data.storeDetail, data.topStores)}
        </div>
        <footer>依 API_USAGE.md 串接五個政府端 Web API；系統會自動以 gov.admin@example.com 登入。</footer>
      </div>
    `;

    initCharts(data);
    bindEvents();
  } catch (error) {
    console.error(error);
    const dashboard = document.querySelector<HTMLElement>('.dashboard');
    if (dashboard) {
      dashboard.innerHTML = `
        <div class="error-state">
          <h1>API 資料載入失敗</h1>
          <p>${error instanceof Error ? error.message : '請確認後端服務是否已啟動。'}</p>
          <button type="button" id="retryButton">重新載入</button>
        </div>
      `;
      document.getElementById('retryButton')?.addEventListener('click', renderDashboard);
    }
  }
}

function bindEvents() {
  document.getElementById('periodForm')?.addEventListener('submit', event => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget as HTMLFormElement);
    selectedYear = Number(formData.get('year')) || selectedYear;
    selectedMonth = Number(formData.get('month')) || selectedMonth;
    renderDashboard();
  });

  document.getElementById('storeSearch')?.addEventListener('submit', event => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget as HTMLFormElement);
    selectedStoreName = String(formData.get('storeName') || '').trim();
    renderDashboard();
  });

  document.querySelectorAll<HTMLButtonElement>('[data-store-name]').forEach(button => {
    button.addEventListener('click', () => {
      selectedStoreName = button.dataset.storeName ?? '';
      renderDashboard();
    });
  });
}

void renderDashboard();
