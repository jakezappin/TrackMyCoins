import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { Coin } from "../api";
import CoinPlaceholder from "./CoinPlaceholder";
import { useApp } from "../App";
import { coinPath, dateMint, metalFor, serviceLabel, gradeLabel, money, profit, setLineName, shortDate, slabLabel, toningLabel } from "../format";

type SortKey = "inventory" | "date" | "grade" | "paid" | "cpg" | "sold";

interface Props {
  coins: Coin[];
  mode: "collection" | "sold";
}

export default function CoinTable({ coins, mode }: Props) {
  const navigate = useNavigate();
  const { coinTypes } = useApp();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "toned" | "cac" | "slab">("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({
    key: mode === "sold" ? "sold" : "date",
    dir: mode === "sold" ? -1 : 1,
  });

  // Mint & proof sets aren't graded: their "grade" column shows which set.
  const setTypeIds = useMemo(() => new Set(coinTypes.filter((t) => t.is_set).map((t) => t.id)), [coinTypes]);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = coins.filter((c) => {
      if (filter === "toned" && toningLabel(c).length === 0) return false;
      if (filter === "cac" && !c.cac) return false;
      if (filter === "slab" && slabLabel(c).length === 0) return false;
      if (!q) return true;
      const hay = [
        c.inventory_number,
        dateMint(c),
        gradeLabel(c),
        c.grading_service,
        c.cert_number,
        c.vam,
        c.purchased_from,
        c.sold_to,
        c.notes,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
    const val = (c: Coin): number | string => {
      switch (sort.key) {
        case "inventory":
          return c.inventory_number;
        case "date":
          return (c.year ?? 0) * 100 + "PCCDOS".indexOf(c.mint_mark);
        case "grade":
          return (c.grade ?? 0) + (c.grade_plus ? 0.5 : 0);
        case "paid":
          return Number(c.price_paid ?? -1);
        case "cpg":
          return Number(c.value_estimate ?? -1);
        case "sold":
          return c.sale_date ?? "";
      }
    };
    return [...filtered].sort((a, b) => {
      const va = val(a);
      const vb = val(b);
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
    });
  }, [coins, query, filter, sort]);

  const th = (key: SortKey, label: string, className = "") => (
    <th
      className={`sortable ${className}`}
      aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        className="sort-btn"
        onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : 1 }))}
      >
        {label}
        {sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  const sortOptions: [SortKey, string][] = [
    ["date", "Date"],
    ["inventory", "Inventory #"],
    ["grade", "Grade"],
    ["paid", "Price paid"],
    ...(mode === "collection" ? ([["cpg", "Value"]] as [SortKey, string][]) : ([["sold", "Sold on"]] as [SortKey, string][])),
  ];

  return (
    <div className="card table-card">
      <div className="table-toolbar">
        <input
          className="search"
          placeholder="Search date, grade, cert, VAM, notes…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label className="mobile-sort">
          <span className="small muted">Sort by</span>
          <select
            value={`${sort.key}:${sort.dir}`}
            onChange={(e) => {
              const [key, dir] = e.target.value.split(":");
              setSort({ key: key as SortKey, dir: Number(dir) as 1 | -1 });
            }}
          >
            {sortOptions.flatMap(([k, label]) => [
              <option key={`${k}:1`} value={`${k}:1`}>{label} ▲</option>,
              <option key={`${k}:-1`} value={`${k}:-1`}>{label} ▼</option>,
            ])}
          </select>
        </label>
        <div className="chips">
          {(["all", "toned", "cac", "slab"] as const).map((f) => (
            <button key={f} className={`chip ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>
              {{ all: "All", toned: "Toned", cac: "CAC", slab: "Collector slab" }[f]}
            </button>
          ))}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="muted empty">{coins.length === 0 ? "No coins yet." : "No coins match."}</p>
      ) : (
        <div className="table-scroll">
          <table className={`coin-table ${mode}`}>
            <thead>
              <tr>
                <th className="thumb-col" />
                {th("inventory", "Inv #")}
                {th("date", "Date")}
                {th("grade", "Grade")}
                <th>Service</th>
                <th>Tags</th>
                {th("paid", "Paid", "num")}
                {mode === "collection" ? th("cpg", "Value", "num") : null}
                {mode === "sold" ? (
                  <>
                    <th className="num">Sold for</th>
                    {th("sold", "Sold on")}
                    <th className="num">P/L</th>
                  </>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => {
                const pl = profit(c);
                return (
                  <tr key={c.id} onClick={() => navigate(coinPath(c.inventory_number))}>
                    <td className="thumb-col c-thumb">
                      {c.thumbnail_url ? <img src={c.thumbnail_url} alt="" className="thumb" loading="lazy" /> : <CoinPlaceholder className="thumb ph" metal={metalFor(coinTypes, c.coin_type_id)} />}
                    </td>
                    <td className="mono c-inv">
                      {/* A real link, so rows can be reached and opened from the keyboard */}
                      <Link to={coinPath(c.inventory_number)} className="row-link" onClick={(e) => e.stopPropagation()}>
                        {c.inventory_number}
                      </Link>
                    </td>
                    <td className="strong c-date">
                      {dateMint(c)}
                      {c.vam && <span className="sub"> {c.vam}</span>}
                    </td>
                    <td className="c-grade">{setTypeIds.has(c.coin_type_id) ? setLineName(c.variety) : gradeLabel(c)}</td>
                    <td className="c-svc">
                      {setTypeIds.has(c.coin_type_id) ? "—" : serviceLabel(c.grading_service)}
                      {c.cert_number && <span className="sub mono"> {c.cert_number}</span>}
                    </td>
                    <td className="c-tags">
                      <div className="tags">
                        {c.location === "grading" && <span className="tag grading">At grading</span>}
                        {c.cac && <span className={`tag cac-${c.cac_sticker ?? "green"}`}>CAC</span>}
                        {toningLabel(c).length > 0 && <span className="tag toned">Toned</span>}
                        {slabLabel(c).map((s) => (
                          <span key={s} className="tag slab">
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="num c-paid" data-label="Paid">{money(c.price_paid)}</td>
                    {mode === "collection" && (
                      <td className="num c-value" data-label="Value">
                        {money(c.value_estimate)}
                        {c.value_source === "custom" ? (
                          <span className="value-tag" title="Your own value">own</span>
                        ) : c.toner_premium || c.holder_premium ? (
                          <span
                            className="value-tag"
                            title={[
                              c.toner_premium && `toner premium ${money(c.toner_premium)}`,
                              c.holder_premium && `holder premium ${money(c.holder_premium)}`,
                            ]
                              .filter(Boolean)
                              .join(" + ")}
                          >
                            {[c.toner_premium && "+toner", c.holder_premium && "+holder"].filter(Boolean).join(" ")}
                          </span>
                        ) : null}
                      </td>
                    )}
                    {mode === "sold" && (
                      <>
                        <td className="num c-soldfor" data-label="Sold for">{money(c.sale_price)}</td>
                        <td className="c-soldon" data-label="Sold">{shortDate(c.sale_date)}</td>
                        <td className={`num c-pl ${pl == null ? "" : pl >= 0 ? "pos" : "neg"}`} data-label="P/L">
                          {pl == null ? "—" : money(pl)}
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
