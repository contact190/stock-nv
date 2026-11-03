/**
 * DASHBOARD.JS - MÉTROLOGIE FINANCIÈRE AU PMP & FILTRES TEMPORELS
 * Filtres disponibles :
 * - Périodes : Toutes, Cette Semaine, Ce Mois-ci, Cette Année, Personnalisé
 * - Commandes & Lots : Vue globale ou restreinte à un lot / commande
 */

window.timelineChartInstance = null;
window.categoryChartInstance = null;

// Gestion des filtres temporels
function setDashboardPeriod(period) {
  AppState.dashboardPeriod = period;

  const periods = ['ALL', 'WEEK', 'MONTH', 'YEAR', 'CUSTOM'];
  periods.forEach(p => {
    const btn = document.getElementById(`btnPeriod-${p}`);
    if (btn) {
      if (p === period) {
        btn.className = 'period-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow-sm transition-all flex items-center gap-1';
      } else {
        btn.className = 'period-btn px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 border border-slate-200 dark:border-slate-800 transition-all flex items-center gap-1';
      }
    }
  });

  const customBox = document.getElementById('customDateRangeBox');
  if (period === 'CUSTOM') {
    customBox?.classList.remove('hidden');
  } else {
    customBox?.classList.add('hidden');
    refreshDashboard();
  }

  if (window.lucide) {
    lucide.createIcons();
  }
}

function applyCustomDateFilter() {
  const start = document.getElementById('dashCustomStart')?.value;
  const end = document.getElementById('dashCustomEnd')?.value;

  if (!start && !end) {
    showToast("Veuillez choisir une date de début ou de fin", "warning");
    return;
  }

  AppState.dashboardStartDate = start || '';
  AppState.dashboardEndDate = end || '';
  refreshDashboard();
}

