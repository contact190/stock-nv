let currentOrderStatusFilter = 'ALL';

async function loadOrdersData() {
  const params = new URLSearchParams();
  if (currentOrderStatusFilter && currentOrderStatusFilter !== 'ALL') {
    params.append('status', currentOrderStatusFilter);
  }

  try {
    const res = await fetch(`/api/orders?${params.toString()}`);
    if (!res.ok) throw new Error('Erreur chargement commandes');
    const orders = await res.json();

    renderOrdersList(orders);

  } catch (err) {
    console.error('Erreur loadOrdersData:', err);
    showToast('Erreur de chargement des chantiers', 'error');
  }
}

function filterOrdersByStatus(status) {
  currentOrderStatusFilter = status;

  document.querySelectorAll('.order-status-pill').forEach(pill => {
    if (pill.getAttribute('data-status') === status) {
      pill.className = 'order-status-pill px-3 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white shadow-sm';
    } else {
      pill.className = 'order-status-pill px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800';
    }
  });

  loadOrdersData();
}

function renderOrdersList(orders) {
  const container = document.getElementById('ordersListContainer');
  if (!container) return;

  if (!orders || orders.length === 0) {
    container.innerHTML = `
      <div class="p-8 text-center text-slate-400 glass-panel rounded-2xl border border-slate-200 dark:border-slate-800">
        <div class="flex flex-col items-center justify-center gap-2">
          <i data-lucide="package-open" class="w-8 h-8 text-slate-400"></i>
          <span>Aucun chantier ou commande trouvé pour ce filtre.</span>
        </div>
      </div>
    `;
    lucide.createIcons();
    return;
  }

  container.innerHTML = orders.map(o => {
    let statusBadge = '';
    const isDestocked = o.status === 'DESTOCKED';
    const isReserved = o.status === 'RESERVEE';

    if (isDestocked) {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">✅ Déstocké / Posé</span>';
    } else if (isReserved) {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">🔒 Profilés Réservés</span>';
    } else {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300">⏳ En attente</span>';
    }

    return `
      <div class="glass-panel p-5 rounded-2xl border border-slate-200 dark:border-slate-800 space-y-4">
        
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800/80 pb-3">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-950 flex items-center justify-center text-blue-600">
              <i data-lucide="hard-hat" class="w-5 h-5"></i>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-extrabold text-base text-slate-900 dark:text-white font-mono">${o.order_number}</span>
                ${statusBadge}
              </div>
              <div class="text-xs text-slate-500">${o.client_name} • Créé le ${o.created_at}</div>
            </div>
          </div>

          <!-- Bouton Valider & Déstocker -->
          <div class="flex items-center gap-2 self-start sm:self-auto">
            ${isReserved ? `
              <button onclick="handleValidateDestockOrder('${o.order_number}')" class="btn-touch px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-xs shadow-md shadow-emerald-600/20 flex items-center gap-1.5">
                <i data-lucide="check-check" class="w-4 h-4"></i>
                <span>Valider & Déstocker Chantier</span>
              </button>
            ` : ''}

            <button onclick="toggleOrderItemsDetails('${o.order_number}')" class="btn-touch px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 text-xs font-semibold flex items-center gap-1">
              <span>Profilés (${o.items_count})</span>
              <i data-lucide="chevron-down" id="chevron-${o.order_number}" class="w-3.5 h-3.5"></i>
            </button>
          </div>
        </div>

        <!-- Bilan financier du chantier au PMP (DZD) -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs bg-slate-50 dark:bg-slate-900/60 p-3 rounded-xl">
          <div>
            <span class="text-slate-400">Barres réservées:</span>
            <div class="font-bold text-amber-600 text-sm">${o.total_reserved_qty} barres</div>
          </div>
          <div>
            <span class="text-slate-400">Valeur réservée:</span>
            <div class="font-bold text-amber-600 text-sm">${formatMoney(o.total_reserved_value)}</div>
          </div>
          <div>
            <span class="text-slate-400">Barres déstockées:</span>
            <div class="font-bold text-emerald-600 text-sm">${o.total_destocked_qty} barres</div>
          </div>
          <div>
            <span class="text-slate-400">Valeur déstockée:</span>
            <div class="font-bold text-emerald-600 text-sm">${formatMoney(o.total_destocked_value)}</div>
          </div>
        </div>

        ${o.notes ? `<div class="text-xs text-slate-500 italic bg-white/40 dark:bg-slate-800/40 p-2 rounded-lg border border-slate-100 dark:border-slate-800">📝 Notes: ${o.notes}</div>` : ''}

        <div id="orderDetails-${o.order_number}" class="hidden space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800">
          <div class="text-xs font-bold text-slate-700 dark:text-slate-300">Lignes de profilés réservés pour le débit :</div>
          <div id="orderItemsTable-${o.order_number}" class="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
            <div class="p-3 text-xs text-slate-400">Chargement...</div>
          </div>
        </div>

      </div>
    `;
  }).join('');

  lucide.createIcons();
}

