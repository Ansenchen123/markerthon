export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
};

async function readErrorMessage(response: Response) {
  const fallbackMessages: Record<number, string> = {
    401: 'Email or password is incorrect',
    403: 'You do not have permission to access this API',
    404: 'QR code was not found',
    409: 'Email already exists or this QR code has already been returned',
    422: 'Invalid input format',
  };

  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;

    if (typeof detail === 'string') {
      return detail;
    }

    if (Array.isArray(detail) && detail.length > 0) {
      return fallbackMessages[response.status] ?? detail[0]?.msg ?? '';
    }
  }

  const message = await response.text().catch(() => '');
  return message || fallbackMessages[response.status] || `API request failed: ${response.status}`;
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
    throw new Error(await readErrorMessage(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