async function refreshDashboard() {
  try {
    await loadDashboardOrderOptions();

    const selectedOrder = document.getElementById('dashboardOrderFilter')?.value || 'ALL';
    const period = AppState.dashboardPeriod || 'ALL';

    const params = new URLSearchParams();
    params.set('period', period);

    if (period === 'CUSTOM') {
      const start = AppState.dashboardStartDate || document.getElementById('dashCustomStart')?.value;
      const end = AppState.dashboardEndDate || document.getElementById('dashCustomEnd')?.value;
      if (start) params.set('start_date', start);
      if (end) params.set('end_date', end);
    }

    if (selectedOrder && selectedOrder !== 'ALL') {
      params.set('orders', selectedOrder);
    }

    const res = await fetch(`/api/dashboard/metrics?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur lors du calcul des métriques');
    const data = await res.json();

    updateDashboardKPIs(data.kpis);
    renderLowStockAlerts(data.alerts, data.unassigned_locations);
    renderDashboardInventoryAnomalies(data.inventory_anomalies_alerts, data.kpis.inventory_anomalies_count);
    renderTimelineChart(data.charts.timeline);
    renderCategoryChart(data.charts.categories);

  } catch (err) {
    console.error('Erreur refreshDashboard:', err);
    showToast('Erreur de synchronisation du Dashboard', 'error');
  }
}

async function loadDashboardOrderOptions() {
  const select = document.getElementById('dashboardOrderFilter');
  if (!select) return;

  const currentVal = select.value || 'ALL';
  try {
    const res = await fetch('/api/dashboard/orders-list');
    if (res.ok) {
      const data = await res.json();
      const orders = data.orders || [];

      let html = '<option value="ALL">📦 Toutes les commandes & lots (Vue Globale)</option>';

      if (orders.length > 0) {
        html += '<optgroup label="Commandes & Lots">';
        orders.forEach(o => {
          const emoji = o.status === 'DESTOCKED' ? '✅' : (o.status === 'RESERVEE' ? '🔒' : '⏳');
          html += `<option value="${o.order_number}">${emoji} ${o.order_number} (${o.client_name})</option>`;
        });
        html += '</optgroup>';
      }

      select.innerHTML = html;
      select.value = currentVal;
    }
  } catch (err) {
    console.error('Erreur chargement liste des commandes:', err);
  }
}

function onDashboardOrderFilterChange() {
  refreshDashboard();
}

function updateDashboardKPIs(kpis) {
  if (!kpis) return;

  const elTotalPurchase = document.getElementById('kpiTotalPurchase');
  if (elTotalPurchase) elTotalPurchase.textContent = formatMoney(kpis.total_purchase_value);

  const elRealStockVal = document.getElementById('kpiRealStockVal');
  if (elRealStockVal) elRealStockVal.textContent = formatMoney(kpis.real_stock_value);

  const elRealQty = document.getElementById('kpiRealQty');
  if (elRealQty) elRealQty.textContent = `${kpis.total_real_quantity}`;

  const elAvailQty = document.getElementById('kpiAvailableQty');
  if (elAvailQty) elAvailQty.textContent = `${kpis.available_quantity}`;

  const elDestockedVal = document.getElementById('kpiDestockedVal');
  if (elDestockedVal) elDestockedVal.textContent = formatMoney(kpis.destocked_value);

  const elReservedVal = document.getElementById('kpiReservedVal');
  if (elReservedVal) elReservedVal.textContent = formatMoney(kpis.total_reserved_value);

  const elLowStockCount = document.getElementById('kpiLowStockCount');
  if (elLowStockCount) elLowStockCount.textContent = `${kpis.low_stock_count}`;

  const elUnassigned = document.getElementById('kpiUnassignedCount');
  if (elUnassigned) elUnassigned.textContent = `${kpis.unassigned_location_count} sans casier`;

  // Badges barre latérale
  const sideAlerts = document.getElementById('sideAlertsCount');
  if (sideAlerts) sideAlerts.textContent = `${kpis.low_stock_count}`;

  const sideUnassigned = document.getElementById('sideUnassignedCount');
  if (sideUnassigned) sideUnassigned.textContent = `${kpis.unassigned_location_count}`;

  const sideReal = document.getElementById('sideRealVal');
  if (sideReal) sideReal.textContent = formatMoney(kpis.real_stock_value);

  const sideInvAnom = document.getElementById('sideInventoryAnomaliesCount');
  if (sideInvAnom) sideInvAnom.textContent = `${kpis.inventory_anomalies_count || 0}`;
}

function renderDashboardInventoryAnomalies(anomalies, count) {
  const container = document.getElementById('dashboardInventoryAnomaliesSection');
  const tbody = document.getElementById('dashboardInventoryAnomaliesBody');
  const badgeCount = document.getElementById('dashInvAnomaliesBadge');
  if (!container || !tbody) return;

  if (badgeCount) badgeCount.textContent = `${count || 0} anomalie(s)`;

  if (!anomalies || anomalies.length === 0) {
    container.classList.add('hidden');
    return;
  }

  container.classList.remove('hidden');

  let html = '';
  anomalies.forEach(a => {
    html += `
      <tr class="bg-rose-50/60 dark:bg-rose-950/30 hover:bg-rose-100/50 dark:hover:bg-rose-950/50 border-b border-rose-200/60 dark:border-rose-900/40 transition-colors">
        <td class="p-3">
          <div class="flex items-center gap-2.5">
            <span class="w-3.5 h-3.5 rounded-full shrink-0 shadow-sm border border-slate-300 dark:border-slate-600" style="background-color: ${a.color_hex};"></span>
            <div>
              <div class="font-bold text-sm text-slate-900 dark:text-white font-mono">${a.reference}</div>
              <div class="text-xs text-slate-500">${a.designation} (${a.color})</div>
            </div>
          </div>
        </td>
        <td class="p-3 text-right font-mono font-bold text-slate-800 dark:text-slate-200">
          ${a.real_quantity} <span class="text-[11px] font-normal text-slate-400">${a.unit}</span>
        </td>
        <td class="p-3 text-center text-xs">
          <div class="font-mono">
            <span class="text-slate-600 dark:text-slate-400">${a.person1_name}:</span> <span class="font-bold">${a.count1 !== null ? a.count1 : '—'}</span>
            <span class="mx-1 text-slate-300">|</span>
            <span class="text-slate-600 dark:text-slate-400">${a.person2_name}:</span> <span class="font-bold">${a.count2 !== null ? a.count2 : '—'}</span>
          </div>
        </td>
        <td class="p-3 text-center">
          <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-200 border border-rose-300 dark:border-rose-700">
            <i data-lucide="alert-triangle" class="w-3.5 h-3.5 text-rose-600"></i>
            ${a.issue_label}
          </span>
        </td>
        <td class="p-3 text-right">
          <div class="flex items-center justify-end gap-2">
            <!-- Bouton Refaire l'inventaire -->
            <button 
              onclick="recountFromDashboard(${a.variant_id})" 
              class="px-2.5 py-1.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5 transition-all"
              title="Réinitialiser pour recomptage par les 2 personnes"
            >
              <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
              <span>Refaire l'inventaire</span>
            </button>
            <!-- Bouton Mettre à niveau vers quantité d'inventaire -->
            <button 
              onclick="adjustFromDashboard(${a.variant_id})" 
              class="px-2.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5 transition-all"
              title="Changer d'état vers quantité d'inventaire"
            >
              <i data-lucide="scale" class="w-3.5 h-3.5"></i>
              <span>Mettre à niveau</span>
            </button>
          </div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

async function recountFromDashboard(variantId) {
  if (typeof recountInventoryItemPrompt === 'function') {
    await recountInventoryItemPrompt(variantId);
  } else {
    try {
      const res = await fetch('/api/inventory/recount', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variant_id: variantId, notes: 'Recomptage demandé depuis le Dashboard' })
      });
      if (res.ok) {
        showToast("Demande de recomptage enregistrée. L'article est prêt pour un nouvel inventaire.", "success");
        refreshDashboard();
      }
    } catch (e) {
      showToast("Erreur lors de la demande de recomptage", "error");
    }
  }
}

