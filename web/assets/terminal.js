(() => {
"use strict";
const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
let apiKey = "";
let portfolios = [];

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
};
const fmt = (v, d=2) => v === null || v === undefined || v === "" || !Number.isFinite(Number(v))
  ? "—" : new Intl.NumberFormat("tr-TR",{maximumFractionDigits:d}).format(Number(v));
const pct = v => v === null || v === undefined ? "—" : fmt(v) + "%";
const money = (v,c="USD") => {
  if (v === null || v === undefined || !Number.isFinite(Number(v))) return "—";
  try { return new Intl.NumberFormat("tr-TR",{style:"currency",currency:(c||"USD").toUpperCase(),notation:Math.abs(Number(v))>=1e9?"compact":"standard",maximumFractionDigits:Math.abs(Number(v))>=100?0:2}).format(Number(v)); }
  catch { return fmt(v) + " " + c; }
};
const compact = v => v === null || v === undefined ? "—" : new Intl.NumberFormat("tr-TR",{notation:"compact",maximumFractionDigits:2}).format(Number(v));
const toggle = (s,on) => $(s)?.classList.toggle("hidden",!on);
const loading = (s,on) => toggle(s,on);
function showError(s,e){const x=$(s);x.textContent=e?.message||String(e);x.classList.remove("hidden");}
function clearError(s){const x=$(s);x.textContent="";x.classList.add("hidden");}
function toast(msg){const x=$("#toast");x.textContent=msg;x.classList.remove("hidden");clearTimeout(toast.timer);toast.timer=setTimeout(()=>x.classList.add("hidden"),3500);}
async function api(path,opts={}){
  const headers=new Headers(opts.headers||{});headers.set("Accept","application/json");
  if(opts.body&&!headers.has("Content-Type"))headers.set("Content-Type","application/json");
  if(apiKey)headers.set("X-AKCA-API-Key",apiKey);
  const res=await fetch(path,{...opts,headers});const raw=await res.text();let data=null;
  try{data=raw?JSON.parse(raw):null;}catch{data={detail:raw};}
  if(!res.ok)throw new Error(data?.detail||data?.message||("HTTP "+res.status));
  return data;
}
function askKey(){
  const d=$("#api-key-dialog"),i=$("#api-key-input");i.value="";d.showModal();i.focus();
  return new Promise(resolve=>d.addEventListener("close",function closed(){
    d.removeEventListener("close",closed);
    if(d.returnValue==="save"&&i.value.trim()){apiKey=i.value.trim();resolve(true);}else resolve(false);
  }));
}
async function protectedApi(path,opts={}){
  if(!apiKey&&!(await askKey()))throw new Error("İşlem iptal edildi.");
  try{return await api(path,opts);}catch(e){
    if(/anahtar|AKCA_API_KEY|401|503/i.test(e.message)){apiKey="";if(!(await askKey()))throw e;return api(path,opts);}throw e;
  }
}
function rows(target,items){
  const host=typeof target==="string"?$(target):target;host.replaceChildren();
  const valid=items.filter(x=>x&&x[1]!==undefined);
  if(!valid.length){host.append(el("div","empty","Bu bölümde gösterilecek veri yok."));return;}
  valid.forEach(pair=>{const r=el("div","key-row");r.append(el("span","",pair[0]),el("strong","",pair[1]??"—"));host.append(r);});
}
function table(target,headers,data){
  const host=typeof target==="string"?$(target):target;host.replaceChildren();
  if(!data.length){host.append(el("div","empty","Gösterilecek veri yok."));return;}
  const wrap=el("div","table-scroll"),t=el("table","data-table"),head=el("thead"),tr=el("tr");
  headers.forEach(h=>tr.append(el("th","",h)));head.append(tr);t.append(head);
  const body=el("tbody");
  data.forEach(line=>{const r=el("tr");line.forEach(v=>r.append(el("td","",v??"—")));body.append(r);});
  t.append(body);wrap.append(t);host.append(wrap);
}
function setView(name){
  $$(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.view===name));
  $$(".view").forEach(v=>v.classList.toggle("active",v.id==="view-"+name));
  if(name==="portfolio")loadPortfolios();
  if(name==="inflation")loadBasket();
  if(name==="macro"&&!$("#macro-results").children.length)loadMacro();
  if(name==="markets"&&!$("#indices-grid").children.length)loadMarkets();
  if(name==="commodities"&&!$("#commodities-live-grid").children.length)loadCommodities();
}
$$(".nav-item").forEach(b=>b.addEventListener("click",()=>setView(b.dataset.view)));
$$("[data-open]").forEach(b=>b.addEventListener("click",()=>setView(b.dataset.open)));

