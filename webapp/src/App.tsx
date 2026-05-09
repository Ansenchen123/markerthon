import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import globeImage from '../assets/global.png';
import spoonImage from '../assets/spoon.png';
import {
  api,
  type LoginResponse,
  type MerchantCategory,
  type MerchantQrCodeResponse,
  type MerchantRecoveredStatsResponse,
  type MerchantSoldStatsResponse,
} from './api/client';

type ScanView = 'home' | 'reader' | 'storeQr';
type ActivePage = 'home' | 'records' | 'stats' | 'profile';
type AuthPage = 'login' | 'register';
type RecordType = '借出' | '回收';

type StoreInfo = {
  id: number;
  code: string;
  name: string;
  address: string;
  item: string;
};

type CreatedQrCode = MerchantQrCodeResponse & {
  imageUrl: string;
};

type StatsState = {
  sold: MerchantSoldStatsResponse | null;
  recovered: MerchantRecoveredStatsResponse | null;
  isLoading: boolean;
  error: string;
};

type DashboardStats = {
  soldTotal: number;
  recoveredTotal: number;
  activeTotal: number;
  dailyRows: Array<{
    day: string;
    date: string;
    loaned: number;
    returned: number;
    cupSold: number;
    mealBoxSold: number;
    cupRecovered: number;
    mealBoxRecovered: number;
  }>;
};

type AuthSession = {
  accessToken: string;
  tokenType: string;
  store: LoginResponse['store'];
};

const AUTH_COOKIE_NAME = 'green_dining_auth';
const AUTH_COOKIE_MAX_AGE = 60 * 60 * 24 * 30;

const fallbackStore: StoreInfo = {
  id: 0,
  code: 'ECO-CUP-028',
  name: '綠森咖啡 台北信義店',
  address: '台北市信義區松仁路 88 號',
  item: '循環杯',
};

const tabs = [
  { id: 'home', icon: 'fa-solid fa-house', label: '首頁' },
  { id: 'records', icon: 'fa-solid fa-clipboard-list', label: '紀錄' },
  { id: 'stats', icon: 'fa-solid fa-chart-pie', label: '統計' },
  { id: 'profile', icon: 'fa-solid fa-user', label: '用戶' },
] satisfies Array<{ id: ActivePage; icon: string; label: string }>;

function createInvoiceCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  const randomText = Array.from({ length: 10 }, () => {
    const index = Math.floor(Math.random() * alphabet.length);
    return alphabet[index];
  }).join('');
  const timeText = Date.now().toString(36).toUpperCase();

  return `INV-${timeText}-${randomText}`;
}

function readCookie(name: string) {
  const target = `${name}=`;
  const cookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(target));

  return cookie ? cookie.slice(target.length) : '';
}

function saveAuthCookie(session: AuthSession) {
  document.cookie = `${AUTH_COOKIE_NAME}=${encodeURIComponent(JSON.stringify(session))}; path=/; max-age=${AUTH_COOKIE_MAX_AGE}; SameSite=Lax`;
}

function readAuthCookie(): AuthSession | null {
  const value = readCookie(AUTH_COOKIE_NAME);

  if (!value) {
    return null;
  }

  try {
    return JSON.parse(decodeURIComponent(value)) as AuthSession;
  } catch {
    return null;
  }
}

