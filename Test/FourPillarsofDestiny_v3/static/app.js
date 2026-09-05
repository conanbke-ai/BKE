(() => {
  'use strict';
  const current = document.currentScript;
  const base = new URL('.', current?.src || window.location.href);
  const load = (name, version) => new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = new URL(`${name}?v=${version}`, base).toString();
    script.onload = resolve;
    script.onerror = () => reject(new Error(`${name} 로드 실패`));
    document.head.appendChild(script);
  });

  load('solar_time_ui.js', '20260905-solar-time-1')
    .then(() => load('app_core.js', '20260831-public-deploy-56'))
    .catch(error => {
      console.error(error);
      const toast = document.querySelector('#toast');
      if (toast) {
        toast.textContent = '화면 스크립트를 불러오지 못했습니다. 새로고침해 주세요.';
        toast.classList.remove('hidden');
      }
    });
})();