function renderCompany(r){
  toggle("#company-report",true);
  const p=r.profile||{},f=r.fundamentals||{},m=f.metrics||{},d=f.derived||{},t=r.technical||{},ind=t.indicators||{},v=r.valuation||{},rec=r.recommendation||{};
  $("#report-asof").textContent="VERİ ALINDI · "+new Date(r.as_of).toLocaleString("tr-TR");
  $("#company-name").textContent=r.company_name||r.symbol;
  $("#company-meta").textContent=[r.symbol,p.exchange,p.sector,p.industry,p.currency].filter(Boolean).join(" · ");
  $("#company-action").textContent=rec.action||"BEKLE";
  $("#company-confidence").textContent="Güven: "+fmt((rec.confidence||0)*100,0)+"% · Veri bütünlüğü: "+pct(r.data_completeness_pct);
  $("#m-price").textContent=money(p.current_price,p.currency);$("#m-price-date").textContent=p.price_timestamp||"Tarih yok";
  $("#m-cap").textContent=compact(p.market_cap);$("#m-currency").textContent=p.currency||"Para birimi yok";
  $("#m-pe").textContent=fmt(v.trailing_pe_provider);$("#m-growth").textContent=pct(d.revenue_growth_yoy_pct);
  $("#m-rsi").textContent=fmt(ind.rsi_14,1);$("#m-trend").textContent=ind.trend_state||"Teknik trend —";
  $("#fundamental-status").textContent=f.status||"—";
  const fin=[
    ["Gelir",m.revenue?.latest,m.revenue?.unit],["Net kâr",m.net_income?.latest,m.net_income?.unit],
    ["Faaliyet kârı",m.operating_income?.latest,m.operating_income?.unit],
    ["Faaliyet nakit akışı",m.operating_cash_flow?.latest,m.operating_cash_flow?.unit],
    ["CapEx",m.capex?.latest,m.capex?.unit],["Serbest nakit akışı",d.free_cash_flow,m.operating_cash_flow?.unit],
    ["Toplam varlıklar",m.total_assets?.latest,m.total_assets?.unit],
    ["Toplam yükümlülükler",m.total_liabilities?.latest,m.total_liabilities?.unit],
    ["Borç / özsermaye",d.debt_to_equity,"x"],["ROE",d.return_on_equity_pct,"%"]
  ];
  const ft=el("table","data-table"),fh=el("thead"),fhr=el("tr");
  ["Finansal kalem","Son değer","Birim"].forEach(x=>fhr.append(el("th","",x)));fh.append(fhr);ft.append(fh);
  const fb=el("tbody");fin.forEach(x=>{const tr=el("tr");tr.append(el("td","",x[0]),el("td","",x[1]===null||x[1]===undefined?"—":fmt(x[1])),el("td","",x[2]||"—"));fb.append(tr);});ft.append(fb);$("#financial-table").replaceChildren(ft);
  rows("#valuation-list",[
    ["Sağlayıcı F/K",v.trailing_pe_provider],["İleri F/K",v.forward_pe_provider],
    ["FD / FAVÖK",v.enterprise_to_ebitda_provider],["Fiyat / Satış",v.price_to_sales_provider],
    ["Fiyat / Defter",v.price_to_book_provider],["Piyasa değeri / gelir",v.market_cap_to_revenue],
    ["Serbest nakit akışı verimi",pct(v.free_cash_flow_yield_pct)]
  ]);
  $("#technical-status").textContent=t.status||"—";
  rows("#technical-list",[
    ["Son fiyat",money(t.last_price,p.currency)],["SMA 50",fmt(ind.sma_50)],["SMA 200",fmt(ind.sma_200)],
    ["MACD",fmt(ind.macd_line,4)],["RSI 14",fmt(ind.rsi_14,1)],["52 hafta yüksek",fmt(ind.high_52w)],
    ["52 hafta düşük",fmt(ind.low_52w)],["1 ay getiri",pct(t.returns_pct?.["1m"])],
    ["1 yıl getiri",pct(t.returns_pct?.["1y"])],["Yıllık oynaklık",pct(t.risk?.annualized_volatility_pct)],
    ["Maksimum düşüş",pct(t.risk?.max_drawdown_2y_pct)]
  ]);
  const risk=$("#risk-list");risk.replaceChildren();
  (r.risk_flags||[]).forEach(x=>risk.append(el("div","risk-item "+(x.severity==="high"?"high":""),x.message)));
  (rec.reasons||[]).forEach(x=>risk.append(el("div","risk-item",x)));
  if(!risk.children.length)risk.append(el("div","empty","Belirlenmiş risk işareti yok; bu risksiz olduğu anlamına gelmez."));
  const c=r.institutional_consensus||{};
  rows("#consensus-list",[
    ["Doğrulanmış bağımsız rapor",c.independent_verified_record_count??0],
    ["Ortalama hedef fiyat",c.equal_weight_target_price?.mean],["Medyan hedef",c.equal_weight_target_price?.median],
    ["Doğruluk ağırlıklı hedef",c.accuracy_weighted_target_price],
    ["AL / TUT / SAT",(c.recommendation_distribution?.buy||0)+" / "+(c.recommendation_distribution?.hold||0)+" / "+(c.recommendation_distribution?.sell||0)]
  ]);
  const filings=$("#filings-list");filings.replaceChildren();
  (r.filings||[]).slice(0,12).forEach(file=>{
    const a=el("a","filing");a.href=file.url;a.target="_blank";a.rel="noopener noreferrer";
    a.append(el("span","",file.form+" · "+file.filed_at),el("small","",file.accession));filings.append(a);
  });
  if(!filings.children.length)filings.append(el("div","empty","SEC EDGAR bildirimi bulunamadı. BIST/KAP bildirimleri ayrı erişim gerektirir."));
  const checklist=r.company_research_checklist||[],ch=$("#checklist-list");ch.replaceChildren();
  const cnt={complete:0,partial:0,manual_required:0,missing:0,not_available:0};
  checklist.forEach(x=>{
    cnt[x.status]=(cnt[x.status]||0)+1;const row=el("div","check-row "+x.status);
    row.append(el("b","",String(x.step).padStart(2,"0")),el("span","",x.task),
      el("em","",x.status==="complete"?"tamam":x.status==="partial"?"kısmi":x.status==="missing"?"eksik":x.status==="not_available"?"yok":"manuel"));
    ch.append(row);
  });
  $("#checklist-summary").textContent=cnt.complete+" tamam · "+cnt.partial+" kısmi · "+cnt.manual_required+" manuel";
  const sources=$("#sources-list");sources.replaceChildren();
  (r.sources||[]).forEach(x=>{
    const box=el("div","source");box.append(el("strong","",x.source_name||x.source_id),el("span","",x.status||x.access||"—"));
    if(x.url){const a=el("a","",x.url);a.href=x.url;a.target="_blank";a.rel="noopener noreferrer";box.append(a);}
    (x.limitations||[]).forEach(n=>box.append(el("small","",n)));sources.append(box);
  });
  if(!sources.children.length)sources.append(el("div","empty","Kaynak bilgisi alınamadı."));
  const gaps=$("#evidence-gaps");gaps.replaceChildren();(r.evidence_gaps||[]).forEach(x=>gaps.append(el("div","", "• "+x)));
  $("#report-notice").textContent=r.important_notice||"İlk sürüm araştırma çıktısıdır; karar eşikleri geriye dönük testle kalibre edilmemiştir.";
}
async function runCompany(refresh=false){
  clearError("#company-error");loading("#company-loading",true);toggle("#company-report",false);
  const symbol=$("#company-symbol").value.trim().toUpperCase();
  try{renderCompany(await api("/api/research/"+encodeURIComponent(symbol)+"?refresh="+refresh));}
  catch(e){showError("#company-error",e);}finally{loading("#company-loading",false);}
}
$("#company-form").addEventListener("submit",e=>{e.preventDefault();runCompany(false);});
$("#refresh-button").addEventListener("click",()=>runCompany(true));

