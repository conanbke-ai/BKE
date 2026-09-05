(() => {
  'use strict';

  const warningState = { profile: null, pair: [] };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  function normalizeApiData(json) {
    if (!json || typeof json !== 'object') return {};
    if (json.data && typeof json.data === 'object') return json.data;
    return json;
  }

  function correctionFromFacts(facts) {
    const correction = facts?.chart?.time_correction;
    return correction && typeof correction === 'object' ? correction : null;
  }

  function warningFor(correction) {
    if (!correction?.boundary_warning) return null;
    return {
      text: correction.warning || '시주 경계에 가까운 출생시간입니다. 적용하는 만세력 계산법에 따라 시주가 달라질 수 있습니다.',
      civil: correction.civil_datetime || '',
      corrected: correction.selected_datetime || '',
      mode: correction.mode || 'true_solar',
      location: correction.location?.name || '',
    };
  }

  function boundaryBanner(item) {
    if (!item) return '';
    return `<aside class="time-boundary-warning" role="note" aria-label="시주 경계 안내">
      <span class="time-boundary-icon" aria-hidden="true">⚠️</span>
      <div><strong>시주 경계에 가까운 출생시간입니다.</strong><p>${esc(item.text.replace(/^시주 경계에 가까운 출생시간입니다\.\s*/, ''))}</p></div>
    </aside>`;
  }

  function installStyles() {
    if (document.getElementById('solarTimeUiStyles')) return;
    const style = document.createElement('style');
    style.id = 'solarTimeUiStyles';
    style.textContent = `
      .time-boundary-warning{display:flex;align-items:flex-start;gap:12px;margin:14px 0 18px;padding:14px 16px;border:1px solid #f1d49a;border-radius:14px;background:#fffaf0;color:#4f4332;box-shadow:0 4px 14px rgba(95,72,37,.06)}
      .time-boundary-warning .time-boundary-icon{font-size:18px;line-height:1.35;flex:0 0 auto}
      .time-boundary-warning strong{display:block;margin:0 0 3px;font-size:14px;color:#3f3528}
      .time-boundary-warning p{margin:0;font-size:13px;line-height:1.55;color:#6a5a45}
      .birth-city-field input{width:100%}
      @media (max-width:640px){.time-boundary-warning{padding:12px 13px;border-radius:12px}.time-boundary-warning p{font-size:12.5px}}
    `;
    document.head.appendChild(style);
  }

  function ensureMainBirthplace() {
    const form = document.querySelector('#profileForm');
    if (!form) return;
    let label = form.querySelector('label.foreign-city, label.birth-city-field');
    if (label) {
      label.classList.remove('foreign-city', 'hidden');
      label.classList.add('birth-city-field');
      const input = label.querySelector('input[name="city"]');
      if (input) {
        input.placeholder = '예: 부천시';
        input.autocomplete = 'address-level2';
      }
      const textNode = [...label.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
      if (textNode) textNode.textContent = '태어난 곳 (시·군)';
    }
    const guide = form.querySelector('.location-guide');
    if (guide) guide.textContent = '태어난 지역의 경도와 당시 시간대·서머타임, 날짜별 태양시 차이를 반영해 시주 시간을 보정합니다.';
  }

  function ensureDynamicBirthplaces(root = document) {
    root.querySelectorAll?.('.dynamic-person[data-person-prefix]').forEach(card => {
      const prefix = card.dataset.personPrefix;
      if (!prefix || card.querySelector(`input[name="${CSS.escape(prefix)}_city"]`)) return;
      const countryLabel = card.querySelector(`select[name="${CSS.escape(prefix)}_country_code"]`)?.closest('label');
      const label = document.createElement('label');
      label.className = 'birth-city-field';
      label.innerHTML = `태어난 곳 (시·군)<input name="${esc(prefix)}_city" placeholder="예: 부천시" autocomplete="address-level2">`;
      if (countryLabel) countryLabel.insertAdjacentElement('afterend', label);
      else card.appendChild(label);
    });
  }

  function dynamicProfilesFromDom() {
    const rows = [];
    document.querySelectorAll('.dynamic-person[data-person-prefix]').forEach(card => {
      const prefix = card.dataset.personPrefix;
      const name = card.querySelector(`[name="${CSS.escape(prefix)}_name"]`)?.value?.trim() || '';
      const city = card.querySelector(`[name="${CSS.escape(prefix)}_city"]`)?.value?.trim() || '';
      const countryCode = card.querySelector(`[name="${CSS.escape(prefix)}_country_code"]`)?.value || 'KR';
      if (name && city) rows.push({ name, city, countryCode });
    });
    return rows;
  }

  function enrichProfiles(value, rows) {
    if (Array.isArray(value)) {
      value.forEach(item => enrichProfiles(item, rows));
      return;
    }
    if (!value || typeof value !== 'object') return;
    const looksLikeProfile = 'year' in value && 'month' in value && 'day' in value && 'name' in value;
    if (looksLikeProfile) {
      value.solar_time_mode ||= 'true_solar';
      if (!String(value.city || '').trim()) {
        const matched = rows.find(row => row.name === String(value.name || '').trim());
        if (matched) {
          value.city = matched.city;
          value.country_code ||= matched.countryCode;
          if (matched.countryCode === 'KR' && !value.country) value.country = '대한민국';
        }
      }
    }
    Object.values(value).forEach(child => enrichProfiles(child, rows));
  }

  function captureWarnings(url, json) {
    const data = normalizeApiData(json);
    const urlText = String(url || '');
    if (urlText.includes('/api/pair')) {
      warningState.pair = [
        warningFor(correctionFromFacts(data.user_facts)),
        warningFor(correctionFromFacts(data.target_facts)),
      ].filter(Boolean);
    } else {
      const profileWarning = warningFor(correctionFromFacts(data.facts));
      if (profileWarning) warningState.profile = profileWarning;
      else if (data.facts) warningState.profile = null;
    }
    queueMicrotask(injectWarnings);
  }

  function placeBanner(root, key, item) {
    if (!root) return;
    const existing = root.querySelector(`[data-time-boundary-banner="${key}"]`);
    if (!item) {
      existing?.remove();
      return;
    }
    if (existing) return;
    const holder = document.createElement('div');
    holder.dataset.timeBoundaryBanner = key;
    holder.innerHTML = boundaryBanner(item);
    const shell = root.querySelector('.page-shell') || root;
    const natal = shell.querySelector('.natal-chart, .natal-chart-wrap, .chart-section, .hero-summary');
    if (natal?.parentNode) natal.insertAdjacentElement('afterend', holder);
    else shell.prepend(holder);
  }

  function injectWarnings() {
    placeBanner(document.querySelector('#page-profile'), 'profile', warningState.profile);
    if (warningState.pair.length) {
      const pairText = warningState.pair.length > 1
        ? { text: '두 사람 중 시주 경계에 가까운 출생시간이 있습니다. 적용하는 만세력 계산법에 따라 시주가 달라질 수 있습니다.' }
        : warningState.pair[0];
      placeBanner(document.querySelector('#page-pair'), 'pair', pairText);
    } else {
      placeBanner(document.querySelector('#page-pair'), 'pair', null);
    }
  }

  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    let nextInit = init;
    try {
      if (typeof init?.body === 'string' && init.body.trim().startsWith('{')) {
        const parsed = JSON.parse(init.body);
        enrichProfiles(parsed, dynamicProfilesFromDom());
        nextInit = { ...init, body: JSON.stringify(parsed) };
      }
    } catch (_) {
      nextInit = init;
    }

    const response = await originalFetch(input, nextInit);
    try {
      const clone = response.clone();
      const json = await clone.json();
      captureWarnings(typeof input === 'string' ? input : input?.url, json);
    } catch (_) {
      // JSON API가 아니거나 응답 본문을 읽지 못한 경우 기존 흐름을 방해하지 않습니다.
    }
    return response;
  };

  installStyles();
  ensureMainBirthplace();
  ensureDynamicBirthplaces();

  const observer = new MutationObserver(() => {
    ensureMainBirthplace();
    ensureDynamicBirthplaces();
    injectWarnings();
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
