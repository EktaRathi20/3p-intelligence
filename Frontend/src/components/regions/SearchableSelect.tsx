import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Loader2, Search, X } from "lucide-react";

interface SearchableSelectProps<T> {
  id: string;
  label: string;
  required?: boolean;
  value: T | null;
  options: T[];
  getKey: (item: T) => string;
  getLabel: (item: T) => string;
  getSublabel?: (item: T) => string | null;
  onChange: (item: T | null) => void;
  placeholder?: string;
  disabled?: boolean;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  emptyMessage?: string;
  hint?: string;
  allowClear?: boolean;
  // Server-side search: when onSearchTextChange is provided, the parent
  // owns filtering and `options` already reflects the query.
  searchText?: string;
  onSearchTextChange?: (text: string) => void;
  searching?: boolean;
  totalCount?: number;
  hasMore?: boolean;
  onLoadMore?: () => void;
  loadingMore?: boolean;
}

export default function SearchableSelect<T>({
  id,
  label,
  required,
  value,
  options,
  getKey,
  getLabel,
  getSublabel,
  onChange,
  placeholder,
  disabled,
  loading,
  error,
  onRetry,
  emptyMessage,
  hint,
  allowClear,
  searchText,
  onSearchTextChange,
  searching,
  totalCount,
  hasMore,
  onLoadMore,
  loadingMore,
}: SearchableSelectProps<T>) {
  const [open, setOpen] = useState(false);
  const [internalQuery, setInternalQuery] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const serverSide = onSearchTextChange !== undefined;
  const query = serverSide ? (searchText ?? "") : internalQuery;

  const visibleOptions = useMemo(() => {
    if (serverSide) return options;
    const needle = internalQuery.trim().toLowerCase();
    if (!needle) return options;
    return options.filter((item) => {
      const haystack =
        `${getLabel(item)} ${getSublabel?.(item) ?? ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [serverSide, options, internalQuery, getLabel, getSublabel]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open ]);

  useEffect(() => {
    if (open) {
      setInternalQuery("");
      window.setTimeout(() => searchRef.current?.focus(), 0);
    }
  }, [open ]);

  const selectedKey = value ? getKey(value) : null;

  return (
    <div ref={containerRef} className="relative">
      <label
        htmlFor={`${id}-button`}
        className="block text-sm font-medium text-slate-700"
      >
        {label} {required && <span className="text-red-600">*</span>}
      </label>

      <div className="mt-1 flex gap-2">
        <button
          id={`${id}-button`}
          type="button"
          disabled={disabled || loading}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
          className="flex w-full items-center justify-between gap-2 border border-slate-300 bg-white px-3 py-2.5 text-left text-sm outline-none hover:border-slate-400 focus:border-[#18365b] focus:ring-1 focus:ring-[#18365b] disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
        >
          <span className="min-w-0 flex-1 truncate">
            {loading ? (
              <span className="inline-flex items-center gap-2 text-slate-500">
                <Loader2 size={15} className="animate-spin" />
                Loading...
              </span>
            ) : value ? (
              getLabel(value)
            ) : (
              <span className="text-slate-400">
                {placeholder ?? `Select ${label.toLowerCase()}`}
              </span>
            )}
          </span>
          <ChevronDown
            size={16}
            className={`shrink-0 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>

        {allowClear && value && !disabled && (
          <button
            type="button"
            aria-label={`Clear ${label}`}
            onClick={() => onChange(null)}
            className="border border-slate-300 bg-white px-2.5 text-slate-500 hover:bg-slate-50 hover:text-slate-700"
          >
            <X size={16} />
          </button>
        )}
      </div>

      {hint && !error && (
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
      )}

      {error && !open && (
        <p className="mt-1 flex items-center gap-2 text-xs text-red-700">
          <span className="flex-1">{error}</span>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="font-semibold underline hover:text-red-900"
            >
              Retry
            </button>
          )}
        </p>
      )}

      {open && !disabled && (
        <div className="absolute z-30 mt-1 max-h-72 w-full overflow-hidden border border-slate-300 bg-white shadow-lg">
          <div className="border-b border-slate-200 p-2">
            <div className="flex items-center gap-2 border border-slate-300 bg-white px-2">
              {searching ? (
                <Loader2 size={15} className="animate-spin text-slate-400" />
              ) : (
                <Search size={15} className="text-slate-400" />
              )}
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => {
                  if (serverSide) {
                    onSearchTextChange(event.target.value);
                  } else {
                    setInternalQuery(event.target.value);
                  }
                }}
                placeholder={`Search ${label.toLowerCase()}...`}
                aria-label={`Search ${label}`}
                className="w-full py-2 text-sm outline-none"
              />
            </div>
            {serverSide && totalCount !== undefined && (
              <p className="mt-1 px-1 text-xs text-slate-500">
                Showing {options.length} of {totalCount}
              </p>
            )}
          </div>

          <div
            role="listbox"
            aria-label={label}
            className="max-h-48 overflow-y-auto"
          >
            {error ? (
              <div className="p-3 text-sm text-red-700">
                <p>{error}</p>
                {onRetry && (
                  <button
                    type="button"
                    onClick={onRetry}
                    className="mt-1 font-semibold underline hover:text-red-900"
                  >
                    Retry
                  </button>
                )}
              </div>
            ) : visibleOptions.length === 0 ? (
              <p className="p-3 text-sm text-slate-500">
                {emptyMessage ?? `No ${label.toLowerCase()} found.`}
              </p>
            ) : (
              visibleOptions.map((item) => {
                const key = getKey(item);
                const selected = key === selectedKey;
                const sublabel = getSublabel?.(item);
                return (
                  <button
                    key={key}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => {
                      onChange(item);
                      setOpen(false);
                    }}
                    className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-slate-100 ${
                      selected ? "bg-[#eaf0f7] font-semibold text-[#18365b]" : ""
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate">{getLabel(item)}</span>
                      {sublabel && (
                        <span className="block truncate text-xs font-normal text-slate-500">
                          {sublabel}
                        </span>
                      )}
                    </span>
                    {selected && <Check size={15} className="shrink-0" />}
                  </button>
                );
              })
            )}
          </div>

          {hasMore && onLoadMore && (
            <div className="border-t border-slate-200 p-2">
              <button
                type="button"
                disabled={loadingMore}
                onClick={onLoadMore}
                className="flex w-full items-center justify-center gap-2 border border-slate-300 bg-slate-50 px-3 py-2 text-sm font-semibold text-[#18365b] hover:bg-slate-100 disabled:opacity-50"
              >
                {loadingMore && (
                  <Loader2 size={15} className="animate-spin" />
                )}
                Load more
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