$("#screener-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#screener-error");loading("#screener-loading",true);toggle("#screener-results",true);
  try{
    const d=await api("/api/screener?symbols="+encodeURIComponent($("#screen-symbols").value.trim()));
    table("#screener-results",["Sembol","Şirket","Fiyat","F/K","Gelir büy.","ROE","Borç/Özsermaye","FCF verimi","Trend","Aksiyon","Veri"],
      (d.results||[]).map(x=>[x.symbol,x.company_name,money(x.price,x.currency),fmt(x.trailing_pe),pct(x.revenue_growth_yoy_pct),pct(x.return_on_equity_pct),fmt(x.debt_to_equity),pct(x.free_cash_flow_yield_pct),x.trend||"—",x.recommendation,pct(x.data_completeness_pct)]));
    (d.errors||[]).forEach(x=>$("#screener-results").append(el("div","gaps",x.symbol+": "+x.error)));
    $("#screener-results").append(el("div","notice",d.ranking_note||""));
  }catch(e){showError("#screener-error",e);}finally{loading("#screener-loading",false);}
});

function marketCards(target,data){
  const host=$(target);host.replaceChildren();
  (data||[]).forEach(x=>{
    const card=el("article","market-card");
    card.append(el("span","market-name",x.name||x.symbol),el("strong","market-price",money(x.last_price,x.currency||"USD")),
      el("span","market-change "+((x.change_pct||0)>=0?"positive":"negative"),x.change_pct===null||x.change_pct===undefined?"—":pct(x.change_pct)),
      el("small","market-detail",x.status==="ok"?x.symbol+" · "+(x.as_of||"tarih yok"):x.symbol+" · veri alınamadı"));
    host.append(card);
  });
  if(!host.children.length)host.append(el("div","empty","Piyasa verisi dönmedi."));
}
async function loadMarkets(){
  clearError("#markets-error");loading("#markets-loading",true);
  try{
    const pair=await Promise.all([api("/api/markets?group=indices&period=6mo"),api("/api/markets?group=fx&period=6mo")]);
    marketCards("#indices-grid",pair[0].results);marketCards("#fx-grid",pair[1].results);
    $("#markets-asof").textContent="ALINDI · "+new Date().toLocaleString("tr-TR");
  }catch(e){showError("#markets-error",e);}finally{loading("#markets-loading",false);}
}
$("#markets-load").addEventListener("click",loadMarkets);
async function loadCommodities(){
  clearError("#commodities-error");loading("#commodities-loading",true);
  try{const d=await api("/api/markets?group=commodities&period=6mo");marketCards("#commodities-live-grid",d.results);}
  catch(e){showError("#commodities-error",e);}finally{loading("#commodities-loading",false);}
}
$("#commodities-live-load").addEventListener("click",loadCommodities);
$("#commodities-history-load").addEventListener("click",async()=>{
  clearError("#commodities-error");loading("#commodities-loading",true);
  try{
    const d=await api("/api/commodities/world-bank?limit=36");const host=$("#commodities-history-content");host.replaceChildren();
    const data=(d.series||[]).map(s=>{const a=s.observations||[],z=a[a.length-1],p=a[a.length-2];return[s.name,z?.period,fmt(z?.price_usd),p?.period,fmt(p?.price_usd)];});
    table(host,["Emtia","Son dönem","Fiyat USD","Önceki dönem","Önceki fiyat"],data);
    if(d.source?.url){const a=el("a","small-link","World Bank kaynak dosyası ↗");a.href=d.source.url;a.target="_blank";a.rel="noopener noreferrer";host.append(a);}
    toggle("#commodities-history",true);
  }catch(e){showError("#commodities-error",e);}finally{loading("#commodities-loading",false);}
});

