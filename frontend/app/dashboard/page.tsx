"use client";
import { RequireAuth as __RequireAuth } from '@/features/auth/Guard';

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import PageHero from "@/components/PageHero";
import WelcomePrompt from "@/components/WelcomePrompt";
import { useAuth } from "@/features/auth/AuthProvider";
import {
  BusinessCard,
  combineBilingual,
  fetchJson,
  sendCardWelcome,
  toMediaUrl,
} from "@/lib/api";
import { INVESTMENT_TYPES } from "@/lib/constants";

type Stats = {
  total: number;
  needs_review: number;
  companies: number;
  with_email: number;
  with_phone: number;
};

type CategoryStat = {
  category: string;
  count: number;
};

type PaginatedCardsResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: BusinessCard[];
};

const PAGE_SIZE_OPTIONS = [20, 50, 100];

type SortOrder = "newest" | "oldest";



type EditableCard = {
  person_name: string;
  job_title: string;
  company_name: string;
  mobile_numbers_text: string;
  emails_text: string;
  website: string;
  address: string;
  country: string;
  company_activity: string;
  investment_type: string;
  investment_type_other: string;
  needs_review: boolean;
  review_notes: string;
};

function compactPhone(value: string) {
  const cleaned = String(value || "").replace(/[^0-9+]/g, "");
  if (!cleaned) return "";
  if (cleaned.startsWith("+")) return cleaned;
  return cleaned;
}

function PhoneList({ numbers }: { numbers?: string[] }) {
  const items = (numbers || []).map(compactPhone).filter(Boolean);
  if (!items.length) return <span>-</span>;
  return (
    <div className="phone-list" dir="ltr">
      {items.map((phone, index) => (
        <a
          key={`${phone}-${index}`}
          className="phone-chip"
          href={`tel:${phone}`}
          aria-label={`اتصال بالرقم ${phone}`}
        >
          {phone}
        </a>
      ))}
    </div>
  );
}

function cardField(
  card: BusinessCard,
  field: "person_name" | "job_title" | "company_name",
) {
  if (field === "person_name")
    return combineBilingual(
      card.person_name,
      card.person_name_ar,
      card.person_name_en,
    );
  if (field === "job_title")
    return combineBilingual(
      card.job_title,
      card.job_title_ar,
      card.job_title_en,
    );
  return combineBilingual(
    card.company_name,
    card.company_name_ar,
    card.company_name_en,
  );
}

