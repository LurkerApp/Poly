document.addEventListener('DOMContentLoaded', function() {
  const footer = document.createElement('footer');
  footer.innerHTML = `
    <div class="footer-inner">
      <span class="footer-logo">Lurker<span style="color:#1ABC9C;">.</span></span>
      <div class="footer-links">
        <a href="index.html">Home</a>
        <a href="insider_trades.html">Insider Trades</a>
        <a href="gov-spending.html">Gov Spending</a>
        <a href="polywatcher.html">Whale Watcher</a>
        <a href="polytopaccounts.html">Top Accounts</a>
      </div>
      <span class="footer-copy">© ${new Date().getFullYear()} Lurker. All rights reserved.</span>
    </div>
  `;
  document.body.appendChild(footer);
});