$("#crypto-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#crypto-error");
  try{
    const d=await api("/api/crypto/search?q="+encodeURIComponent($("#crypto-query").value.trim()));
    const host=$("#crypto-results");host.replaceChildren();
    (d.coins||[]).forEach(c=>{
      const b=el("button","crypto-choice");b.type="button";
      b.append(el("strong","",c.name+" ("+c.symbol+")"),el("small","","CoinGecko ID: "+c.id+" · sıra: "+(c.market_cap_rank??"—")));
      b.addEventListener("click",()=>loadCoin(c.id));host.append(b);
    });
    if(!host.children.length)host.append(el("div","empty","Eşleşen varlık bulunamadı."));
  }catch(e){showError("#crypto-error",e);}
});
async function loadCoin(id){
  try{
    const d=await api("/api/crypto/"+encodeURIComponent(id)+"?currency=usd");
    const host=$("#crypto-detail");host.replaceChildren();host.append(el("h3","",d.name+" ("+d.symbol+")"));
    const grid=el("div","crypto-detail-grid");
    [["Fiyat",money(d.current_price,"USD")],["Piyasa değeri",money(d.market_cap,"USD")],["24 saat",pct(d.price_change_24h_pct)],["7 gün",pct(d.price_change_7d_pct)],["30 gün",pct(d.price_change_30d_pct)],["1 yıl",pct(d.price_change_1y_pct)],["24s yüksek",money(d.high_24h,"USD")],["24s düşük",money(d.low_24h,"USD")]].forEach(x=>{const c=el("div","metric");c.append(el("span","",x[0]),el("strong","",x[1]));grid.append(c);});
    host.append(grid,el("div","muted","Son güncelleme: "+(d.last_updated||"—")+" · CoinGecko"));toggle("#crypto-detail",true);
  }catch(e){showError("#crypto-error",e);}
}

