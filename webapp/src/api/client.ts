import { apiRequest } from './http';

export type LoginRequest = {
  userEmail: string;
  password: string;
};

export type LoginResponse = {
  accessToken: string;
  tokenType: 'bearer' | string;
  store: {
    id: number;
    code: string;
    name: string;
  };
};

export type RegisterRequest = {
  userEmail: string;
  password: string;
  storeName: string;
};

export type GovernmentAuthRequest = {
  userEmail: string;
  password: string;
};

export type GovernmentAuthResponse = {
  accessToken: string;
  tokenType: 'bearer' | string;
  user: {
    id: number;
    userEmail: string;
  };
};

export type GovernmentMonthParams = {
  year?: number;
  month?: number;
};

export type GovernmentMonthlyUsageResponse = {
  month: string;
  from: string;
  to: string;
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

export type GovernmentEnterpriseCountsResponse = {
  month: string;
  from: string;
  to: string;
  monthJoinedCount: number;
  totalEnterpriseCount: number;
};

export type GovernmentRegionDistributionResponse = {
  totalEnterpriseCount: number;
  regions: Array<{
    region: string;
    enterpriseCount: number;
  }>;
};

export type GovernmentTopCupStoresParams = GovernmentMonthParams & {
  limit?: number;
};

export type GovernmentTopCupStoresResponse = {
  month: string;
  from: string;
  to: string;
  category: 'cup';
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

export type GovernmentStoreDetailResponse = {
  month: string;
  from: string;
  to: string;
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

export type RentalRequest = {
  qrCode: string;
  cupCount: number;
  invoiceCode: string;
};

export type MerchantCategory = 'cup' | 'meal_box';

export type MerchantQrCodeRequest = {
  invoiceCode: string;
  category: MerchantCategory;
  count: number;
};

export type MerchantQrCodeResponse = {
  loanId: number;
  qrValue: string;
  invoiceCode: string;
  storeCode: string;
  category: MerchantCategory;
  addedCount: number;
  totalCount: number;
  returnedCount: number;
  remainingCount: number;
  issuedAt: string;
  dueAt: string;
};

export type MerchantReturnScanRequest = {
  qrValue: string;
};

export type MerchantReturnScanResponse = {
  accepted: boolean;
  loanId: number;
  status: 'active' | 'partial_returned' | 'returned' | string;
  category: MerchantCategory;
  invoiceCode: string;
  issuedStoreId: number;
  returnedStoreId: number;
  count: number;
  totalCount: number;
  returnedCount: number;
  remainingCount: number;
  refundReason: string;
  isExpired: boolean;
  isAbnormal: boolean;
  dueAt: string;
  returnedAt: string;
};

export type MerchantStatsParams = {
  storeId: number;
  from: string;
  to: string;
};

export type MerchantStatsCategoryCount = {
  category: MerchantCategory;
  count: number;
};

export type MerchantSoldStatsRow = {
  statDate: string;
  totalCount: number;
  categoryCounts: MerchantStatsCategoryCount[];
};

export type MerchantRecoveredStatsRow = MerchantSoldStatsRow & {
  normalCount: number;
  expiredCount: number;
  abnormalCount: number;
  crossStoreCount: number;
};

export type MerchantSoldStatsResponse = {
  storeId: number;
  from: string;
  to: string;
  rows: MerchantSoldStatsRow[];
};

export type MerchantRecoveredStatsResponse = {
  storeId: number;
  from: string;
  to: string;
  rows: MerchantRecoveredStatsRow[];
};

function buildStatsPath(path: string, params: MerchantStatsParams) {
  const search = new URLSearchParams({
    storeId: String(params.storeId),
    from: params.from,
    to: params.to,
  });

  return `${path}?${search.toString()}`;
}

function buildGovernmentMonthPath(path: string, params: GovernmentMonthParams = {}) {
  const search = new URLSearchParams();

  if (params.year !== undefined) {
    search.set('year', String(params.year));
  }

  if (params.month !== undefined) {
    search.set('month', String(params.month));
  }

  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

function buildGovernmentTopStoresPath(
  path: string,
  params: GovernmentTopCupStoresParams = {},
) {
  const search = new URLSearchParams();

  if (params.year !== undefined) {
    search.set('year', String(params.year));
  }

  if (params.month !== undefined) {
    search.set('month', String(params.month));
  }

  if (params.limit !== undefined) {
    search.set('limit', String(params.limit));
  }

  const query = search.toString();
  return query ? `${path}?${query}` : path;
}

export type ApiUser = {
  id: string;
  name: string;
  email: string;
  phone: string;
};

export type ApiMerchant = {
  id: string;
  name: string;
  address: string;
};

export const api = {
  auth: {
    login: (body: LoginRequest) =>
      apiRequest<LoginResponse>('/auth/login', {
        method: 'POST',
        body,
      }),
    register: (body: RegisterRequest) =>
      apiRequest<LoginResponse>('/auth/register', {
        method: 'POST',
        body,
      }),
    me: () => apiRequest<{ user: ApiUser; merchant?: ApiMerchant }>('/api/auth/me'),
  },
  government: {
    auth: {
      login: (body: GovernmentAuthRequest) =>
        apiRequest<GovernmentAuthResponse>('/government/auth/login', {
          method: 'POST',
          body,
        }),
      register: (body: GovernmentAuthRequest) =>
        apiRequest<GovernmentAuthResponse>('/government/auth/register', {
          method: 'POST',
          body,
        }),
    },
    web: {
      monthlyUsage: (accessToken: string, params?: GovernmentMonthParams) =>
        apiRequest<GovernmentMonthlyUsageResponse>(
          buildGovernmentMonthPath('/government/web/monthly-usage', params),
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        ),
      enterpriseCounts: (accessToken: string, params?: GovernmentMonthParams) =>
        apiRequest<GovernmentEnterpriseCountsResponse>(
          buildGovernmentMonthPath('/government/web/enterprise-counts', params),
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        ),
      regionDistribution: (accessToken: string) =>
        apiRequest<GovernmentRegionDistributionResponse>('/government/web/region-distribution', {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        }),
      topCupStores: (accessToken: string, params?: GovernmentTopCupStoresParams) =>
        apiRequest<GovernmentTopCupStoresResponse>(
          buildGovernmentTopStoresPath('/government/web/top-cup-stores', params),
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        ),
      storeDetail: (storeId: number, accessToken: string, params?: GovernmentMonthParams) =>
        apiRequest<GovernmentStoreDetailResponse>(
          buildGovernmentMonthPath(`/government/web/stores/${storeId}`, params),
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          },
        ),
    },
  },
  rentals: {
    create: (body: RentalRequest) =>
      apiRequest<{ id?: string }>('/api/rentals', {
        method: 'POST',
        body,
      }),
    list: () => apiRequest<unknown[]>('/api/rentals'),
  },
  merchant: {
    createQrCode: (body: MerchantQrCodeRequest, accessToken: string) =>
      apiRequest<MerchantQrCodeResponse>('/merchant/qr-codes', {
        method: 'POST',
        body,
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }),
    scanReturn: (body: MerchantReturnScanRequest, accessToken: string) =>
      apiRequest<MerchantReturnScanResponse>('/merchant/returns/scan', {
        method: 'POST',
        body,
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }),
  },
  stats: {
    sold: (params: MerchantStatsParams, accessToken: string) =>
      apiRequest<MerchantSoldStatsResponse>(buildStatsPath('/merchant/stats/sold', params), {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      }),
    recovered: (params: MerchantStatsParams, accessToken: string) =>
      apiRequest<MerchantRecoveredStatsResponse>(
        buildStatsPath('/merchant/stats/recovered', params),
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        },
      ),
    summary: () => apiRequest<unknown>('/api/stats/summary'),
  },
};
