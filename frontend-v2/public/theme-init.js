// Apply the saved theme before the first paint (see src/lib/theme.ts).
try {
  var t = localStorage.getItem('floor-theme')
  if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t
} catch (e) {}