$("#macro-load").addEventListener("click",loadMacro);
async function loadMacro(){
  clearError("#macro-error");const host=$("#macro-results");host.replaceChildren();
  try{
    const d=await api("/api/macro?series=FEDFUNDS,DGS10,CPIAUCSL,UNRATE,DEXUSAL&observations=24");
    if(d.status==="not_configured"){host.append(el("div","notice","FRED_API_KEY tanımlı değil. ABD makro serileri için FRED API anahtarı sunucu .env dosyasına eklenmeli."));return;}
    (d.series||[]).forEach(s=>{const c=el("div","metric");c.append(el("span","",s.name||s.series_id),el("strong","",fmt(s.latest?.value)),el("small","",(s.latest?.date||"—")+" · "+s.series_id));host.append(c);});
    if(!host.children.length)host.append(el("div","empty","FRED serisi dönmedi."));
  }catch(e){showError("#macro-error",e);}
}
$("#evds-load").addEventListener("click",async()=>{
  clearError("#macro-error");const host=$("#evds-results");host.replaceChildren();
  try{
    const d=await api("/api/evds");
    if(d.status==="not_configured")host.append(el("div","notice","TCMB_EVDS_API_KEY tanımlı değil. EVDS hesabından ücretsiz API anahtarı alıp sunucu .env dosyasına ekle."));
    else (d.series||[]).forEach(s=>{const r=el("div","key-row");r.append(el("span","",s.name),el("strong","",(s.latest?fmt(s.latest.value):"—")+" · "+(s.latest?.date||"—")));host.append(r);});
    toggle("#evds-results",true);
  }catch(e){showError("#macro-error",e);}
});