function getAr(primary: string, ar: string) {
  if (ar) return ar;
  const lines = (primary || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (lines.length >= 1 && /[؀-ۿ]/.test(lines[0])) return lines[0];
  return "";
}

function getEn(primary: string, en: string) {
  if (en) return en;
  const lines = (primary || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  const enLine = lines.find((l) => !/[؀-ۿ]/.test(l));
  return enLine || "";
}

function BilingualCell({
  primary, ar, en,
}: { primary: string; ar: string; en: string }) {
  const arabic = getAr(primary, ar);
  const english = getEn(primary, en);
  if (!arabic && !english) return <span>-</span>;
  return (
    <div className="bilingual-cell">
      {arabic && <span className="bilingual-ar" dir="rtl">{arabic}</span>}
      {english && <span className="bilingual-en" dir="ltr">{english}</span>}
    </div>
  );
}

function hasCardImages(card: BusinessCard) {
  return Boolean(toMediaUrl(card.front_image_url) || toMediaUrl(card.back_image_url));
}

function CardImageFigure({
  title,
  url,
  alt,
  onError,
}: {
  title: string;
  url?: string;
  alt: string;
  onError: () => void;
}) {
  const imageUrl = toMediaUrl(url);
  if (!imageUrl) {
    return (
      <div className="image-placeholder" role="note">
        <strong>{title}</strong>
        <span>لا توجد صورة محفوظة لهذا الوجه.</span>
      </div>
    );
  }

  return (
    <figure>
      <figcaption>{title}</figcaption>
      <img src={imageUrl} alt={alt} onError={onError} />
    </figure>
  );
}

function toEditForm(card: BusinessCard): EditableCard {
  return {
    person_name: cardField(card, "person_name"),
    job_title: cardField(card, "job_title"),
    company_name: cardField(card, "company_name"),
    mobile_numbers_text: (card.mobile_numbers || []).join(" | "),
    emails_text: (card.emails || []).join(" | "),
    website: card.website || "",
    address: card.address || "",
    country: card.country || "",
    company_activity: card.company_activity || "",
    investment_type: card.investment_type || "",
    investment_type_other: card.investment_type_other || "",
    needs_review: card.needs_review,
    review_notes: card.review_notes || "",
  };
}

function splitMultiValue(value: string) {
  return value
    .split(/[|\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

const TOP_CATEGORY_COUNT = 8;

function CategoryChip({
  item,
  isActive,
  onClick,
}: {
  item: CategoryStat;
  isActive: boolean;
  onClick: () => void;
}) {
  const isUnknown = item.category === "غير محدد";
  return (
    <button
      type="button"
      className={`category-chip${isActive ? " active" : ""}${isUnknown ? " disabled" : ""}`}
      onClick={onClick}
      disabled={isUnknown}
      title={
        isUnknown
          ? "لا يوجد نوع استثمار محدد لهذه السجلات"
          : `عرض الشركات التابعة لـ ${item.category}`
      }
    >
      <span>{item.category}</span>
      <strong>{item.count}</strong>
    </button>
  );
}

function displayInvestment(card: BusinessCard) {
  if (card.investment_type === "غير ذلك")
    return card.investment_type_other || "غير ذلك";
  return card.investment_type || "-";
}

function DashboardPageInner() {
  const { user } = useAuth();
  const router = useRouter();
  const welcomeConfigured = !!user?.welcome_email?.sender_email;
  const [welcomeBusyId, setWelcomeBusyId] = useState<number | null>(null);
  const [welcomeSetupOpen, setWelcomeSetupOpen] = useState(false);
  const [welcomeErrorMsg, setWelcomeErrorMsg] = useState("");
  const [q, setQ] = useState("");
  const [company, setCompany] = useState("");
  const [activity, setActivity] = useState("");
  const [investmentType, setInvestmentType] = useState("");
  const [needsReview, setNeedsReview] = useState("");
  const [country, setCountry] = useState("");
  const [countries, setCountries] = useState<string[]>([]);
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const [cards, setCards] = useState<BusinessCard[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [totalResults, setTotalResults] = useState(0);
  const [stats, setStats] = useState<Stats | null>(null);
  const [categoryStats, setCategoryStats] = useState<CategoryStat[]>([]);
  const [categoryFilterText, setCategoryFilterText] = useState("");
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [imageCard, setImageCard] = useState<BusinessCard | null>(null);
  const [editCard, setEditCard] = useState<BusinessCard | null>(null);
  const [editForm, setEditForm] = useState<EditableCard | null>(null);
  const [editFrontFile, setEditFrontFile] = useState<File | null>(null);
  const [editBackFile, setEditBackFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [imageError, setImageError] = useState("");
  const [deleteCard, setDeleteCard] = useState<BusinessCard | null>(null);
  const [deleting, setDeleting] = useState(false);

  const filterQuery = useMemo(() => {
    const params = new URLSearchParams();
    if (q.trim()) params.set("q", q.trim());
    if (company.trim()) params.set("company", company.trim());
    if (activity.trim()) params.set("activity", activity.trim());
    if (investmentType.trim())
      params.set("investment_type", investmentType.trim());
    if (needsReview) params.set("needs_review", needsReview);
    if (country.trim()) params.set("country", country.trim());
    if (createdFrom) params.set("created_from", createdFrom);
    if (createdTo) params.set("created_to", createdTo);
    return params.toString();
  }, [q, company, activity, investmentType, needsReview, country, createdFrom, createdTo]);

  const requestQuery = useMemo(() => {
    const params = new URLSearchParams(filterQuery);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    params.set("sort", sortOrder);
    return params.toString();
  }, [filterQuery, page, pageSize, sortOrder]);

  const exportQuery = useMemo(() => {
    const params = new URLSearchParams(filterQuery);
    params.set("sort", sortOrder);
    return params.toString();
  }, [filterQuery, sortOrder]);

  const topCategories = useMemo(
    () => categoryStats.slice(0, TOP_CATEGORY_COUNT),
    [categoryStats],
  );
  const hasMoreCategories = categoryStats.length > TOP_CATEGORY_COUNT;
  const filteredCategoryStats = useMemo(() => {
    const term = categoryFilterText.trim();
    if (!term) return categoryStats;
    return categoryStats.filter((item) => item.category.includes(term));
  }, [categoryStats, categoryFilterText]);

  const hasActiveSearch = Boolean(filterQuery);
  const totalPages = Math.max(1, Math.ceil(totalResults / pageSize));
  const pageStart = totalResults ? (page - 1) * pageSize + 1 : 0;
  const pageEnd = Math.min(page * pageSize, totalResults);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [list, statsData] = await Promise.all([
        fetchJson<PaginatedCardsResponse | BusinessCard[]>(`/cards/?${requestQuery}`),
        fetchJson<Stats>("/cards/stats/"),
      ]);
      if (Array.isArray(list)) {
        setCards(list);
        setTotalResults(list.length);
      } else {
        setCards(list.results || []);
        setTotalResults(list.count || 0);
      }
      setStats(statsData);
    } catch (e: any) {
      setError(e.message || "فشل تحميل البيانات");
    } finally {
      setLoading(false);
    }
  }

  async function loadCategoryStats() {
    try {
      const data = await fetchJson<CategoryStat[]>("/cards/stats-by-category/?field=investment_type");
      setCategoryStats(data || []);
    } catch {
      // Non-critical: the categories panel simply stays empty on failure.
    }
  }

  function applyCategoryFilter(category: string) {
    if (category === "غير محدد") return;
    setPage(1);
    setQ("");
    setInvestmentType((current) => (current === category ? "" : category));
  }

  async function confirmDelete() {
    if (!deleteCard) return;
    setDeleting(true);
    setError("");
    try {
      await fetchJson(`/cards/${deleteCard.id}/`, { method: "DELETE" });
      setCards((current) => current.filter((c) => c.id !== deleteCard.id));
      setDeleteCard(null);
      await Promise.all([load(), loadCategoryStats()]);
    } catch (e: any) {
      setError(e.message || "فشل حذف الكرت");
      setDeleteCard(null);
    } finally {
      setDeleting(false);
    }
  }

  function openEdit(card: BusinessCard) {
    setEditCard(card);
    setEditForm(toEditForm(card));
    setError("");
  }

  async function handleWelcome(card: BusinessCard) {
    // Already sent → not actionable (the cell renders a static chip, not a button).
    if (card.welcome_status === "sent") return;
    // Not configured → show the setup popup (offer to set the sender email).
    if (!welcomeConfigured) {
      setWelcomeSetupOpen(true);
      return;
    }
    if (welcomeBusyId) return;
    setWelcomeBusyId(card.id);
    setWelcomeErrorMsg("");
    try {
      const res = await sendCardWelcome(card.id, false);
      if (res.card) {
        const updated = res.card;
        setCards((cur) => cur.map((c) => (c.id === updated.id ? updated : c)));
      }
    } catch (e: any) {
      // Show the reason centred on screen; mark the row as failed for a retry.
      setWelcomeErrorMsg(e.message || "تعذّر إرسال رسالة الترحيب.");
      setCards((cur) => cur.map((c) => (c.id === card.id ? { ...c, welcome_status: "failed" } : c)));
    } finally {
      setWelcomeBusyId(null);
    }
  }

  async function saveEdit() {
    if (!editCard || !editForm) return;
    setSaving(true);
    setError("");
    try {
      let updated: BusinessCard;
      // If user supplied new front/back files, send multipart/form-data
      if (editFrontFile || editBackFile) {
        const fd = new FormData();
        fd.append('person_name', editForm.person_name);
        fd.append('job_title', editForm.job_title);
        fd.append('company_name', editForm.company_name);
        fd.append('mobile_numbers', JSON.stringify(splitMultiValue(editForm.mobile_numbers_text)));
        fd.append('emails', JSON.stringify(splitMultiValue(editForm.emails_text)));
        fd.append('website', editForm.website || '');
        fd.append('address', editForm.address || '');
        fd.append('country', editForm.country || '');
        fd.append('company_activity', editForm.company_activity || '');
        fd.append('investment_type', editForm.investment_type || '');
        fd.append('investment_type_other', editForm.investment_type === 'غير ذلك' ? (editForm.investment_type_other || '') : '');
        fd.append('needs_review', String(editForm.needs_review));
        fd.append('review_notes', editForm.review_notes || '');
        if (editFrontFile) fd.append('front', editFrontFile);
        if (editBackFile) fd.append('back', editBackFile);

        updated = await fetchJson<BusinessCard>(`/cards/${editCard.id}/`, {
          method: 'PATCH',
          body: fd,
        });
      } else {
        updated = await fetchJson<BusinessCard>(`/cards/${editCard.id}/`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            person_name: editForm.person_name,
            job_title: editForm.job_title,
            company_name: editForm.company_name,
            mobile_numbers: splitMultiValue(editForm.mobile_numbers_text),
            emails: splitMultiValue(editForm.emails_text),
            website: editForm.website,
            address: editForm.address,
            country: editForm.country,
            company_activity: editForm.company_activity,
            investment_type: editForm.investment_type,
            investment_type_other:
              editForm.investment_type === "غير ذلك"
                ? editForm.investment_type_other
                : "",
            needs_review: editForm.needs_review,
            review_notes: editForm.review_notes,
          }),
        });
      }
      setCards((current) =>
        current.map((card) => (card.id === updated.id ? updated : card)),
      );
      setEditCard(null);
      setEditForm(null);
      setEditFrontFile(null);
      setEditBackFile(null);
      await Promise.all([load(), loadCategoryStats()]);
    } catch (e: any) {
      setError(e.message || "فشل حفظ التعديلات");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    const handle = setTimeout(() => {
      load();
    }, 250);
    return () => clearTimeout(handle);
  }, [requestQuery]);

  async function loadCountries() {
    try {
      const data = await fetchJson<string[]>("/cards/countries/");
      setCountries(data || []);
    } catch {
      // Non-critical: the country filter simply stays empty on failure.
    }
  }

  useEffect(() => {
    loadCategoryStats();
    loadCountries();
  }, []);

  return (
    <main className="container">
      
      <PageHero
        title="عرض بيانات الكروت والبحث"
        description="جدول يعرض الكروت المحفوظة مع البحث بالاسم والشركة وبيانات الاتصال والنشاط ونوع الاستثمار."
      />

      <section className="card">
        <div className="section-head">
          <h2>ملخص قاعدة البيانات</h2>
        </div>
        <div className="stats-grid">
          <div className="stat-box">
            <span>كل الكروت</span>
            <strong>{stats?.total ?? 0}</strong>
          </div>
          <div className="stat-box">
            <span>يحتاج مراجعة</span>
            <strong>{stats?.needs_review ?? 0}</strong>
          </div>
          <div className="stat-box">
            <span>الشركات</span>
            <strong>{stats?.companies ?? 0}</strong>
          </div>
          <div className="stat-box">
            <span>مع بيانات اتصال</span>
            <strong>{stats ? stats.with_email + stats.with_phone : 0}</strong>
          </div>
        </div>
        <div className="button-row2" style={{ marginTop: 0 }}>
          <Link href="/upload" className="download">
            رفع كرت جديد
          </Link>
          <a
            className="download gold"
            href={`/api/cards/export-xlsx/?${exportQuery}`}
          >
            تحميل Excel
          </a>
        </div>
      </section>

      <section className="card-details">
        <div className="section-head">
          <h2>عدد الكروت حسب نوع الاستثمار</h2>
          {investmentType && (
            <button
              type="button"
              className="btn-small"
              onClick={() => {
                setPage(1);
                setInvestmentType("");
              }}
            >
              إلغاء فلتر "{investmentType}" ✕
            </button>
          )}
        </div>
        {categoryStats.length ? (
          <>
            <div className="category-stats">
              {topCategories.map((item) => (
                <CategoryChip
                  key={item.category}
                  item={item}
                  isActive={investmentType === item.category}
                  onClick={() => applyCategoryFilter(item.category)}
                />
              ))}
            </div>
            {hasMoreCategories && (
              <button
                type="button"
                className="btn-small category-toggle-more"
                onClick={() => setShowAllCategories((current) => !current)}
              >
                {showAllCategories
                  ? "إخفاء باقي أنواع الاستثمار"
                  : `عرض كل أنواع الاستثمار (${categoryStats.length})`}
              </button>
            )}
            {showAllCategories && (
              <div className="category-expanded">
                <input
                  className="category-search-input"
                  value={categoryFilterText}
                  onChange={(event) => setCategoryFilterText(event.target.value)}
                  placeholder="ابحث عن نوع استثمار ضمن القائمة الكاملة..."
                />
                <div className="category-stats category-stats-scroll">
                  {filteredCategoryStats.map((item) => (
                    <CategoryChip
                      key={item.category}
                      item={item}
                      isActive={investmentType === item.category}
                      onClick={() => applyCategoryFilter(item.category)}
                    />
                  ))}
                  {!filteredCategoryStats.length && (
                    <p className="helper-text">لا يوجد نوع استثمار مطابق لبحثك.</p>
                  )}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="helper-text">لا توجد بيانات كافية لعرض الإحصائيات بعد.</p>
        )}
      </section>

      <section className="card">
        <h2>البحث والتصفية</h2>
        <div className="grid-3">
          <label>
            ابحث بالكلام الطبيعي
            <input
              value={q}
              onChange={(event) => {
                setPage(1);
                setQ(event.target.value);
              }}
              placeholder="مثال: عرضلي شركات المياه، الشركات التركية، بدون إيميل..."
            />
          </label>
          <label>
            اسم الشركة
            <input
              value={company}
              onChange={(event) => { setPage(1); setCompany(event.target.value); }}
              placeholder="مثال: SAMIROCK"
            />
          </label>
          <label>
            نشاط الشركة
            <input
              value={activity}
              onChange={(event) => { setPage(1); setActivity(event.target.value); }}
              placeholder="تعدين، غذائية، هندسية..."
            />
          </label>
          <label>
            نوع الاستثمار
            <select
              value={investmentType}
              onChange={(event) => { setPage(1); setInvestmentType(event.target.value); }}
            >
              <option value="">الكل</option>
              {INVESTMENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label>
            من تاريخ
            <input type="date" value={createdFrom} onChange={(event) => { setPage(1); setCreatedFrom(event.target.value); }} />
          </label>
          <label>
            إلى تاريخ
            <input type="date" value={createdTo} onChange={(event) => { setPage(1); setCreatedTo(event.target.value); }} />
          </label>
          <label>
            الدولة
            <select
              value={country}
              onChange={(event) => { setPage(1); setCountry(event.target.value); }}
            >
              <option value="">كل الدول</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            حالة المراجعة
            <select
              value={needsReview}
              onChange={(event) => { setPage(1); setNeedsReview(event.target.value); }}
            >
              <option value="">الكل</option>
              <option value="true">يحتاج مراجعة</option>
              <option value="false">لا يحتاج مراجعة</option>
            </select>
          </label>
        </div>
        
        <div className="button-row">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="btn-gold"
          >
            {loading ? "جاري التحديث..." : "تحديث الجدول"}
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => {
              setPage(1);
              setQ("");
              setCompany("");
              setActivity("");
              setInvestmentType("");
              setNeedsReview("");
              setCountry("");
              setCreatedFrom("");
              setCreatedTo("");
            }}
          >
           حذف الفلترة
          </button>
          <button
            type="button"
            className="sort-toggle-button"
            disabled={loading}
            onClick={() => {
              setPage(1);
              setSortOrder((current) =>
                current === "newest" ? "oldest" : "newest",
              );
            }}
            title="تبديل ترتيب عرض الكروت"
          >
            {sortOrder === "newest"
              ? "الترتيب: الأحدث ← الأقدم"
              : "الترتيب: الأقدم ← الأحدث"}
          </button>
        </div>
        <div className="results-summary" aria-live="polite">
          <span>
            {hasActiveSearch ? "عدد نتائج البحث" : "عدد السجلات"}:
            <strong> {totalResults}</strong>
          </span>
          <span>
            المعروض حالياً: <strong>{pageStart}-{pageEnd}</strong>
          </span>
          <span>
            الترتيب الحالي: <strong>{sortOrder === "newest" ? "الأحدث أولاً" : "الأقدم أولاً"}</strong>
          </span>
          <label className="page-size-control">
            عدد الصفوف
            <select
              value={pageSize}
              onChange={(event) => {
                setPage(1);
                setPageSize(Number(event.target.value));
              }}
            >
              {PAGE_SIZE_OPTIONS.map((size) => (
                <option key={size} value={size}>{size}</option>
              ))}
            </select>
          </label>
        </div>
        {error && <p className="status-box error">{error}</p>}
      </section>

      <section className="table-wrap" aria-label="جدول بيانات الكروت">
        <table className="dashboard-table">
          <thead>
            <tr>
              <th>الكرت</th>
              <th>الشركة والنشاط</th>
              <th>بيانات الاتصال</th>
              <th>الدولة</th>
              <th>تاريخ الإضافة</th>
              <th>الحالة والترحيب</th>
              <th>إجراءات</th>
            </tr>
          </thead>
          <tbody>
            {cards.map((card) => (
              <tr key={card.id}>
                {/* الشخص: الرقم التسلسلي + الاسم + المنصب */}
                <td data-label="الكرت" className="primary-cell">
                  <div className="cell-stack">
                    <span className="seq-badge">#{card.sequence_number}</span>
                    <BilingualCell primary={card.person_name} ar={card.person_name_ar} en={card.person_name_en} />
                    <span className="cell-sub">
                      <BilingualCell primary={card.job_title} ar={card.job_title_ar} en={card.job_title_en} />
                    </span>
                  </div>
                </td>
                {/* الشركة: الاسم + النشاط + نوع الاستثمار */}
                <td data-label="الشركة والنشاط">
                  <div className="cell-stack">
                    <BilingualCell primary={card.company_name} ar={card.company_name_ar} en={card.company_name_en} />
                    {card.company_activity && (
                      <span className="cell-sub">{card.company_activity}</span>
                    )}
                    {displayInvestment(card) !== "-" && (
                      <span className="cell-chip">{displayInvestment(card)}</span>
                    )}
                  </div>
                </td>
                {/* الاتصال: الموبايل + الإيميل + الموقع */}
                <td data-label="بيانات الاتصال">
                  <div className="cell-stack">
                    <PhoneList numbers={card.mobile_numbers} />
                    {(card.emails || []).length > 0 && (
                      <span className="cell-sub ltr-text">{(card.emails || []).join(" | ")}</span>
                    )}
                    {card.website && <span className="cell-sub ltr-text">{card.website}</span>}
                  </div>
                </td>
                <td data-label="الدولة">{card.country || "-"}</td>
                <td data-label="تاريخ الإضافة" className="date-cell">
                  {(card.created_at || "").slice(0, 10) || "-"}
                </td>
                {/* الحالة + الترحيب */}
                <td data-label="الحالة والترحيب">
                  <div className="cell-stack">
                    {card.needs_review ? (
                      <span className="badge warning">مراجعة</span>
                    ) : (
                      <span className="badge success">جاهز</span>
                    )}
                    {!(card.emails || []).length ? (
                      <span className="muted-dash">—</span>
                    ) : card.welcome_status === "sent" ? (
                      // Sent: a static, non-clickable chip with no hover.
                      <span
                        className="welcome-chip sent"
                        title={`تم إرسال الترحيب${card.welcome_sent_to ? " إلى " + card.welcome_sent_to : ""}`}
                      >
                        تم الترحيب ✓
                      </span>
                    ) : (
                      // not_sent → send; failed (red) → retry.
                      <button
                        type="button"
                        className={card.welcome_status === "failed" ? "btn-small welcome-failed" : "btn-small welcome-send"}
                        disabled={welcomeBusyId === card.id}
                        onClick={() => handleWelcome(card)}
                        title={
                          card.welcome_status === "failed"
                            ? "فشل إرسال الترحيب — اضغط لإعادة المحاولة"
                            : "إرسال رسالة ترحيب إلى بريد الكرت"
                        }
                      >
                        {welcomeBusyId === card.id
                          ? "جارٍ..."
                          : card.welcome_status === "failed"
                            ? "فشل الترحيب"
                            : "إرسال ترحيب"}
                      </button>
                    )}
                  </div>
                </td>
                <td data-label="إجراءات">
                  <div className="row-actions">
                    <button
                      type="button"
                      className="btn-small"
                      onClick={() => {
                        setImageCard(card);
                        setImageError("");
                      }}
                      disabled={!hasCardImages(card)}
                      title={hasCardImages(card) ? "عرض صور الكرت" : "هذا السجل لا يحتوي على صور محفوظة"}
                    >
                      {hasCardImages(card) ? "الصور" : "لا صور"}
                    </button>
                    <button
                      type="button"
                      className="btn-small gold"
                      onClick={() => openEdit(card)}
                    >
                      تعديل
                    </button>
                    <button
                      type="button"
                      className="btn-small danger"
                      onClick={() => setDeleteCard(card)}
                    >
                      حذف
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!cards.length && (
              <tr>
                <td colSpan={7} className="empty-cell">
                  {loading
                    ? "جاري تحميل البيانات..."
                    : "لا توجد بيانات مطابقة للبحث."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      {totalPages > 1 && (
        <nav className="pagination-bar" aria-label="التنقل بين صفحات الكروت">
          <button
            type="button"
            className="btn-small"
            disabled={loading || page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            السابق
          </button>
          <span>
            صفحة <strong>{page}</strong> من <strong>{totalPages}</strong>
          </span>
          <button
            type="button"
            className="btn-small"
            disabled={loading || page >= totalPages}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            التالي
          </button>
        </nav>
      )}

      <WelcomePrompt
        open={welcomeSetupOpen}
        mode="setup"
        onSetupEmail={() => router.push('/profile')}
        onClose={() => setWelcomeSetupOpen(false)}
      />

      {welcomeErrorMsg && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="فشل إرسال الترحيب">
          <div className="modal-panel welcome-prompt" style={{ maxWidth: 440 }}>
            <div className="welcome-prompt-icon" aria-hidden="true">⚠️</div>
            <h2>تعذّر إرسال رسالة الترحيب</h2>
            <p>{welcomeErrorMsg}</p>
            <div className="button-row welcome-prompt-actions">
              <button type="button" className="btn-green" onClick={() => setWelcomeErrorMsg("")}>حسناً</button>
            </div>
          </div>
        </div>
      )}

      {imageCard && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="صور الكرت"
        >
          <div className="modal-panel image-modal">
            <div className="section-head">
              <h2>صور الكرت #{imageCard.sequence_number}</h2>
              <button
                type="button"
                className="btn-small"
                onClick={() => setImageCard(null)}
              >
                إغلاق
              </button>
            </div>
            <div className="image-modal-grid">
              <CardImageFigure
                title="الوجه الأمامي"
                url={imageCard.front_image_url}
                alt="صورة الوجه الأمامي للكرت"
                onError={() =>
                  setImageError(
                    "تعذر تحميل إحدى الصور. تأكد من إعداد MEDIA_URL وإعادة تشغيل الخادم بعد تعديل الإعدادات.",
                  )
                }
              />
              <CardImageFigure
                title="الوجه الخلفي"
                url={imageCard.back_image_url}
                alt="صورة الوجه الخلفي للكرت"
                onError={() =>
                  setImageError(
                    "تعذر تحميل إحدى الصور. تأكد من إعداد MEDIA_URL وإعادة تشغيل الخادم بعد تعديل الإعدادات.",
                  )
                }
              />
            </div>
            {imageError && (
              <p className="status-box error" style={{ marginTop: 16 }}>
                {imageError}
              </p>
            )}
          </div>
        </div>
      )}

      {deleteCard && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="تأكيد الحذف"
        >
          <div className="modal-panel" style={{ maxWidth: 420 }}>
            <div className="confirm-modal-body">
              <div className="confirm-modal-icon">🗑️</div>
              <h2>تأكيد الحذف</h2>
              <p>
                هل أنت متأكد من حذف كرت{" "}
                <strong>
                  {deleteCard.person_name || deleteCard.company_name || `#${deleteCard.sequence_number}`}
                </strong>
                ؟
              </p>
              <p>لا يمكن التراجع عن هذا الإجراء.</p>
            </div>
            <div className="button-row" style={{ marginTop: 20 }}>
              <button
                type="button"
                className="btn-small danger"
                style={{ padding: "10px 24px", fontSize: 14 }}
                onClick={confirmDelete}
                disabled={deleting}
              >
                {deleting ? "جاري الحذف..." : "نعم، احذف"}
              </button>
              <button
                type="button"
                onClick={() => setDeleteCard(null)}
                disabled={deleting}
              >
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}

      {editCard && editForm && (
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="تعديل بيانات الكرت"
        >
          <div className="modal-panel">
            <div className="section-head">
              <h2>تعديل الكرت #{editCard.sequence_number}</h2>
              <button
                type="button"
                className="btn-small"
                onClick={() => {
                  setEditCard(null);
                  setEditForm(null);
                  setEditFrontFile(null);
                  setEditBackFile(null);
                }}
              >
                إغلاق
              </button>
            </div>
            <div className="grid">
              <label className="full-width">
                اسم الشخص
                <textarea
                  value={editForm.person_name}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      person_name: event.target.value,
                    })
                  }
                  placeholder="السطر الأول عربي&#10;السطر الثاني English"
                />
              </label>
              <label className="full-width">
                المنصب
                <textarea
                  value={editForm.job_title}
                  onChange={(event) =>
                    setEditForm({ ...editForm, job_title: event.target.value })
                  }
                  placeholder="السطر الأول عربي&#10;السطر الثاني English"
                />
              </label>
              <label className="full-width">
                اسم الشركة
                <textarea
                  value={editForm.company_name}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      company_name: event.target.value,
                    })
                  }
                  placeholder="السطر الأول عربي&#10;السطر الثاني English"
                />
              </label>
              <label>
                الموبايلات
                <input
                  dir="ltr"
                  className="ltr-input"
                  value={editForm.mobile_numbers_text}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      mobile_numbers_text: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                الإيميلات
                <input
                  dir="ltr"
                  className="ltr-input"
                  value={editForm.emails_text}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      emails_text: event.target.value,
                    })
                  }
                />
              </label>
              <label>
                الموقع
                <input
                  dir="ltr"
                  className="ltr-input"
                  value={editForm.website}
                  onChange={(event) =>
                    setEditForm({ ...editForm, website: event.target.value })
                  }
                />
              </label>
              <label>
                نوع الاستثمار
                <select
                  value={editForm.investment_type}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      investment_type: event.target.value,
                    })
                  }
                >
                  <option value="">غير محدد</option>
                  {INVESTMENT_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              {editForm.investment_type === "غير ذلك" && (
                <label className="full-width">
                  غير ذلك
                  <input
                    value={editForm.investment_type_other}
                    onChange={(event) =>
                      setEditForm({
                        ...editForm,
                        investment_type_other: event.target.value,
                      })
                    }
                  />
                </label>
              )}
              <label className="full-width">
                نشاط الشركة
                <textarea
                  value={editForm.company_activity}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      company_activity: event.target.value,
                    })
                  }
                />
              </label>
              <label className="full-width">
                العنوان
                <input
                  value={editForm.address}
                  onChange={(event) =>
                    setEditForm({ ...editForm, address: event.target.value })
                  }
                />
              </label>
              <label>
                الدولة
                <input
                  value={editForm.country}
                  onChange={(event) =>
                    setEditForm({ ...editForm, country: event.target.value })
                  }
                />
              </label>
              <label className="full-width">
                ملاحظات المراجعة
                <textarea
                  value={editForm.review_notes}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      review_notes: event.target.value,
                    })
                  }
                />
              </label>
              <label className="check-row full-width">
                <input
                  type="checkbox"
                  checked={editForm.needs_review}
                  onChange={(event) =>
                    setEditForm({
                      ...editForm,
                      needs_review: event.target.checked,
                    })
                  }
                />
                يحتاج مراجعة
              </label>
              <label className="full-width">
                صورة الوجه الأمامي (اختياري)
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setEditFrontFile(e.target.files?.[0] || null)}
                />
              </label>
              <label className="full-width">
                صورة الوجه الخلفي (اختياري)
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => setEditBackFile(e.target.files?.[0] || null)}
                />
              </label>
            </div>
            <div className="button-row-saveEdit">
              <button
                type="button"
                className="btn-gold"
                onClick={saveEdit}
                disabled={saving}
              >
                {saving ? "جاري الحفظ..." : "حفظ التعديلات"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEditCard(null);
                  setEditForm(null);
                  setEditFrontFile(null);
                  setEditBackFile(null);
                }}
                disabled={saving}
              >
                إلغاء
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default function DashboardPage() {
  return (
    <__RequireAuth>
      <DashboardPageInner />
    </__RequireAuth>
  );
}
