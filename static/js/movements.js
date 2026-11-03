let mvtDebounceTimer = null;

async function loadMovementsData() {
  await loadOrdersForMovementFilter();

  const actionType = document.getElementById('mvtFilterType')?.value || 'ALL';
  const orderNumber = document.getElementById('mvtFilterOrder')?.value || 'ALL';
  const startDate = document.getElementById('mvtFilterStartDate')?.value || '';
  const endDate = document.getElementById('mvtFilterEndDate')?.value || '';
  const search = document.getElementById('mvtSearchInput')?.value || '';

  const params = new URLSearchParams();
  if (actionType && actionType !== 'ALL') params.append('action_type', actionType);
  if (orderNumber && orderNumber !== 'ALL') params.append('order_number', orderNumber);
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);
  if (search) params.append('search', search);

  try {
    const res = await fetch(`/api/movements?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur chargement mouvements');
    const movements = await res.json();

    renderMovementsTable(movements);

  } catch (err) {
    console.error('Erreur loadMovementsData:', err);
    showToast('Erreur de chargement des mouvements', 'error');
  }
}

async function loadOrdersForMovementFilter() {
  const select = document.getElementById('mvtFilterOrder');
  if (!select || select.options.length > 1) return;

  try {
    const res = await fetch('/api/dashboard/orders-list');
    if (res.ok) {
      const data = await res.json();
      const chantiers = data.chantiers || [];
      const orders = data.orders || [];

      let html = '<option value="ALL">Tous chantiers & commandes</option>';
      chantiers.forEach(c => {
        html += `<option value="${c.code}">📍 ${c.code} (${c.name})</option>`;
      });
      orders.forEach(o => {
        if (!chantiers.some(c => c.code === o.order_number)) {
          html += `<option value="${o.order_number}">📦 ${o.order_number}</option>`;
        }
      });
      select.innerHTML = html;
    }
  } catch (err) {
    console.error('Erreur:', err);
  }
}

function filterMovements() {
  loadMovementsData();
}

function debounceMovementsFilter() {
  clearTimeout(mvtDebounceTimer);
  mvtDebounceTimer = setTimeout(() => loadMovementsData(), 250);
}

function renderMovementsTable(movements) {
  const tbody = document.getElementById('movementsTableBody');
  if (!tbody) return;

  if (!movements || movements.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="12" class="p-8 text-center text-slate-400">
          <div class="flex flex-col items-center justify-center gap-2">
            <i data-lucide="inbox" class="w-8 h-8 text-slate-400"></i>
            <span>Aucun mouvement ne correspond aux filtres appliqués.</span>
          </div>
        </td>
      </tr>
    `;
    lucide.createIcons();
    return;
  }

  tbody.innerHTML = movements.map(m => {
    let actionBadge = '';
    if (m.action_type === 'STOCKAGE') {
      actionBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">📥 Entrée</span>';
    } else if (m.action_type === 'DESTOCKAGE') {
      actionBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300">📤 Sortie</span>';
    } else {
      actionBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">🔒 Réservation</span>';
    }

    const isAnonyme = m.is_anonyme === 1 || m.order_number === 'STOCK_GENERAL';

    return `
      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${isAnonyme ? 'bg-amber-50/30 dark:bg-amber-950/10' : ''}">
        <td class="py-2.5 px-2.5 font-mono text-[11px] text-slate-500">${m.timestamp}</td>
        <td class="py-2.5 px-2 text-center">${actionBadge}</td>
        <td class="py-2.5 px-2.5 font-mono font-semibold text-indigo-600">${m.product_reference}</td>
        <td class="py-2.5 px-2.5 font-medium text-slate-800 dark:text-slate-200 truncate max-w-[200px] xl:max-w-none" title="${m.product_name}">${m.product_name}</td>
        <td class="py-2.5 px-2.5 font-semibold text-slate-700 dark:text-slate-300">${m.color}</td>
        <td class="py-2.5 px-2 text-right font-bold text-sm ${m.action_type === 'STOCKAGE' ? 'text-indigo-600' : 'text-slate-800 dark:text-white'}">
          ${m.action_type === 'STOCKAGE' ? '+' : (m.action_type === 'DESTOCKAGE' ? '-' : '')}${m.quantity}
        </td>
        <td class="py-2.5 px-2.5 text-right text-slate-500">${formatMoney(m.unit_price)}</td>
        <td class="py-2.5 px-2.5 text-right font-bold text-emerald-600">${formatMoney(m.pmp_at_movement)}</td>
        <td class="py-2.5 px-2.5 text-right font-extrabold text-slate-900 dark:text-white">${formatMoney(m.total_value)}</td>
        
        <!-- Chantier avec alerte anonyme si non affecté -->
        <td class="py-2.5 px-2.5 text-xs">
          ${isAnonyme ? '<span class="px-2 py-0.5 rounded-full font-bold bg-amber-100 text-amber-800 text-[10px]">⚠️ Non assigné</span>' : `<span class="font-bold text-indigo-600 font-mono">${m.order_number}</span>`}
        </td>

        <td class="py-2.5 px-2.5 text-slate-600 dark:text-slate-300 text-xs">${m.operator || m.poseur || 'Atelier'}</td>
        <td class="py-2.5 px-2.5 text-slate-400 text-xs truncate max-w-[160px] xl:max-w-[240px]" title="${m.notes || ''}">${m.notes || '-'}</td>
      </tr>
    `;
  }).join('');

  lucide.createIcons();
  if (typeof updateTopScrollSync === 'function') {
    updateTopScrollSync('movementsTopScrollWrapper', 'movementsTableScrollWrapper', 'movementsTable', 'movementsTopScrollContent');
  }
}

function exportMovementsCSV() {
  const actionType = document.getElementById('mvtFilterType')?.value || 'ALL';
  const orderNumber = document.getElementById('mvtFilterOrder')?.value || 'ALL';

  const params = new URLSearchParams();
  if (actionType && actionType !== 'ALL') params.append('action_type', actionType);
  if (orderNumber && orderNumber !== 'ALL') params.append('order_number', orderNumber);

  window.location.href = `/api/movements/export-csv?${params.toString()}`;
  showToast('Export CSV en cours de téléchargement', 'info');
}