async function loadPortfolios(){
  try{
    portfolios=await protectedApi("/api/portfolios");const s=$("#portfolio-select");s.replaceChildren();
    portfolios.forEach(p=>{const o=el("option","",p.name);o.value=p.portfolio_id;s.append(o);});
  }catch(e){showError("#portfolio-error",e);}
}
$("#portfolio-create-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#portfolio-error");
  try{
    await protectedApi("/api/portfolios",{method:"POST",body:JSON.stringify({name:$("#portfolio-name").value.trim(),base_currency:$("#portfolio-currency").value.trim().toUpperCase()})});
    toast("Portföy oluşturuldu.");await loadPortfolios();
  }catch(e){showError("#portfolio-error",e);}
});
$("#position-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#portfolio-error");const id=$("#portfolio-select").value;
  if(!id){showError("#portfolio-error",new Error("Önce portföy oluştur."));return;}
  try{
    await protectedApi("/api/portfolios/"+encodeURIComponent(id)+"/positions",{method:"POST",body:JSON.stringify({
      symbol:$("#position-symbol").value.trim().toUpperCase(),quantity:Number($("#position-quantity").value),
      average_cost:$("#position-cost").value?Number($("#position-cost").value):null
    })});
    toast("Pozisyon kaydedildi.");await loadPortfolioAnalysis(id);
  }catch(e){showError("#portfolio-error",e);}
});
$("#portfolio-select").addEventListener("change",e=>loadPortfolioAnalysis(e.target.value));
async function loadPortfolioAnalysis(id){
  if(!id)return;
  try{
    const d=await protectedApi("/api/portfolios/"+encodeURIComponent(id)+"/analysis");const host=$("#portfolio-results");host.replaceChildren();
    host.append(el("h3","","Portföy görünümü"));
    (d.warnings||[]).forEach(w=>host.append(el("div","notice",w)));
    table(host,["Sembol","Adet","Fiyat","Para birimi","Piyasa değeri","Ağırlık"],(d.positions||[]).map(p=>[p.symbol,p.quantity??"—",fmt(p.price),p.currency||"—",fmt(p.market_value),pct(p.weight_pct)]));
    toggle("#portfolio-results",true);
  }catch(e){showError("#portfolio-error",e);}
}

$("#broker-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#broker-error");
  try{
    await protectedApi("/api/institutional/research",{method:"POST",body:JSON.stringify({
      symbol:$("#broker-symbol").value.trim().toUpperCase(),institution:$("#broker-institution").value.trim(),analyst:null,
      recommendation:$("#broker-rating").value,target_price:$("#broker-target").value?Number($("#broker-target").value):null,
      currency:$("#broker-currency").value.trim().toUpperCase()||null,published_at:$("#broker-date").value,
      report_url:$("#broker-url").value.trim(),source_name:$("#broker-source").value.trim(),
      dependency_group:$("#broker-dependency").value.trim()||null,verified:$("#broker-verified").checked,
      reference_price_at_publication:$("#broker-reference").value?Number($("#broker-reference").value):null
    })});
    toast("Kurum araştırması kaydedildi.");$("#broker-consensus-symbol").value=$("#broker-symbol").value;
  }catch(e){showError("#broker-error",e);}
});
$("#broker-consensus-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#broker-error");const symbol=$("#broker-consensus-symbol").value.trim().toUpperCase();
  try{
    const d=await api("/api/institutional/consensus/"+encodeURIComponent(symbol));const host=$("#broker-consensus-results");host.replaceChildren();
    host.append(el("h3","",symbol+" · Kurum konsensüsü"));
    rows(host,[
      ["Tüm kayıt",d.all_records_count],["Doğrulanmış kayıt",d.verified_records_count],["Bağımsız rapor",d.independent_verified_record_count],
      ["Ortalama hedef",d.equal_weight_target_price?.mean],["Medyan hedef",d.equal_weight_target_price?.median],
      ["Doğruluk ağırlıklı hedef",d.accuracy_weighted_target_price],
      ["AL / TUT / SAT",(d.recommendation_distribution?.buy||0)+" / "+(d.recommendation_distribution?.hold||0)+" / "+(d.recommendation_distribution?.sell||0)]
    ]);
    (d.methodology_notes||[]).forEach(n=>host.append(el("div","notice",n)));toggle("#broker-consensus-results",true);
  }catch(e){showError("#broker-error",e);}
});

