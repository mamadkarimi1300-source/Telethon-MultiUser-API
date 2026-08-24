import { useEffect, useMemo, useRef, useState } from "react";
import { COUNTRIES } from "./countries";

const API_URL = (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "");
const SECRET_KEY_STORAGE = "secret_key";
const STEPS = ["phone", "code", "two_factor", "connected"];

function storedSecretKey() { return sessionStorage.getItem(SECRET_KEY_STORAGE) || ""; }
function normalisePhone(value, dialCode) {
  const persianDigits = "۰۱۲۳۴۵۶۷۸۹";
  const englishValue = value.replace(/[۰-۹]/g, (digit) => persianDigits.indexOf(digit));
  const localNumber = englishValue.replace(/\D/g, "").replace(/^0+/, "");
  if (localNumber.length < 7 || localNumber.length > 14) return "";
  return `+${dialCode}${localNumber}`;
}
function friendlyError(error) {
  const message = String(error?.message || "");
  const lower = message.toLowerCase();
  const safeMessages = [
    "شماره تلفن واردشده معتبر نیست.",
    "ارسال کد تأیید موقتاً محدود شده است. لطفاً کمی بعد دوباره تلاش کنید.",
    "کد تأیید واردشده صحیح نیست.",
    "کد تأیید منقضی شده است. لطفاً درخواست کد جدید کنید.",
    "برای ادامه، رمز عبور دو مرحله‌ای تلگرام را وارد کنید.",
    "رمز عبور دو مرحله‌ای صحیح نیست.",
    "ارتباط با تلگرام برقرار نشد. لطفاً دوباره تلاش کنید.",
  ];
  if (safeMessages.some((safeMessage) => message.startsWith(safeMessage))) return message;
  if (lower.includes("phone") && (lower.includes("invalid") || lower.includes("number"))) return safeMessages[0];
  if (lower.includes("code") && lower.includes("expired")) return safeMessages[3];
  if (lower.includes("code") && lower.includes("invalid")) return safeMessages[2];
  if (lower.includes("password") || lower.includes("two-factor")) return safeMessages[5];
  if (lower.includes("authorization") || lower.includes("token") || lower.includes("secret key")) return "کلید امنیتی معتبر نیست.";
  if (lower.includes("network") || lower.includes("fetch") || lower.includes("failed")) return safeMessages[6];
  return "خطایی رخ داد. لطفاً دوباره تلاش کنید.";
}