function clearAuthCookie() {
  document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`;
}

function formatDateForApi(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

function getDefaultDateRange() {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 4);

  return {
    from: formatDateForApi(from),
    to: formatDateForApi(to),
  };
}

function getCategoryCount(
  categoryCounts: Array<{ category: MerchantCategory; count: number }>,
  category: MerchantCategory,
) {
  return categoryCounts.find((item) => item.category === category)?.count ?? 0;
}

function createDashboardStats(
  sold: MerchantSoldStatsResponse | null,
  recovered: MerchantRecoveredStatsResponse | null,
): DashboardStats {
  const soldRows = sold?.rows ?? [];
  const recoveredRows = recovered?.rows ?? [];
  const soldTotal = soldRows.reduce((total, row) => total + row.totalCount, 0);
  const recoveredTotal = recoveredRows.reduce((total, row) => total + row.totalCount, 0);
  const recoveredByDate = new Map(recoveredRows.map((row) => [row.statDate, row]));

  return {
    soldTotal,
    recoveredTotal,
    activeTotal: sold?.remainingCount ?? 0,
    dailyRows: soldRows.map((soldRow) => {
      const recoveredRow = recoveredByDate.get(soldRow.statDate);

      return {
        day: soldRow.statDate.slice(5).replace('-', '/'),
        date: soldRow.statDate,
        loaned: soldRow.totalCount,
        returned: recoveredRow?.totalCount ?? 0,
        cupSold: getCategoryCount(soldRow.categoryCounts, 'cup'),
        mealBoxSold: getCategoryCount(soldRow.categoryCounts, 'meal_box'),
        cupRecovered: getCategoryCount(recoveredRow?.categoryCounts ?? [], 'cup'),
        mealBoxRecovered: getCategoryCount(recoveredRow?.categoryCounts ?? [], 'meal_box'),
      };
    }),
  };
}

export function App() {
  const [activePage, setActivePage] = useState<ActivePage>('home');
  const [authPage, setAuthPage] = useState<AuthPage>('login');
  const [scanView, setScanView] = useState<ScanView>('home');
  const [store, setStore] = useState<StoreInfo>(fallbackStore);
  const [accessToken, setAccessToken] = useState('');
  const [tokenType, setTokenType] = useState('');
  const [qrCodeValue, setQrCodeValue] = useState(fallbackStore.code);
  const [cupCount, setCupCount] = useState(0);
  const [mealBoxCount, setMealBoxCount] = useState(0);
  const [invoiceCode, setInvoiceCode] = useState(() => createInvoiceCode());
  const [createdQrCodes, setCreatedQrCodes] = useState<CreatedQrCode[]>([]);
  const [isCreatingQr, setIsCreatingQr] = useState(false);
  const [qrError, setQrError] = useState('');
  const [returnQrValue, setReturnQrValue] = useState('');
  const [returnMessage, setReturnMessage] = useState('');
  const [returnError, setReturnError] = useState('');
  const [isReturning, setIsReturning] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [statsState, setStatsState] = useState<StatsState>({
    sold: null,
    recovered: null,
    isLoading: false,
    error: '',
  });

  const isScanOpen = scanView !== 'home';
  const dashboardStats = createDashboardStats(statsState.sold, statsState.recovered);

  const updateBoundedCount = (value: string, update: (count: number) => void) => {
    const numericValue = Number(value.replace(/[^\d]/g, ''));
    update(Math.min(100, Math.max(0, Number.isNaN(numericValue) ? 0 : numericValue)));
  };

  const copyQrCode = async () => {
    if (!qrCodeValue) {
      return;
    }

    await navigator.clipboard.writeText(qrCodeValue);
  };

  const handleLoginSuccess = (data: LoginResponse) => {
    const nextStore = {
      ...fallbackStore,
      id: data.store.id,
      code: data.store.code,
      name: data.store.name,
    };

    setAccessToken(data.accessToken);
    setTokenType(data.tokenType);
    setStore(nextStore);
    setQrCodeValue(nextStore.code);
    setIsLoggedIn(true);
    setActivePage('home');
    setScanView('home');
    saveAuthCookie({
      accessToken: data.accessToken,
      tokenType: data.tokenType,
      store: data.store,
    });
  };

  useEffect(() => {
    const session = readAuthCookie();

    if (session?.accessToken && session.store) {
      handleLoginSuccess(session);
    }
  }, []);

  const logout = () => {
    clearAuthCookie();
    setAccessToken('');
    setTokenType('');
    setStore(fallbackStore);
    setQrCodeValue(fallbackStore.code);
    setCreatedQrCodes([]);
    setReturnQrValue('');
    setReturnMessage('');
    setReturnError('');
    setStatsState({
      sold: null,
      recovered: null,
      isLoading: false,
      error: '',
    });
    setIsLoggedIn(false);
    setAuthPage('login');
    setActivePage('home');
    setScanView('home');
  };

  const openPage = (page: ActivePage) => {
    setActivePage(page);
    setScanView('home');
  };

  const loadMerchantStats = async () => {
    if (!accessToken || store.id <= 0) {
      return;
    }

    const range = getDefaultDateRange();
    setStatsState((current) => ({ ...current, isLoading: true, error: '' }));

    try {
      const [sold, recovered] = await Promise.all([
        api.stats.sold({ storeId: store.id, ...range }, accessToken),
        api.stats.recovered({ storeId: store.id, ...range }, accessToken),
      ]);

      setStatsState({
        sold,
        recovered,
        isLoading: false,
        error: '',
      });
    } catch (err) {
      setStatsState((current) => ({
        ...current,
        isLoading: false,
        error: err instanceof Error ? err.message : '統計資料讀取失敗',
      }));
    }
  };

  useEffect(() => {
    if (isLoggedIn && accessToken && store.id > 0) {
      void loadMerchantStats();
    }
  }, [isLoggedIn, accessToken, store.id]);

  const createMerchantQrCode = async () => {
    setQrError('');
    setIsCreatingQr(true);

    try {
      const requests: Array<{ category: MerchantCategory; count: number }> = [
        { category: 'cup', count: cupCount },
        { category: 'meal_box', count: mealBoxCount },
      ].filter((item): item is { category: MerchantCategory; count: number } => item.count > 0);

      if (requests.length === 0) {
        throw new Error('請至少輸入一項數量');
      }

      const responses = await Promise.all(
        requests.map((request) =>
          api.merchant.createQrCode(
            {
              invoiceCode,
              category: request.category,
              count: request.count,
            },
            accessToken,
          ),
        ),
      );
      const nextQrCodes = await Promise.all(
        responses.map(async (item) => ({
          ...item,
          imageUrl: await QRCode.toDataURL(item.qrValue, {
            width: 240,
            margin: 2,
            color: {
              dark: '#112636',
              light: '#ffffff',
            },
          }),
        })),
      );

      setCreatedQrCodes(nextQrCodes);
      setQrCodeValue(nextQrCodes.map((item) => item.qrValue).join('\n'));
      await loadMerchantStats();
    } catch (err) {
      setQrError(err instanceof Error ? err.message : '建立 QRCode 失敗，請稍後再試');
    } finally {
      setIsCreatingQr(false);
    }
  };

  const scanReturn = async () => {
    setReturnError('');
    setReturnMessage('');
    setIsReturning(true);

    try {
      const data = await api.merchant.scanReturn(
        {
          qrValue: returnQrValue.trim(),
        },
        accessToken,
      );

      setReturnMessage(
        data.remainingCount > 0
          ? `回收成功，尚有 ${data.remainingCount} 個未歸還`
          : '回收成功，這筆借出已全數歸還',
      );
      setReturnQrValue('');
      await loadMerchantStats();
    } catch (err) {
      setReturnError(err instanceof Error ? err.message : '回收失敗，請稍後再試');
    } finally {
      setIsReturning(false);
    }
  };

  const renderActivePage = () => {
    if (activePage === 'records') {
      return (
        <RecordsPage
          storeName={store.name}
          stats={dashboardStats}
          createdQrCodes={createdQrCodes}
          isLoading={statsState.isLoading}
          error={statsState.error}
        />
      );
    }

    if (activePage === 'stats') {
      return (
        <StatsPage
          storeName={store.name}
          stats={dashboardStats}
          isLoading={statsState.isLoading}
          error={statsState.error}
        />
      );
    }

    if (activePage === 'profile') {
      return (
        <ProfilePage
          accessToken={accessToken}
          tokenType={tokenType}
          store={store}
          onLogout={logout}
        />
      );
    }

    return (
      <HomePage
        stats={dashboardStats}
        isLoading={statsState.isLoading}
        error={statsState.error}
        onOpenQr={() => setScanView('storeQr')}
      />
    );
  };

  return (
    <main className="app-frame">
      <section className="phone-screen" aria-label="綠食堂 WebApp">
        {isLoggedIn && (
          <div className="topbar">
            <div className="brand-row">
              <h1>還寶同步士</h1>
              <i className="fa-solid fa-leaf" aria-hidden="true" />
            </div>
            <button className="icon-button" type="button" aria-label="通知">
              <i className="fa-regular fa-bell" aria-hidden="true" />
              <span className="notify-dot" />
            </button>
          </div>
        )}

        <div className="content-scroll auth-content">
          {isLoggedIn ? (
            renderActivePage()
          ) : (
            <AuthGate
              mode={authPage}
              onSwitchMode={setAuthPage}
              onLoginSuccess={handleLoginSuccess}
              onRegisterSuccess={handleLoginSuccess}
            />
          )}
        </div>

        {isLoggedIn && isScanOpen && (
          <section
            className="scan-panel"
            aria-label="Scan 操作面板"
          >
            <div className="scan-handle" aria-hidden="true" />
            <div className="scan-actions">
              <button
                className={scanView === 'reader' ? 'active' : ''}
                type="button"
                onClick={() => setScanView('reader')}
              >
                <i className="fa-solid fa-qrcode" aria-hidden="true" />
                掃描回收
              </button>
              <button
                className={scanView === 'storeQr' ? 'active' : ''}
                type="button"
                onClick={() => setScanView('storeQr')}
              >
                <i className="fa-solid fa-plus" aria-hidden="true" />
                創建 QRCode
              </button>
              <button
                className="scan-close"
                type="button"
                aria-label="關閉 Scan"
                onClick={() => setScanView('home')}
              >
                <i className="fa-solid fa-xmark" aria-hidden="true" />
              </button>
            </div>

            {scanView === 'reader' ? (
              <div className="scanner-view">
                <div className="scanner-lens">
                  <span className="corner top-left" />
                  <span className="corner top-right" />
                  <span className="corner bottom-left" />
                  <span className="corner bottom-right" />
                  <div className="scan-line" />
                  <i className="fa-solid fa-qrcode" aria-hidden="true" />
                </div>
                <h2>讀取 QRCode</h2>
                <p>掃描或貼上 QR Value，送出後會回收 1 個容器</p>
                <form
                  className="return-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void scanReturn();
                  }}
                >
                  <label className="scan-field">
                    <span>QR Value</span>
                    <input
                      required
                      type="text"
                      value={returnQrValue}
                      onChange={(event) => setReturnQrValue(event.target.value)}
                      placeholder="INV-20260509-001|tea-shop|cup"
                    />
                  </label>
                  {returnError && <p className="form-error">{returnError}</p>}
                  {returnMessage && <p className="form-success">{returnMessage}</p>}
                  <button className="qr-submit" disabled={isReturning} type="submit">
                    {isReturning ? '回收中...' : '送出回收'}
                  </button>
                </form>
              </div>
            ) : (
              <div className="store-qr-view">
                <div className="store-card">
                  <span className="store-badge">
                    <i className="fa-solid fa-store" aria-hidden="true" />
                    對應店家
                  </span>
                  <h2>{store.name}</h2>
                  <p>{store.address}</p>
                  <div
                    className={createdQrCodes.length > 1 ? 'qr-preview-list' : 'large-qr'}
                    aria-label={`${store.name} QRCode`}
                  >
                    {createdQrCodes.length > 0 ? (
                      createdQrCodes.map((item) => (
                        <figure className="created-qr" key={item.qrValue}>
                          <img src={item.imageUrl} alt={`${store.name} ${item.category} QRCode`} />
                          <figcaption>{item.category === 'cup' ? '環保杯' : '環保餐具'}</figcaption>
                        </figure>
                      ))
                    ) : (
                      <i className="fa-solid fa-qrcode" aria-hidden="true" />
                    )}
                  </div>

                  <form
                    className="order-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void createMerchantQrCode();
                    }}
                  >
                    <label className="scan-field">
                      <span>QRCode</span>
                      <div className="qr-copy-row">
                        <input readOnly type="text" value={qrCodeValue} />
                        <button type="button" aria-label="複製 QRCode" onClick={() => void copyQrCode()}>
                          <i className="fa-regular fa-copy" aria-hidden="true" />
                        </button>
                      </div>
                    </label>
                    <label className="scan-field">
                      <span>環保杯數量</span>
                      <input
                        inputMode="numeric"
                        pattern="[0-9]*"
                        type="text"
                        value={cupCount}
                        onChange={(event) => updateBoundedCount(event.target.value, setCupCount)}
                      />
                    </label>
                    <label className="scan-field">
                      <span>環保餐具數量</span>
                      <input
                        inputMode="numeric"
                        pattern="[0-9]*"
                        type="text"
                        value={mealBoxCount}
                        onChange={(event) =>
                          updateBoundedCount(event.target.value, setMealBoxCount)
                        }
                      />
                    </label>
                    <label className="scan-field invoice-field">
                      <span>發票編號</span>
                      <div>
                        <input
                          required
                          type="text"
                          value={invoiceCode}
                          onChange={(event) => setInvoiceCode(event.target.value)}
                        />
                      </div>
                    </label>
                    {qrError && <p className="form-error">{qrError}</p>}
                    <button className="qr-submit" disabled={isCreatingQr} type="submit">
                      {isCreatingQr ? '送出中...' : '送出借出資料'}
                    </button>
                  </form>

                </div>
              </div>
            )}
          </section>
        )}

        {isLoggedIn && (
          <nav className="bottom-nav" aria-label="底部導覽">
            {tabs.slice(0, 2).map((tab) => (
              <button
                className={activePage === tab.id ? 'active' : ''}
                type="button"
                key={tab.id}
                onClick={() => openPage(tab.id)}
              >
                <i className={tab.icon} aria-hidden="true" />
                <span>{tab.label}</span>
              </button>
            ))}
            <button
              className="scan-button"
              type="button"
              aria-label="Scan"
              onClick={() => {
                setActivePage('home');
                setScanView(scanView === 'home' ? 'reader' : 'home');
              }}
            >
              <i className="fa-solid fa-expand" aria-hidden="true" />
              <span>Scan</span>
            </button>
            {tabs.slice(2).map((tab) => (
              <button
                className={activePage === tab.id ? 'active' : ''}
                type="button"
                key={tab.id}
                onClick={() => openPage(tab.id)}
              >
                <i className={tab.icon} aria-hidden="true" />
                <span>{tab.label}</span>
              </button>
            ))}
          </nav>
        )}
      </section>
    </main>
  );
}

function AuthGate({
  mode,
  onSwitchMode,
  onLoginSuccess,
  onRegisterSuccess,
}: {
  mode: AuthPage;
  onSwitchMode: (mode: AuthPage) => void;
  onLoginSuccess: (data: LoginResponse) => void;
  onRegisterSuccess: (data: LoginResponse) => void;
}) {
  return mode === 'login' ? (
    <LoginPage onLoginSuccess={onLoginSuccess} onOpenRegister={() => onSwitchMode('register')} />
  ) : (
    <RegisterPage
      onRegisterSuccess={onRegisterSuccess}
      onOpenLogin={() => onSwitchMode('login')}
    />
  );
}

function HomePage({
  stats,
  isLoading,
  error,
  onOpenQr,
}: {
  stats: DashboardStats;
  isLoading: boolean;
  error: string;
  onOpenQr: () => void;
}) {
  const homeStats = [
    {
      id: 'active',
      icon: 'fa-solid fa-utensils',
      title: '在外的',
      subtitle: '環保餐具數量',
      badge: isLoading ? '讀取中' : '在外使用中',
      amount: stats.activeTotal,
    },
    {
      id: 'recovered',
      icon: 'fa-solid fa-recycle',
      title: '已回收的',
      subtitle: '環保餐具數量',
      badge: isLoading ? '讀取中' : '累計已回收',
      amount: stats.recoveredTotal,
    },
  ];

  return (
    <>
      <section className="hero-section">
        <div className="hero-copy">
          <h2>
            一起為地球
            <br />
            盡一份心力！
          </h2>
          <p>
            減少一次性用品
            <br />
            共創永續未來
            <i className="fa-solid fa-leaf" aria-hidden="true" />
          </p>
        </div>
        <img src={globeImage} alt="地球與綠葉插圖" />
      </section>

      <section className="cards" aria-label="環保餐具資訊">
        {homeStats.map((item) => (
          <article className="stat-card" key={item.id}>
            <div className="round-icon">
              <i className={item.icon} aria-hidden="true" />
            </div>
            <div className="stat-copy">
              <h3>
                {item.title}
                <br />
                {item.subtitle}
              </h3>
              <span>{item.badge}</span>
            </div>
            <div className="stat-number">
              <strong>{item.amount}</strong>
              <span>件</span>
              <small>
                <i className="fa-regular fa-clock" aria-hidden="true" />
                {error ? '讀取失敗' : 'API 統計'}
                <br />
                近 5 日
              </small>
            </div>
          </article>
        ))}

        <article className="qr-card" onClick={onOpenQr}>
          <div className="qr-code" aria-label="QRCode 圖示">
            <i className="fa-solid fa-qrcode" aria-hidden="true" />
          </div>
          <div className="qr-copy">
            <h3>環保餐具 QRCode</h3>
            {/* <button type="button">
              查看 QRCode
            </button> */}
          </div>
          <p className="qr-note">
            掃描借用
            <br />
            減少一次性使用
          </p>
        </article>
      </section>

      <section className="reminder-card" aria-label="永續小提醒">
        <img src={spoonImage} alt="餐具插圖" />
        <div>
          <h3>
            <i className="fa-solid fa-leaf" aria-hidden="true" />
            永續小提醒
          </h3>
          <p>
            每一次的借用與歸還，
            <br />
            都是對地球的一份承諾。
          </p>
        </div>
        <i className="fa-solid fa-seedling leaf-mark" aria-hidden="true" />
      </section>
    </>
  );
}

function LoginPage({
  onLoginSuccess,
  onOpenRegister,
}: {
  onLoginSuccess: (data: LoginResponse) => void;
  onOpenRegister: () => void;
}) {
  const [userEmail, setUserEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  return (
    <section className="auth-page auth-minimal" aria-label="登入頁面">
      <div className="auth-heading">
        <h2>登入</h2>
        <p>請登入您的店家帳戶，成功後會同步 API 回傳的商家資料。</p>
      </div>
      <form
        className="auth-form minimal-form"
        onSubmit={async (event) => {
          event.preventDefault();
          setError('');
          setIsSubmitting(true);

          try {
            const data = await api.auth.login({ userEmail, password });
            onLoginSuccess(data);
          } catch (err) {
            setError(err instanceof Error ? err.message : '登入失敗，請稍後再試');
          } finally {
            setIsSubmitting(false);
          }
        }}
      >
        <label>
          Email
          <span className="input-shell">
            <input
              required
              type="email"
              value={userEmail}
              onChange={(event) => setUserEmail(event.target.value)}
              placeholder="tea.owner@example.com"
              autoComplete="email"
            />
            <i className="fa-regular fa-envelope" aria-hidden="true" />
          </span>
        </label>
        <label>
          密碼
          <span className="input-shell">
            <input
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="password"
              autoComplete="current-password"
            />
            <i className="fa-regular fa-eye" aria-hidden="true" />
          </span>
        </label>
        <label className="terms-row">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
          />
          <span>
            我已閱讀並同意 <span>使用條款及隱私權政策</span>。
          </span>
        </label>
        {error && <p className="form-error">{error}</p>}
        <button disabled={isSubmitting} type="submit">
          {isSubmitting ? '登入中...' : '登入帳號'}
        </button>
      </form>

      <SocialLogin />

      <p className="auth-switch">
        Don't have an account? <button type="button" onClick={onOpenRegister}>Sign Up</button>
      </p>
    </section>
  );
}

function RegisterPage({
  onRegisterSuccess,
  onOpenLogin,
}: {
  onRegisterSuccess: (data: LoginResponse) => void;
  onOpenLogin: () => void;
}) {
  const [form, setForm] = useState({
    storeName: '',
    userEmail: '',
    password: '',
  });
  const [accepted, setAccepted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const updateField = (field: keyof typeof form, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  return (
    <section className="auth-page auth-minimal" aria-label="註冊頁面">
      <div className="auth-heading">
        <h2>註冊</h2>
        <p>請填寫商家資料以建立帳戶。</p>
      </div>
      <form
        className="auth-form minimal-form"
        onSubmit={async (event) => {
          event.preventDefault();
          setError('');
          setIsSubmitting(true);

          try {
            const data = await api.auth.register({
              userEmail: form.userEmail,
              password: form.password,
              storeName: form.storeName,
            });
            onRegisterSuccess(data);
          } catch (err) {
            setError(err instanceof Error ? err.message : '註冊失敗，請稍後再試');
          } finally {
            setIsSubmitting(false);
          }
        }}
      >
        <label>
          註冊商家
          <span className="input-shell">
            <input
              required
              type="text"
              value={form.storeName}
              onChange={(event) => updateField('storeName', event.target.value)}
              placeholder="綠森咖啡"
            />
            <i className="fa-solid fa-store" aria-hidden="true" />
          </span>
        </label>
        <label>
          電子郵件
          <span className="input-shell">
            <input
              required
              type="email"
              value={form.userEmail}
              onChange={(event) => updateField('userEmail', event.target.value)}
              placeholder="name@example.com"
              autoComplete="email"
            />
            <i className="fa-regular fa-envelope" aria-hidden="true" />
          </span>
        </label>
        <label>
          密碼
          <span className="input-shell">
            <input
              required
              type="password"
              minLength={8}
              value={form.password}
              onChange={(event) => updateField('password', event.target.value)}
              placeholder="至少 8 碼"
              autoComplete="new-password"
            />
            <i className="fa-regular fa-eye" aria-hidden="true" />
          </span>
        </label>
        <label className="terms-row">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(event) => setAccepted(event.target.checked)}
          />
          <span>
            我已閱讀並同意 <span>使用條款及隱私權政策</span>。
          </span>
        </label>
        {error && <p className="form-error">{error}</p>}
        <button disabled={isSubmitting} type="submit">
          {isSubmitting ? '建立中...' : '建立帳號'}
        </button>
      </form>

      <SocialLogin />

      <p className="auth-switch">
        Already have an account? <button type="button" onClick={onOpenLogin}>Log in</button>
      </p>
    </section>
  );
}

function SocialLogin() {
  return (
    <div className="social-login">
      <div className="divider">
        <span>Or continue with</span>
      </div>
      <div className="social-buttons">
        <button type="button" aria-label="使用 Google 登入">
          <span className="google-mark">G</span>
        </button>
        <button type="button" aria-label="使用 Apple 登入">
          <i className="fa-brands fa-apple" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

function RecordsPage({
  storeName,
  stats,
  createdQrCodes,
  isLoading,
  error,
}: {
  storeName: string;
  stats: DashboardStats;
  createdQrCodes: CreatedQrCode[];
  isLoading: boolean;
  error: string;
}) {
  type RecordItem = {
    id: string;
    type: RecordType;
    category: MerchantCategory;
    quantity: number;
    detail: string;
    time: string;
    qrValue?: string;
    imageUrl?: string;
  };

  const [selectedRecord, setSelectedRecord] = useState<RecordItem | null>(null);

  const findQrCode = (category: MerchantCategory, date: string) =>
    createdQrCodes.find((item) => item.category === category && item.issuedAt.startsWith(date));

  const recordItems = stats.dailyRows.flatMap((row) => {
    const items: RecordItem[] = [];
    const cupQrCode = findQrCode('cup', row.date);
    const mealBoxQrCode = findQrCode('meal_box', row.date);

    if (row.cupSold > 0) {
      items.push({
        id: `${row.date}-sold-cup`,
        type: '借出' as RecordType,
        category: 'cup',
        quantity: row.cupSold,
        detail: '環保杯',
        time: row.date,
        qrValue: cupQrCode?.qrValue,
        imageUrl: cupQrCode?.imageUrl,
      });
    }

    if (row.mealBoxSold > 0) {
      items.push({
        id: `${row.date}-sold-meal-box`,
        type: '借出' as RecordType,
        category: 'meal_box',
        quantity: row.mealBoxSold,
        detail: '環保餐具',
        time: row.date,
        qrValue: mealBoxQrCode?.qrValue,
        imageUrl: mealBoxQrCode?.imageUrl,
      });
    }

    if (row.cupRecovered > 0) {
      items.push({
        id: `${row.date}-recovered-cup`,
        type: '回收' as RecordType,
        category: 'cup',
        quantity: row.cupRecovered,
        detail: '環保杯',
        time: row.date,
      });
    }

    if (row.mealBoxRecovered > 0) {
      items.push({
        id: `${row.date}-recovered-meal-box`,
        type: '回收' as RecordType,
        category: 'meal_box',
        quantity: row.mealBoxRecovered,
        detail: '環保餐具',
        time: row.date,
      });
    }

    return items;
  });

  if (selectedRecord) {
    return (
      <section className="records-page record-detail-page" aria-label="紀錄詳情">
        <button className="record-back" type="button" onClick={() => setSelectedRecord(null)}>
          <i className="fa-solid fa-arrow-left" aria-hidden="true" />
          返回紀錄
        </button>

        <article className="record-detail">
          <div className="record-detail-head">
            <div>
              <span>{selectedRecord.type}詳情</span>
              <h3>{selectedRecord.detail}</h3>
            </div>
          </div>
          <dl>
            <div>
              <dt>店家</dt>
              <dd>{storeName}</dd>
            </div>
            <div>
              <dt>日期</dt>
              <dd>{selectedRecord.time}</dd>
            </div>
            <div>
              <dt>分類</dt>
              <dd>{selectedRecord.category === 'cup' ? '環保杯' : '環保餐具'}</dd>
            </div>
            <div>
              <dt>數量</dt>
              <dd>{selectedRecord.quantity} 件</dd>
            </div>
            <div>
              <dt>類型</dt>
              <dd>{selectedRecord.type}</dd>
            </div>
          </dl>
          {selectedRecord.imageUrl ? (
            <div className="record-detail-qr">
              <img src={selectedRecord.imageUrl} alt={`${selectedRecord.detail} QRCode`} />
              <p>{selectedRecord.qrValue}</p>
            </div>
          ) : (
            <p className="record-detail-note">這筆 API 統計沒有回傳明文 QRCode。</p>
          )}
        </article>
      </section>
    );
  }

  return (
    <section className="records-page" aria-label="借出與回收紀錄">
      <div className="records-header">
        <span>紀錄頁面</span>
        <h2>借出 / 回收紀錄</h2>
        <p>{storeName} 的近 5 日 API 流動紀錄</p>
      </div>

      <div className="records-summary">
        <div>
          <strong>{stats.soldTotal}</strong>
          <span>借出</span>
        </div>
        <div>
          <strong>{stats.recoveredTotal}</strong>
          <span>回收</span>
        </div>
      </div>

      {error && <p className="form-error">{error}</p>}
      {isLoading && <p className="form-success">正在讀取紀錄...</p>}

      <ul className="record-list">
        {recordItems.map((record) => (
          <li
            className={record.type === '借出' ? 'loaned' : 'returned'}
            key={record.id}
            role="button"
            tabIndex={0}
            onClick={() => setSelectedRecord(record)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                setSelectedRecord(record);
              }
            }}
          >
            <div className="record-icon">
              <i
                className={
                  record.type === '借出'
                    ? 'fa-solid fa-arrow-up-right-from-square'
                    : 'fa-solid fa-recycle'
                }
                aria-hidden="true"
              />
            </div>
            <div className="record-body">
              <div>
                <h3>{record.type}</h3>
                <strong>{record.quantity} 件</strong>
              </div>
              <p>{storeName}</p>
              <small>
                {record.detail} · {record.time}
              </small>
            </div>
          </li>
        ))}
        {!isLoading && recordItems.length === 0 && (
          <li>
            <div className="record-icon">
              <i className="fa-solid fa-circle-info" aria-hidden="true" />
            </div>
            <div className="record-body">
              <div>
                <h3>尚無紀錄</h3>
                <strong>0 件</strong>
              </div>
              <p>{storeName}</p>
              <small>近 5 日 API 沒有借出或回收資料</small>
            </div>
          </li>
        )}
      </ul>

    </section>
  );
}

function StatsPage({
  storeName,
  stats,
  isLoading,
  error,
}: {
  storeName: string;
  stats: DashboardStats;
  isLoading: boolean;
  error: string;
}) {
  const totalActivity = stats.soldTotal + stats.recoveredTotal;
  const soldPercent = totalActivity > 0 ? Math.round((stats.soldTotal / totalActivity) * 100) : 0;
  const recoveredPercent = totalActivity > 0 ? 100 - soldPercent : 0;
  const maxDailyActivity = Math.max(
    1,
    ...stats.dailyRows.flatMap((item) => [item.loaned, item.returned]),
  );

  return (
    <section className="stats-page" aria-label="店家統計">
      <div className="stats-header">
        <span>統計頁面</span>
        <h2>{storeName}</h2>
        <p>根據 API 分析近 5 日提供與回收比例，以及每日出借狀況。</p>
      </div>

      {error && <p className="form-error">{error}</p>}
      {isLoading && <p className="form-success">正在讀取統計...</p>}

      <article className="chart-card">
        <div className="chart-title">
          <div>
            <span>比例分析</span>
            <h3>提供 / 回收比例</h3>
          </div>
          <i className="fa-solid fa-chart-pie" aria-hidden="true" />
        </div>
        <div className="pie-chart-row">
          <div
            className="pie-chart"
            style={{
              background: `conic-gradient(#207341 0 ${soldPercent}%, #8fba64 ${soldPercent}% 100%)`,
            }}
            aria-label={`提供 ${soldPercent}%，回收 ${recoveredPercent}%`}
          >
            <span>{recoveredPercent}%</span>
          </div>
          <div className="chart-legend">
            <div>
              <span className="legend-dot provided" />
              <p>提供</p>
              <strong>{stats.soldTotal} 件</strong>
            </div>
            <div>
              <span className="legend-dot returned" />
              <p>回收</p>
              <strong>{stats.recoveredTotal} 件</strong>
            </div>
          </div>
        </div>
      </article>

      <article className="chart-card">
        <div className="chart-title">
          <div>
            <span>每日分析</span>
            <h3>每天出借狀況</h3>
          </div>
          <i className="fa-solid fa-chart-simple" aria-hidden="true" />
        </div>
        <div className="bar-legend">
          <span>
            <i className="legend-dot loaned" />
            借出
          </span>
          <span>
            <i className="legend-dot returned" />
            回收
          </span>
        </div>
        <div className="bar-chart" aria-label="每日借出與回收長條圖">
          {stats.dailyRows.map((item) => (
            <div className="bar-item" key={item.day}>
              <div className="bar-values">
                <strong>{item.loaned}</strong>
                <strong>{item.returned}</strong>
              </div>
              <div className="bar-pair">
                <span
                  className="bar loaned"
                  style={{
                    height: `${Math.max(18, (item.loaned / maxDailyActivity) * 116)}px`,
                  }}
                />
                <span
                  className="bar returned"
                  style={{
                    height: `${Math.max(18, (item.returned / maxDailyActivity) * 116)}px`,
                  }}
                />
              </div>
              <small>{item.day}</small>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}

function ProfilePage({
  accessToken,
  tokenType,
  store,
  onLogout,
}: {
  accessToken: string;
  tokenType: string;
  store: StoreInfo;
  onLogout: () => void;
}) {
  return (
    <section className="profile-page" aria-label="用戶資料">
      <div className="profile-hero">
        <div className="avatar">
          <i className="fa-solid fa-store" aria-hidden="true" />
        </div>
        <div>
          <span>API 回傳商家</span>
          <h2>{store.name}</h2>
          <p>{store.code}</p>
        </div>
      </div>

      <article className="profile-card">
        <h3>
          <i className="fa-solid fa-store" aria-hidden="true" />
          商家資料
        </h3>
        <dl>
          <div>
            <dt>ID</dt>
            <dd>{store.id}</dd>
          </div>
          <div>
            <dt>Code</dt>
            <dd>{store.code}</dd>
          </div>
          <div>
            <dt>Name</dt>
            <dd>{store.name}</dd>
          </div>
        </dl>
      </article>

      <article className="profile-card">
        <h3>
          <i className="fa-solid fa-key" aria-hidden="true" />
          Token
        </h3>
        <dl>
          <div>
            <dt>Type</dt>
            <dd>{tokenType || '-'}</dd>
          </div>
          <div>
            <dt>Access</dt>
            <dd>{accessToken ? `${accessToken.slice(0, 16)}...` : '-'}</dd>
          </div>
        </dl>
      </article>

      <button className="auth-button logout" type="button" onClick={onLogout}>
        <i className="fa-solid fa-right-from-bracket" aria-hidden="true" />
        登出
      </button>
    </section>
  );
}