function adjustFromDashboard(variantId) {
  switchTab('inventory');
  setTimeout(() => {
    if (typeof openAdjustStockModal === 'function') {
      openAdjustStockModal(variantId);
    }
  }, 150);
}

function renderLowStockAlerts(alerts, unassignedList) {
  const tbody = document.getElementById('alertsTableBody');
  const badgeCount = document.getElementById('alertsBadgeCount');
  const unassignedBadge = document.getElementById('unassignedBadgeCount');
  if (!tbody) return;

  if (badgeCount) badgeCount.textContent = `${alerts.length} sous seuil`;
  if (unassignedBadge) unassignedBadge.textContent = `${(unassignedList || []).length} sans casier`;

  const totalItems = (alerts || []).length + (unassignedList || []).length;
  if (totalItems === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="p-6 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center gap-1">
            <i data-lucide="check-circle" class="w-8 h-8 text-emerald-500"></i>
            <span class="font-medium text-xs mt-1">Excellent ! Tous les profilés sont en stock suffisant et rangés dans un casier atelier.</span>
          </div>
        </td>
      </tr>
    `;
    if (window.lucide) lucide.createIcons();
    return;
  }

  let html = '';

  // 1. Alertes de stock bas
  (alerts || []).forEach(a => {
    const isCritical = a.real_quantity <= 0;
    const isUnassigned = a.location === 'EN_ATTENTE_AFFECTATION' || !a.location;

    const safeRef = encodeURIComponent(a.reference || '');
    const safeDesig = encodeURIComponent(a.designation || '');

    const alertImgHtml = a.image_url
      ? `<img src="${a.image_url}" onclick="openImagePreview('${a.image_url}', '${safeRef}', '${safeDesig}')" class="w-8 h-8 rounded-lg object-cover border border-slate-200 dark:border-slate-700 shrink-0 cursor-pointer hover:scale-110 hover:shadow-md transition-all ring-1 ring-slate-200 dark:ring-slate-700 hover:ring-indigo-500" alt="${a.reference}" title="Cliquer pour agrandir la photo">`
      : `<div class="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 flex items-center justify-center text-slate-400 font-mono text-[10px] font-bold shrink-0">ALU</div>`;

    html += `
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
        <td class="p-3">
          <div class="flex items-center gap-2.5">
            ${alertImgHtml}
            <div>
              <div class="font-bold text-slate-900 dark:text-white">${a.designation}</div>
              <div class="text-[11px] font-mono text-slate-500">${a.reference} • PMP: ${formatMoney(a.pmp)}</div>
            </div>
          </div>
        </td>
        <td class="p-3">
          <div class="flex items-center gap-1.5 font-medium">
            <span class="color-bubble" style="background-color: ${a.color_hex};"></span>
            <span>${a.color}</span>
          </div>
        </td>
        <td class="p-3 font-extrabold text-sm ${isCritical ? 'text-rose-600' : 'text-amber-600'}">
          ${a.real_quantity} <span class="text-[11px] font-normal text-slate-400">${a.unit}</span>
        </td>
        <td class="p-3 font-semibold text-slate-600 dark:text-slate-400">
          ${a.threshold} ${a.unit}
        </td>
        <td class="p-3 text-xs">
          ${isUnassigned ? '<span class="px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-700">⚠️ EN_ATTENTE_AFFECTATION</span>' : `<span class="font-mono font-bold">${a.location}</span>`}
        </td>
        <td class="p-3 text-right">
          <button onclick="quickRestock('${a.reference}', '${a.color}')" class="btn-touch px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5 ml-auto">
            <i data-lucide="download" class="w-3.5 h-3.5"></i>
            <span>Stocker (+)</span>
          </button>
        </td>
      </tr>
    `;
  });

  // 2. Alertes spécifiques de casier non affecté (si pas déjà listé en stock bas)
  (unassignedList || []).forEach(u => {
    const already = (alerts || []).find(a => a.variant_id === u.variant_id);
    if (already) return;

    html += `
      <tr class="bg-amber-50/40 dark:bg-amber-950/20 hover:bg-amber-50 dark:hover:bg-amber-950/40 transition-colors">
        <td class="p-3">
          <div>
            <div class="font-bold text-slate-900 dark:text-white">${u.designation}</div>
            <div class="text-[11px] font-mono text-slate-500">${u.reference}</div>
          </div>
        </td>
        <td class="p-3 font-semibold text-slate-700 dark:text-slate-300">${u.color}</td>
        <td class="p-3 font-bold text-slate-800 dark:text-slate-200">${u.quantity} ${u.unit}</td>
        <td class="p-3 text-slate-400">-</td>
        <td class="p-3 text-xs">
          <span class="px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">⚠️ EN_ATTENTE_AFFECTATION</span>
        </td>
        <td class="p-3 text-right">
          <button onclick="promptAssignLocation(${u.variant_id})" class="btn-touch px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs shadow-sm flex items-center gap-1.5 ml-auto">
            <i data-lucide="map-pin" class="w-3.5 h-3.5"></i>
            <span>Affecter Casier</span>
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
  if (window.lucide) lucide.createIcons();
}

async function promptAssignLocation(variantId) {
  const loc = prompt("Entrez le casier / emplacement atelier (ex: P-03, A-02) :");
  if (loc && loc.trim()) {
    try {
      const res = await fetch(`/api/stock/variant/${variantId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ location: loc.trim().toUpperCase() })
      });
      if (res.ok) {
        showToast("Casier affecté avec succès !", "success");
        refreshDashboard();
      }
    } catch (err) {
      showToast("Erreur lors de l'affectation", "error");
    }
  }
}

function quickRestock(reference, color) {
  switchTab('actions');
  selectActionSubTab('stocker');

  const inRefInput = document.getElementById('stockInSearchRef');
  if (inRefInput) {
    inRefInput.value = reference;
    onStockInSearchRef(reference);
  }
}

function renderTimelineChart(timelineData) {
  const ctx = document.getElementById('timelineChart')?.getContext('2d');
  if (!ctx) return;

  if (window.timelineChartInstance) window.timelineChartInstance.destroy();

  const isDark = document.documentElement.classList.contains('dark');
  const gridColor = isDark ? 'rgba(51, 65, 85, 0.4)' : 'rgba(226, 232, 240, 0.8)';
  const textColor = isDark ? '#94a3b8' : '#64748b';

  window.timelineChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: timelineData?.labels || [],
      datasets: [
        {
          label: 'Approvisionnements Entrants (DZD)',
          data: timelineData?.stockage || [],
          backgroundColor: '#4f46e5',
          borderRadius: 6,
        },
        {
          label: 'Sorties & Chantiers (DZD)',
          data: timelineData?.destockage || [],
          backgroundColor: '#f59e0b',
          borderRadius: 6,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            color: textColor,
            font: { size: 11, family: 'Plus Jakarta Sans', weight: '600' },
            boxWidth: 12,
            usePointStyle: true
          }
        },
        tooltip: {
          callbacks: {
            label: function(ctx) { return ` ${ctx.dataset.label}: ${formatMoney(ctx.raw)}`; }
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: textColor, font: { size: 10 } } },
        y: {
          grid: { color: gridColor },
          ticks: {
            color: textColor,
            font: { size: 10 },
            callback: function(v) { return Number(v).toLocaleString('fr-DZ') + ' DA'; }
          }
        }
      }
    }
  });
}

function renderCategoryChart(categoriesDist) {
  const ctx = document.getElementById('categoryChart')?.getContext('2d');
  if (!ctx) return;

  if (window.categoryChartInstance) window.categoryChartInstance.destroy();

  const isDark = document.documentElement.classList.contains('dark');
  const labels = categoriesDist?.map(c => c.category) || [];
  const values = categoriesDist?.map(c => c.value) || [];

  const palette = ['#4f46e5', '#10b981', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'];

  window.categoryChartInstance = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: values,
        backgroundColor: palette.slice(0, labels.length),
        borderWidth: 2,
        borderColor: isDark ? '#0f172a' : '#ffffff',
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '70%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(ctx) { return ` ${ctx.label}: ${formatMoney(ctx.raw)}`; }
          }
        }
      }
    }
  });

  const listContainer = document.getElementById('categorySummaryList');
  if (listContainer) {
    const totalVal = values.reduce((a, b) => a + b, 0);
    listContainer.innerHTML = (categoriesDist || []).map((c, i) => {
      const pct = totalVal > 0 ? Math.round((c.value / totalVal) * 100) : 0;
      return `
        <div class="flex items-center justify-between text-xs py-1 border-b border-slate-100 dark:border-slate-800/80">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${palette[i % palette.length]}"></span>
            <span class="font-medium text-slate-700 dark:text-slate-300 truncate max-w-[130px]">${c.category}</span>
          </div>
          <div class="text-right">
            <span class="font-bold text-slate-900 dark:text-white">${formatMoney(c.value)}</span>
            <span class="text-[10px] text-slate-400 ml-1">(${pct}%)</span>
          </div>
        </div>
      `;
    }).join('');
  }
}
