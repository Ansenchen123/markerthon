export type LoginResponse = {
  accessToken: string;
  tokenType: string;
  user: {
    id: number;
    userEmail: string;
  };
};

export type MonthlyUsage = {
  month: string;
  from?: string;
  to?: string;
  issuedCount: number;
  returnedCount: number;
  remainingCount: number;
  recoveryRate: number;
  activeInvoiceCount: number;
  partialReturnedInvoiceCount: number;
  returnedInvoiceCount: number;
  overdueCount: number;
  abnormalCount: number;
  daily: Array<{
    statDate: string;
    issuedCount: number;
    returnedCount: number;
  }>;
};

export type EnterpriseCounts = {
  month: string;
  from?: string;
  to?: string;
  monthJoinedCount: number;
  totalEnterpriseCount: number;
};

export type RegionDistribution = {
  totalEnterpriseCount: number;
  regions: Array<{
    region: string;
    enterpriseCount: number;
  }>;
};

export type TopStores = {
  month: string;
  from?: string;
  to?: string;
  rankings: Array<{
    rank: number;
    storeId: number;
    storeCode: string;
    storeName: string;
    region: string;
    issuedCount: number;
    returnedCount: number;
    remainingCount: number;
    recoveryRate: number;
  }>;
};

export type StoreDetail = {
  month: string;
  from?: string;
  to?: string;
  store: {
    id: number;
    code: string;
    name: string;
    region: string;
    createdAt: string;
  };
  issuedCount: number;
  returnedCount: number;
  recoveredCount: number;
  remainingCount: number;
  recoveryRate: number;
  cupIssuedCount: number;
  cupReturnedCount: number;
  mealBoxIssuedCount: number;
  mealBoxReturnedCount: number;
  overdueCount: number;
  abnormalCount: number;
  crossStoreRecoveredCount: number;
  lastActivityAt: string;
};

export type DashboardData = {
  monthlyUsage: MonthlyUsage;
  enterpriseCounts: EnterpriseCounts;
  regionDistribution: RegionDistribution;
  topStores: TopStores;
  storeDetail: StoreDetail | null;
};

export type DashboardQuery = {
  year: number;
  month: number;
  storeId: string;
};

const API_BASE_URL = 'http://127.0.0.1:8000';
const TOKEN_KEY = 'governmentAccessToken';
const GOVERNMENT_LOGIN = {
  userEmail: 'gov.admin@example.com',
  password: 'password123',
};

let accessToken = localStorage.getItem(TOKEN_KEY) ?? '';

function buildQuery(query: Omit<DashboardQuery, 'storeId'>, limit?: number) {
  const params = new URLSearchParams({
    year: String(query.year),
    month: String(query.month),
  });

  if (limit) {
    params.set('limit', String(limit));
  }

  return params.toString();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    throw new Error(await response.text().catch(() => `API error: ${response.status}`));
  }

  return response.json() as Promise<T>;
}

export async function loginGovernment() {
  const data = await request<LoginResponse>('/government/auth/login', {
    method: 'POST',
    body: JSON.stringify(GOVERNMENT_LOGIN),
  });

  accessToken = data.accessToken;
  localStorage.setItem(TOKEN_KEY, accessToken);
  return data;
}

async function authenticatedRequest<T>(path: string): Promise<T> {
  if (!accessToken) {
    await loginGovernment();
  }

  try {
    return await request<T>(path);
  } catch (error) {
    if (error instanceof Error && error.message.includes('401')) {
      await loginGovernment();
      return request<T>(path);
    }

    throw error;
  }
}

export async function getMonthlyUsage(query: Omit<DashboardQuery, 'storeId'>) {
  return authenticatedRequest<MonthlyUsage>(`/government/web/monthly-usage?${buildQuery(query)}`);
}

export async function getEnterpriseCounts(query: Omit<DashboardQuery, 'storeId'>) {
  return authenticatedRequest<EnterpriseCounts>(`/government/web/enterprise-counts?${buildQuery(query)}`);
}

export async function getRegionDistribution() {
  return authenticatedRequest<RegionDistribution>('/government/web/region-distribution');
}

export async function getTopStores(query: Omit<DashboardQuery, 'storeId'>, limit = 10) {
  return authenticatedRequest<TopStores>(`/government/web/top-stores?${buildQuery(query, limit)}`);
}

export async function getStoreDetail(query: DashboardQuery) {
  const storeId = Number(query.storeId);
  if (!Number.isFinite(storeId) || storeId <= 0) {
    return null;
  }

  return authenticatedRequest<StoreDetail>(
    `/government/web/stores/${storeId}?${buildQuery({ year: query.year, month: query.month })}`,
  ).catch(() => null);
}

export async function getDashboardData(query: DashboardQuery): Promise<DashboardData> {
  const baseQuery = { year: query.year, month: query.month };
  const [monthlyUsage, enterpriseCounts, regionDistribution, topStores] = await Promise.all([
    getMonthlyUsage(baseQuery),
    getEnterpriseCounts(baseQuery),
    getRegionDistribution(),
    getTopStores(baseQuery, 10),
  ]);

  const storeDetail = await getStoreDetail(query);

  return {
    monthlyUsage,
    enterpriseCounts,
    regionDistribution,
    topStores,
    storeDetail,
  };
}
