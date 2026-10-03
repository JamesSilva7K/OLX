
    document.addEventListener('wheel', function(e) {
      if (e.ctrlKey) {
        e.preventDefault();
      }
    }, { passive: false });
    // TWA Init
    if (window.Telegram && window.Telegram.WebApp) {
      const twa = window.Telegram.WebApp;
      twa.ready();
      twa.expand();
      // Set theme colors from Telegram
      const root = document.documentElement;
      if (twa.themeParams) {
        const p = twa.themeParams;
        if (p.bg_color) root.style.setProperty('--twa-bg', p.bg_color);
        if (p.text_color) root.style.setProperty('--twa-text', p.text_color);
      }
      // Safe area insets for iOS notch
      root.style.setProperty('--twa-safe-top', (twa.safeAreaInsets?.top || 0) + 'px');
      root.style.setProperty('--twa-safe-bottom', (twa.safeAreaInsets?.bottom || 0) + 'px');
      // Back button handling
      twa.BackButton.onClick(() => {
        const pages = document.querySelectorAll('.page');
        const activePage = document.querySelector('.page:not(.hidden)');
        if (activePage && activePage.id !== 'page-dash') {
          navTo('dash');
          twa.BackButton.hide();
        }
      });
    }
  