function CountrySelector({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selectorRef = useRef(null);
  const searchRef = useRef(null);
  const selectedCountry = COUNTRIES.find(({ code }) => code === value) || COUNTRIES.find(({ code }) => code === "IR");
  const filteredCountries = useMemo(() => {
    const cleanQuery = query.trim().toLowerCase();
    if (!cleanQuery) return COUNTRIES;
    return COUNTRIES.filter((country) => `${country.name} ${country.code} +${country.dialCode}`.toLowerCase().includes(cleanQuery));
  }, [query]);

  useEffect(() => {
    function closeOnOutsideClick(event) {
      if (!selectorRef.current?.contains(event.target)) setOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  useEffect(() => {
    if (open) searchRef.current?.focus();
  }, [open]);

  function chooseCountry(country) {
    onChange(country.code);
    setQuery("");
    setOpen(false);
  }

  return <div className="country-picker" ref={selectorRef} dir="ltr">
    <button className={`country-trigger ${open ? "is-open" : ""}`} type="button" onClick={() => setOpen((isOpen) => !isOpen)} aria-expanded={open} aria-haspopup="listbox" dir="ltr">
      <span className="country-trigger-copy"><span className="country-flag" aria-hidden="true">{selectedCountry.flag}</span></span>
      <span className="country-trigger-code" dir="ltr">+{selectedCountry.dialCode}</span><span className="country-chevron" aria-hidden="true" />
    </button>
    {open && <div className="country-menu" role="listbox" aria-label="انتخاب کشور">
      <div className="country-search-wrap"><span className="country-search-icon" aria-hidden="true">⌕</span><input ref={searchRef} className="country-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="جستجوی کشور یا کد" aria-label="جستجوی کشور" autoComplete="off" /></div>
      <div className="country-options">{filteredCountries.map((country) => <button className={`country-option ${country.code === selectedCountry.code ? "selected" : ""}`} type="button" role="option" aria-selected={country.code === selectedCountry.code} key={country.code} onClick={() => chooseCountry(country)}><span className="country-flag" aria-hidden="true">{country.flag}</span><span className="country-name">{country.name}</span><span className="country-dial" dir="ltr">+{country.dialCode}</span></button>)}{!filteredCountries.length && <p className="country-empty">کشوری پیدا نشد</p>}</div>
    </div>}
  </div>;
}

function CopyableCode({ code, label = "کپی" }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return <div className="guide-code-wrap" dir="ltr">
    <pre className="guide-code"><code>{code}</code></pre>
    <button className="guide-copy" type="button" onClick={copy}>{copied ? "کپی شد" : label}</button>
  </div>;
}

function ApiRouteDoc({ method, path, description, children }) {
  return <article className="api-route" dir="rtl">
    <div className="api-route-heading" dir="ltr"><span className="api-method">{method}</span><code>{path}</code></div>
    <p className="api-description">{description}</p>
    {children}
  </article>;
}

function GuideModal({ onClose }) {
  const [closing, setClosing] = useState(false);

  function close() {
    if (closing) return;
    setClosing(true);
    window.setTimeout(onClose, 180);
  }

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const groupCurl = `curl -X POST "http://localhost:8000/create-group" \\
  -H "Content-Type: application/json" \\
  -H "X-Secret-Key: <SECRET_KEY>" \\
  -d '{
    "title": "Test Group",
    "users": ["m_k_krimi", "mob83", "mob830"],
    "invite_message": "سلام، امکان اضافه کردن مستقیم شما به گروه وجود نداشت."
  }'`;
  const groupResponse = `{
  "success": true,
  "group_id": -123456789,
  "group": {"id": -123456789, "title": "Test Group"},
  "total": 3,
  "success_count": 2,
  "failed_count": 1,
  "users": [
    {"input": "m_k_krimi", "user_id": 123, "status": "success"},
    {"input": "mob83", "user_id": 456, "status": "invite_sent", "invite_message_sent": true},
    {"input": "mob830", "status": "failed", "error_code": "USER_NOT_FOUND", "message": "Telegram user could not be resolved"}
  ],
  "verification_warning": null
}`;
  const groupError = `{
  "detail": {
    "error_code": "GROUP_CREATION_FAILED",
    "message": "Telegram group creation failed."
  }
}`;
  const sendMessageCurl = `curl -G "http://localhost:8000/send-message" \\
  -H "X-Secret-Key: <SECRET_KEY>" \\
  --data-urlencode "target=m_k_krimi" \\
  --data-urlencode "text=سلام" \\
  --data-urlencode "first_name=User" \\
  --data-urlencode "last_name="`;
  const sendMessageResponse = `{
  "chat_created": true,
  "user_id": 123,
  "message_id": 987
}`;
  const getMessageCurl = `curl -G "http://localhost:8000/get-message" \\
  -H "X-Secret-Key: <SECRET_KEY>" \\
  --data-urlencode "target=m_k_krimi"`;
  const getMessageResponse = `{
  "target": "m_k_krimi",
  "entity": {
    "id": 504408116,
    "type": "User",
    "username": "m_k_krimi",
    "first_name": "User",
    "last_name": "",
    "title": null,
    "phone": null
  },
  "messages": [
    {"id": 901298, "text": "سلام", "date": "2026-01-01 12:00:00+00:00"}
  ]
}`;
  const getMessageError = `{
  "detail": "Telegram request failed"
}`;

  return <div className={`guide-overlay ${closing ? "closing" : ""}`} role="presentation" onMouseDown={(event) => event.target === event.currentTarget && close()}>
    <section className="guide-modal" role="dialog" aria-modal="true" aria-labelledby="guide-title" dir="rtl" onMouseDown={(event) => event.stopPropagation()}>
      <header className="guide-header"><div><h1 id="guide-title">راهنما / Help</h1><p className="guide-subtitle">مستندات API و کلید امنیتی</p></div><button className="guide-close" type="button" aria-label="بستن" onClick={close}>×</button></header>
      <section className="guide-section"><h2>کلید امنیتی</h2><p>کلید امنیتی برای شناسایی حساب کاربر و Session اختصاصی تلگرام استفاده می‌شود. آن را محرمانه نگه دارید.</p><CopyableCode code={'X-Secret-Key: <SECRET_KEY>'} /></section>

      <ApiRouteDoc method="POST" path="/create-group" description="ساخت Basic Telegram Chat و افزودن کاربران resolved شده به آن.">
        <h3>Required Headers</h3><p><code>X-Secret-Key</code> الزامی است. بدنه JSON شامل <code>title</code> و آرایه الزامی <code>users</code> است؛ <code>invite_message</code> اختیاری است و کلاینت <code>invite_link</code> ارسال نمی‌کند.</p>
        <h3>Parameters / Request Body</h3><p><code>title</code> باید متن غیرخالی باشد. <code>users</code> باید آرایه‌ای غیرخالی از رشته‌های غیرخالی باشد. <code>invite_message</code> متن اختیاری پیام دعوت است.</p>
        <ul className="guide-list"><li>کاربرانی که مستقیم اضافه شوند، وضعیت <code>success</code> می‌گیرند و پیام دعوت دریافت نمی‌کنند.</li><li>برای کاربر Privacy Restricted یا کاربری که در بررسی عضویت اضافه نشده، اگر <code>invite_message</code> وجود داشته باشد، سرور یک invite link برای همین گروه می‌سازد و برای همه کاربران لازم reuse می‌کند.</li><li>کلاینت <strong>invite_link</strong> ارسال نمی‌کند؛ سرور آن را خودکار می‌سازد و پیام را به شکل <code>invite_message</code>، سپس لینک واقعی گروه ارسال می‌کند.</li><li>در صورت نبودن <code>invite_message</code>، دعوت ارسال نمی‌شود و وضعیت کاربر <code>not_added</code> خواهد بود.</li></ul>
        <h3>Example Request</h3><CopyableCode code={groupCurl} />
        <h3>Example Response</h3><CopyableCode code={groupResponse} />
        <h3>Possible Errors</h3><p>کلید نامعتبر، نبودن هیچ کاربر قابل resolve، خطا در ساخت گروه، خطاهای Telegram هنگام افزودن کاربر، یا خطای ارسال دعوت. پس از ساخت موفق گروه، پاسخ وضعیت کاربران و <code>group_id</code> را حفظ می‌کند.</p>
        <h3>Example Error Response</h3><CopyableCode code={groupError} />
      </ApiRouteDoc>

      <ApiRouteDoc method="GET" path="/send-message" description="ارسال پیام به یک کاربر Telegram؛ در صورت نیاز شماره تلفن به مخاطب وارد می‌شود.">
        <h3>Required Headers</h3><p><code>X-Secret-Key</code> الزامی است.</p>
        <h3>Parameters / Request Body</h3><p>این Route بدنه ندارد. Query پارامتر <code>target</code> الزامی است. <code>text</code> اختیاری و پیش‌فرض آن <code>hi</code> است؛ <code>first_name</code> اختیاری و پیش‌فرض آن <code>User</code> است؛ <code>last_name</code> اختیاری و پیش‌فرض آن خالی است.</p>
        <h3>Example Request</h3><CopyableCode code={sendMessageCurl} />
        <h3>Example Response</h3><CopyableCode code={sendMessageResponse} />
        <h3>Possible Errors</h3><p>کلید امنیتی الزامی/نامعتبر، پیدا نشدن کاربر یا شماره، پاسخ <code>user_not_found</code> برای شماره‌ای که در Telegram پیدا نشود، یا خطای ارتباط با Telegram با وضعیت 502.</p>
      </ApiRouteDoc>

      <ApiRouteDoc method="GET" path="/get-message" description="دریافت حداکثر ۶۰ پیام اخیر از target مشخص‌شده به همراه اطلاعات entity.">
        <h3>Required Headers</h3><p><code>X-Secret-Key</code> الزامی است.</p>
        <h3>Parameters / Request Body</h3><p>این Route بدنه ندارد و Query پارامتر <code>target</code> الزامی است. target می‌تواند شناسه یا username قابل resolve در Telegram باشد.</p>
        <h3>Example Request</h3><CopyableCode code={getMessageCurl} />
        <h3>Example Response</h3><CopyableCode code={getMessageResponse} />
        <h3>Possible Errors</h3><p>کلید امنیتی الزامی/نامعتبر، خطای resolve کردن target، خطای دریافت پیام از Telegram یا خطای داخلی Route؛ پیاده‌سازی فعلی این خطاها را با وضعیت 500 برمی‌گرداند.</p>
        <h3>Example Error Response</h3><CopyableCode code={getMessageError} />
      </ApiRouteDoc>

      <section className="guide-note"><h2>نکته امنیتی</h2><p>کلید امنیتی فقط در Session مرورگر نگه‌داری می‌شود و بستن این پنجره آن را حذف، بازتولید یا اتصال Telegram را قطع نمی‌کند.</p></section>
    </section>
  </div>;
}

async function request(path, options = {}, authToken = storedSecretKey()) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(authToken ? { "X-Secret-Key": authToken } : {}), ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request failed.");
  return body;
}

export default function App() {
  const [guideOpen, setGuideOpen] = useState(false);
  const [secretKey, setSecretKey] = useState(storedSecretKey());
  const [step, setStep] = useState("phone");
  const [phone, setPhone] = useState("");
  const [countryCode, setCountryCode] = useState("IR");
  const [internationalPhone, setInternationalPhone] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [expiresIn, setExpiresIn] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);

  const countdown = useMemo(() => `${Math.floor(expiresIn / 60)}:${String(expiresIn % 60).padStart(2, "0")}`, [expiresIn]);

  useEffect(() => {
    if (!secretKey) return undefined;
    let active = true;
    request("/telegram/status").then((body) => {
      if (!active) return;
      if (body.status === "connected") { setStep("connected"); setGuideOpen(true); }
      else if (body.status === "two_factor_required") setStep("two_factor");
      else if (body.status === "code_pending") { setStep("code"); setExpiresIn(body.expires_in || 0); }
      else setStep("phone");
    }).catch(() => active && setStep("phone"));
    return () => { active = false; };
  }, [secretKey]);

  useEffect(() => {
    if (!expiresIn || step !== "code") return undefined;
    const timer = setInterval(() => setExpiresIn((value) => Math.max(0, value - 1)), 1000);
    return () => clearInterval(timer);
  }, [expiresIn, step]);

  function saveSecretKey(value) {
    const clean = value.trim();
    sessionStorage.setItem(SECRET_KEY_STORAGE, clean);
    setSecretKey(clean);
  }
  function clearFeedback() { setError(""); setNotice(""); setCopied(false); }
  function finishConnection(noticeText = "") {
    setStep("connected");
    if (noticeText) setNotice(noticeText);
    setGuideOpen(true);
  }

  async function startConnection(event) {
    event.preventDefault(); clearFeedback();
    const selectedCountry = COUNTRIES.find(({ code }) => code === countryCode) || COUNTRIES.find(({ code }) => code === "IR");
    const cleanPhone = normalisePhone(phone, selectedCountry.dialCode);
    if (!/^\+[1-9]\d{7,14}$/.test(cleanPhone)) { setError("شماره تلفن واردشده معتبر نیست."); return; }
    setInternationalPhone(cleanPhone); setBusy(true);
    try {
      const endpoint = secretKey ? "/telegram/connect/start" : "/telegram/register";
      const body = await request(endpoint, { method: "POST", body: JSON.stringify({ phone: cleanPhone }) });
      if (body.api_token) saveSecretKey(body.api_token);
      if (body.status === "connected") finishConnection("Session قبلی تلگرام شما استفاده شد.");
      else { setStep("code"); setExpiresIn(body.expires_in || 0); setNotice("کد تأیید به تلگرام شما ارسال شد."); }
    } catch (requestError) { setError(friendlyError(requestError)); }
    finally { setBusy(false); }
  }

  async function resendCode() {
    if (busy || !secretKey || !internationalPhone) return;
    clearFeedback(); setBusy(true);
    try {
      const body = await request("/telegram/connect/start", { method: "POST", body: JSON.stringify({ phone: internationalPhone }) });
      if (body.status === "connected") finishConnection("Session قبلی تلگرام شما استفاده شد.");
      else { setStep("code"); setExpiresIn(body.expires_in || 0); setNotice("کد تأیید جدید ارسال شد."); }
    } catch (requestError) { setError(friendlyError(requestError)); }
    finally { setBusy(false); }
  }

  async function verifyCode(event) {
    event.preventDefault();
    if (!code.trim() || !expiresIn || busy) return;
    clearFeedback(); setBusy(true);
    try {
      const body = await request("/telegram/connect/verify", { method: "POST", body: JSON.stringify({ code: code.trim() }) });
      if (body.api_token) saveSecretKey(body.api_token);
      if (body.status === "two_factor_required") setStep("two_factor"); else finishConnection();
    } catch (requestError) { setError(friendlyError(requestError)); }
    finally { setBusy(false); }
  }

  async function verifyTwoFactor(event) {
    event.preventDefault();
    if (!password || busy) return;
    clearFeedback(); setBusy(true);
    try {
      const body = await request("/telegram/connect/2fa", { method: "POST", body: JSON.stringify({ password }) });
      if (body.api_token) saveSecretKey(body.api_token);
      finishConnection();
    } catch (requestError) { setError(friendlyError(requestError)); }
    finally { setBusy(false); }
  }

  async function copySecretKey() {
    try { await navigator.clipboard.writeText(secretKey); setCopied(true); setNotice("کلید امنیتی کپی شد."); }
    catch { setError("کپی خودکار در دسترس نیست. کلید امنیتی را انتخاب و دستی کپی کنید."); }
  }
  function resetToPhone() { clearFeedback(); setStep("phone"); setCode(""); setPassword(""); }
  function forgetSecretKey() { sessionStorage.removeItem(SECRET_KEY_STORAGE); setSecretKey(""); resetToPhone(); }

  const stepIndex = STEPS.indexOf(step);
  const isCodeExpired = step === "code" && expiresIn === 0;
  return (
    <main className="shell page-view"><section className="card" aria-live="polite">
      <div className="card-header">
        <div className="brand"><span className="brand-mark">✦</span><span>API تلگرام</span></div>
        <button className="guide-button" onClick={() => setGuideOpen(true)}>راهنما</button>
      </div>
      <div className="content-area">
      <div className="telegram-content" dir="rtl">
      <h1>{step === "connected" ? "تلگرام متصل است" : "اتصال تلگرام"}</h1>
      <p className="intro">حساب تلگرام خود را به برنامه متصل کنید.</p>
      <div className={`steps progress-${stepIndex}`} aria-label="مراحل اتصال">
        {STEPS.map((item, index) => <div className={`step ${index < stepIndex ? "active completed" : index === stepIndex ? "active current" : ""}`} key={item}><span>{index < stepIndex ? "✓" : index + 1}</span><small>{item === "phone" ? "تلفن" : item === "code" ? "کد" : item === "two_factor" ? "احراز هویت" : "متصل"}</small></div>)}
      </div>
      {error && <div className="alert error" role="alert">{error}</div>}
      {notice && <div className="alert notice">{notice}</div>}

      {step === "phone" && <>
    <form onSubmit={startConnection}><label htmlFor="phone">شماره تلفن</label><div className="phone-input" dir="ltr"><CountrySelector value={countryCode} onChange={setCountryCode} /><input id="phone" value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="شماره محلی" inputMode="tel" autoComplete="tel-national" aria-describedby="phone-hint" required /></div><p className="hint" id="phone-hint">کد کشور انتخاب شده است؛ شماره را بدون کد کشور وارد کنید.</p><button className="button" disabled={busy}>{busy ? <><span className="spinner" /> در حال ارسال کد…</> : secretKey ? "ارسال کد تأیید" : "ادامه"}</button></form>
        {secretKey && <button className="text-button" onClick={forgetSecretKey}>استفاده از کلید امنیتی دیگر</button>}
      </>}

      {step === "code" && <form onSubmit={verifyCode}><div className="step-heading"><button type="button" className="back" onClick={resetToPhone}>بازگشت</button></div><p className="hint">کدی را که تلگرام برای <strong dir="ltr">{phone}</strong> ارسال کرده وارد کنید.</p><label htmlFor="code">کد تأیید</label><input id="code" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))} inputMode="numeric" autoComplete="one-time-code" maxLength="6" required /><div className={`countdown ${isCodeExpired ? "expired" : ""}`}>{isCodeExpired ? "کد منقضی شده است" : `اعتبار کد: ${countdown}`}</div><button className="button" disabled={busy || isCodeExpired || code.length < 4}>{busy ? <><span className="spinner" /> در حال بررسی…</> : "تأیید کد"}</button><button type="button" className="text-button resend" onClick={resendCode} disabled={busy || !isCodeExpired}>{busy ? "در حال ارسال…" : "ارسال دوباره کد"}</button></form>}

      {step === "two_factor" && <form onSubmit={verifyTwoFactor}><div className="step-heading"><button type="button" className="back" onClick={() => setStep("code")}>بازگشت</button></div><p className="hint">حساب تلگرام شما رمز دومرحله‌ای دارد.</p><label htmlFor="password">رمز دومرحله‌ای</label><input id="password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /><button className="button" disabled={busy}>{busy ? <><span className="spinner" /> در حال اتصال…</> : "تکمیل اتصال"}</button></form>}

      {step === "connected" && <div className="success-screen"><div className="success-icon">✓</div><h2>تلگرام متصل شد</h2><p>Session اختصاصی تلگرام شما آماده است. کلید امنیتی را امن نگه دارید.</p><div className="token-display"><span>کلید امنیتی شما</span><code dir="ltr">{secretKey}</code></div><button className="button" onClick={copySecretKey}>{copied ? "کپی شد" : "کپی کلید امنیتی"}</button><button className="text-button" onClick={forgetSecretKey}>حذف کلید امنیتی از این مرورگر</button></div>}
      </div>
      </div>
    </section>{guideOpen && <GuideModal onClose={() => setGuideOpen(false)} />}</main>
  );
}
