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
