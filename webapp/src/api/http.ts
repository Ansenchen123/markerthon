export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function readErrorMessage(response: Response) {
  const fallbackMessages: Record<number, string> = {
    401: 'Email 或密碼錯誤',
    403: '沒有權限使用這個功能',
    404: 'QR Code 無法辨識',
    409: 'Email 已被使用，或這張 QR Code 已全數歸還',
    422: '輸入格式不正確',
  };
  const localizedMessages: Record<string, string> = {
    'Invalid email or password': 'Email 或密碼錯誤',
    'QR value is not recognized': 'QR Code 無法辨識',
    'This QR value has already been returned': '這張 QR Code 已全數歸還',
  };

  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;

    if (typeof detail === 'string') {
      return localizedMessages[detail] ?? detail;
    }

    if (Array.isArray(detail) && detail.length > 0) {
      return fallbackMessages[response.status] ?? detail[0]?.msg ?? '';
    }
  }

  const message = await response.text().catch(() => '');
  return (
    localizedMessages[message] ||
    message ||
    fallbackMessages[response.status] ||
    `API 請求失敗：${response.status}`
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