async function toggleOrderItemsDetails(orderNumber) {
  const panel = document.getElementById(`orderDetails-${orderNumber}`);
  const chevron = document.getElementById(`chevron-${orderNumber}`);
  if (!panel) return;

  const isHidden = panel.classList.contains('hidden');
  if (isHidden) {
    panel.classList.remove('hidden');
    if (chevron) chevron.classList.add('rotate-180');

    try {
      const res = await fetch(`/api/orders/${orderNumber}`);
      if (res.ok) {
        const data = await res.json();
        const itemsContainer = document.getElementById(`orderItemsTable-${orderNumber}`);
        if (itemsContainer) {
          if (!data.items || data.items.length === 0) {
            itemsContainer.innerHTML = '<div class="p-3 text-xs text-slate-400">Aucun profilé associé.</div>';
          } else {
            itemsContainer.innerHTML = `
              <table class="w-full text-left text-xs">
                <thead class="bg-slate-100 dark:bg-slate-800 text-slate-500 uppercase text-[10px]">
                  <tr>
                    <th class="p-2.5">Profilé & Référence</th>
                    <th class="p-2.5">Teinte</th>
                    <th class="p-2.5 text-right">Qté Réservée</th>
                    <th class="p-2.5 text-right">Qté Déstockée</th>
                    <th class="p-2.5 text-right">PMP / Prix Unitaire</th>
                    <th class="p-2.5 text-right">Total Ligne (DZD)</th>
                    <th class="p-2.5 text-center">Statut</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                  ${data.items.map(itm => `
                    <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <td class="p-2.5 font-medium text-slate-900 dark:text-white">
                        <div>${itm.product_name}</div>
                        <div class="font-mono text-[10px] text-indigo-600">${itm.product_reference}</div>
                      </td>
                      <td class="p-2.5 font-semibold text-slate-700 dark:text-slate-300">${itm.color}</td>
                      <td class="p-2.5 text-right font-bold text-amber-600">${itm.quantity_reserved}</td>
                      <td class="p-2.5 text-right font-bold text-emerald-600">${itm.quantity_destocked}</td>
                      <td class="p-2.5 text-right text-slate-500">${formatMoney(itm.unit_price)}</td>
                      <td class="p-2.5 text-right font-bold text-slate-900 dark:text-white">
                        ${formatMoney((itm.quantity_reserved + itm.quantity_destocked) * itm.unit_price)}
                      </td>
                      <td class="p-2.5 text-center">
                        <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${itm.status === 'DESTOCKED' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}">
                          ${itm.status === 'DESTOCKED' ? 'Déstocké' : 'Réservé'}
                        </span>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            `;
          }
        }
      }
    } catch (err) {
      console.error('Erreur chargement articles:', err);
    }

  } else {
    panel.classList.add('hidden');
    if (chevron) chevron.classList.remove('rotate-180');
  }
}

async function handleValidateDestockOrder(orderNumber) {
  if (!confirm(`Confirmer la validation et le déstockage des profilés pour le chantier ${orderNumber} ?\nLes barres réservées seront débitées physiquement du stock atelier.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/orders/${orderNumber}/validate-destock`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_number: orderNumber, user: 'Admin' })
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur validation');

    showToast(`✅ ${result.message}`, 'success');
    loadOrdersData();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}

function openNewOrderModal() {
  document.getElementById('modalNewOrder')?.classList.remove('hidden');
  document.getElementById('newOrderNumber').value = `CHANTIER-${Math.floor(100 + Math.random() * 900)}`;
}

function closeNewOrderModal() {
  document.getElementById('modalNewOrder')?.classList.add('hidden');
}

async function handleCreateOrderSubmit(e) {
  e.preventDefault();

  const payload = {
    order_number: document.getElementById('newOrderNumber').value.trim().toUpperCase(),
    client_name: document.getElementById('newOrderClient').value.trim(),
    notes: document.getElementById('newOrderNotes').value.trim()
  };

  try {
    const res = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Erreur création');

    showToast(`Chantier ${result.order_number} enregistré`, 'success');
    closeNewOrderModal();
    loadOrdersData();
    refreshDashboard();

  } catch (err) {
    showToast(`⛔ ${err.message}`, 'error');
  }
}