$("#ipo-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#ipo-error");
  try{
    await protectedApi("/api/ipo",{method:"POST",body:JSON.stringify({
      symbol:$("#ipo-symbol").value.trim().toUpperCase(),company_name:$("#ipo-company").value.trim(),offer_date:$("#ipo-date").value,
      offer_price:Number($("#ipo-price").value),offer_currency:$("#ipo-currency").value.trim().toUpperCase(),
      source_url:$("#ipo-url").value.trim(),source_name:$("#ipo-source").value.trim(),verified:$("#ipo-verified").checked
    })});
    toast("Halka arz kaydı eklendi.");$("#ipo-query-symbol").value=$("#ipo-symbol").value;
  }catch(e){showError("#ipo-error",e);}
});
$("#ipo-query-form").addEventListener("submit",async e=>{
  e.preventDefault();clearError("#ipo-error");const sym=$("#ipo-query-symbol").value.trim().toUpperCase();
  try{
    const d=await api("/api/ipo/"+encodeURIComponent(sym));const host=$("#ipo-results");host.replaceChildren();
    host.append(el("h3","",d.company_name+" ("+d.symbol+")"));
    rows(host,[["Halka arz tarihi",d.offer_date],["Halka arz fiyatı",money(d.offer_price,d.offer_currency)],["Güncel fiyat",money(d.current_price,d.current_currency)],["Nominal getiri",pct(d.offer_to_current_return_pct)],["Halka arz kaydı doğrulandı",d.offer_data_verified?"Evet":"Hayır"]]);
    (d.warnings||[]).forEach(w=>host.append(el("div","notice",w)));toggle("#ipo-results",true);
  }catch(e){showError("#ipo-error",e);}
});

async function loadBasket(){
  try{
    const d=await api("/api/weights/status");$("#basket-count").textContent=d.item_count??"409";
    $("#basket-weight").textContent=(d.verified_item_weight_count??0)+"/"+(d.item_count??409);
    $("#basket-status").textContent=d.ready?"HAZIR":"KİLİTLİ";
    $("#basket-notice").textContent=d.ready
      ?"Ağırlıklar ve varyant temsilleri doğrulanmış. Yeterli cari/önceki ay satıcı fiyatı geldiğinde hesaplanabilir."
      :"Endeks kilitli: "+(d.items_missing_or_unverified?.length??0)+" madde ağırlığı doğrulanmamış; "+(d.items_with_incomplete_variant_weights?.length??0)+" maddede varyant temsili eksik.";
  }catch(e){$("#basket-notice").textContent=e.message;}
}
async function health(){
  const status=$("#connection-status");
  try{
    const d=await api("/health");status.replaceChildren(el("i"));
    status.append(document.createTextNode(" AKÇA API "+(d.version||"")+" · "+(d.reference_item_count??0)+" madde"));
    status.classList.remove("bad");
    if(!d.write_api_enabled)status.title="Yazma işlemleri için .env içine AKCA_API_KEY eklenmeli.";
  }catch(e){status.textContent="API bağlantısı yok";status.classList.add("bad");toast("Terminal arayüzü açıldı; FastAPI sunucusu çalışmıyor.");}
}
$("#api-key-save").addEventListener("click",()=>{});
health();loadBasket();runCompany(false);
if($("#broker-date")&&!$("#broker-date").value)$("#broker-date").value=new Date().toISOString().slice(0,10);
})();