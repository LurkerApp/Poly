document.addEventListener('DOMContentLoaded', function() {
  const footer = document.createElement('footer');
  footer.innerHTML = `
    <div class="footer-inner">
      <div class="footer-brand">
        <span class="footer-logo">Lurker<span style="color:#1ABC9C;">.</span></span>
        <p class="footer-tagline">Your edge in markets.</p>
      </div>
      <div class="footer-cols">
        <div class="footer-col">
          <div class="footer-col-title">About</div>
          <a href="index.html">Home</a>
          <a href="settings.html">Settings</a>
          <a href="signup.html">Sign Up</a>
          <a href="login.html">Log In</a>
        </div>
        <div class="footer-col">
          <div class="footer-col-title">Resources</div>
          <a href="insider_trades.html">Insider Trades</a>
          <a href="gov-spending.html">Gov Spending</a>
          <a href="polywatcher.html">Whale Watcher</a>
          <a href="polytopaccounts.html">Top Accounts</a>
        </div>
        <div class="footer-col">
          <div class="footer-col-title">Socials</div>
          <a href="#" target="_blank" class="footer-social">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31.2 31.2 0 0 0 0 12a31.2 31.2 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31.2 31.2 0 0 0 24 12a31.2 31.2 0 0 0-.5-5.8zM9.7 15.5V8.5l6.3 3.5-6.3 3.5z"/></svg>
            YouTube
          </a>
          <a href="#" target="_blank" class="footer-social">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19.6 3H4.4A1.4 1.4 0 0 0 3 4.4v15.2A1.4 1.4 0 0 0 4.4 21h8.2v-6.6H10v-2.6h2.6v-1.9c0-2.6 1.6-4 3.9-4 1.1 0 2.2.1 3.3.2v2.7h-2.3c-1.3 0-1.5.6-1.5 1.5v1.5H20l-.4 2.6h-2.6V21h3.6A1.4 1.4 0 0 0 21 19.6V4.4A1.4 1.4 0 0 0 19.6 3z"/></svg>
            TikTok
          </a>
          <a href="#" target="_blank" class="footer-social">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M18.3 5.7 13.1 11.6 19.5 19h-4.7l-3.8-5-4.5 5H4.2l5.5-6.1L3.3 5.7h4.8l3.4 4.6 4.1-4.6h2.7zm-1 11.9-8.7-11.4H5.4l8.7 11.4h3.2z"/></svg>
            X
          </a>
          <a href="#" target="_blank" class="footer-social">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.2c3.2 0 3.6 0 4.9.1 3.3.1 4.8 1.7 4.9 4.9.1 1.3.1 1.6.1 4.8 0 3.2 0 3.6-.1 4.8-.1 3.2-1.6 4.8-4.9 4.9-1.3.1-1.6.1-4.9.1-3.2 0-3.6 0-4.8-.1-3.3-.1-4.8-1.7-4.9-4.9C2.2 15.6 2.2 15.2 2.2 12c0-3.2 0-3.6.1-4.8C2.4 3.9 3.9 2.3 7.2 2.3 8.4 2.2 8.8 2.2 12 2.2zm0-2.2C8.7 0 8.3 0 7.1.1 2.7.3.3 2.7.1 7.1 0 8.3 0 8.7 0 12c0 3.3 0 3.7.1 4.9.2 4.4 2.6 6.8 7 7C8.3 24 8.7 24 12 24c3.3 0 3.7 0 4.9-.1 4.4-.2 6.8-2.6 7-7 .1-1.2.1-1.6.1-4.9 0-3.3 0-3.7-.1-4.9C23.7 2.7 21.3.3 16.9.1 15.7 0 15.3 0 12 0zm0 5.8a6.2 6.2 0 1 0 0 12.4 6.2 6.2 0 0 0 0-12.4zm0 10.2a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.4-11.8a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8z"/></svg>
            Instagram
          </a>
        </div>
      </div>
      <div class="footer-bottom">
        © ${new Date().getFullYear()} Lurker. All rights reserved.
      </div>
    </div>
  `;
  document.body.appendChild(footer);
});
