document.addEventListener('DOMContentLoaded', function() {
  const footer = document.createElement('footer');
  footer.style.cssText = 'display:block; width:100%; margin-top:4rem; border-top:1px solid #2a2d30; background:#141618; padding:3rem 2rem 1.5rem; font-family:Inter,sans-serif;';

  footer.innerHTML = `
    <div style="max-width:1400px; margin:0 auto; display:flex; flex-direction:column; align-items:center; gap:2.5rem;">

      <!-- Brand -->
      <div style="text-align:center;">
        <div style="font-size:20px; font-weight:700; color:#e0e0e0;">Lurker<span style="color:#1ABC9C;">.</span></div>
        <p style="font-size:13px; color:#5a6068; margin-top:6px;">Your edge in markets.</p>
      </div>

      <!-- 3 columns -->
      <div style="display:grid; grid-template-columns:repeat(3,160px); gap:3rem; justify-content:center; text-align:center;">

        <!-- About -->
        <div style="display:flex; flex-direction:column; gap:0.65rem;">
          <div style="font-size:11px; font-weight:700; color:#7F8C8D; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:0.25rem;">About</div>
          <a href="index.html"    style="font-size:13px; color:#5a6068; text-decoration:none;">Home</a>
          <a href="settings.html" style="font-size:13px; color:#5a6068; text-decoration:none;">Settings</a>
          <a href="signup.html"   style="font-size:13px; color:#5a6068; text-decoration:none;">Sign Up</a>
          <a href="login.html"    style="font-size:13px; color:#5a6068; text-decoration:none;">Log In</a>
        </div>

        <!-- Resources -->
        <div style="display:flex; flex-direction:column; gap:0.65rem;">
          <div style="font-size:11px; font-weight:700; color:#7F8C8D; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:0.25rem;">Resources</div>
          <a href="insider_trades.html"  style="font-size:13px; color:#5a6068; text-decoration:none;">Insider Trades</a>
          <a href="gov-spending.html"    style="font-size:13px; color:#5a6068; text-decoration:none;">Gov Spending</a>
          <a href="polywatcher.html"     style="font-size:13px; color:#5a6068; text-decoration:none;">Whale Watcher</a>
          <a href="polytopaccounts.html" style="font-size:13px; color:#5a6068; text-decoration:none;">Top Accounts</a>
        </div>

        <!-- Socials -->
        <div style="display:flex; flex-direction:column; gap:0.65rem;">
          <div style="font-size:11px; font-weight:700; color:#7F8C8D; text-transform:uppercase; letter-spacing:0.8px; margin-bottom:0.25rem;">Socials</div>
          <a href="#" target="_blank" style="font-size:13px; color:#5a6068; text-decoration:none; display:flex; align-items:center; justify-content:center; gap:7px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31.2 31.2 0 0 0 0 12a31.2 31.2 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31.2 31.2 0 0 0 24 12a31.2 31.2 0 0 0-.5-5.8zM9.7 15.5V8.5l6.3 3.5-6.3 3.5z"/>
            </svg>
            YouTube
          </a>
          <a href="#" target="_blank" style="font-size:13px; color:#5a6068; text-decoration:none; display:flex; align-items:center; justify-content:center; gap:7px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-2.88 2.5 2.89 2.89 0 0 1-2.89-2.89 2.89 2.89 0 0 1 2.89-2.89c.28 0 .54.04.79.1V9.01a6.27 6.27 0 0 0-.79-.05 6.34 6.34 0 0 0-6.34 6.34 6.34 6.34 0 0 0 6.34 6.34 6.34 6.34 0 0 0 6.33-6.34V8.69a8.18 8.18 0 0 0 4.78 1.52V6.75a4.85 4.85 0 0 1-1.01-.06z"/>
            </svg>
            TikTok
          </a>
          <a href="#" target="_blank" style="font-size:13px; color:#5a6068; text-decoration:none; display:flex; align-items:center; justify-content:center; gap:7px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.3 5.7 13.1 11.6 19.5 19h-4.7l-3.8-5-4.5 5H4.2l5.5-6.1L3.3 5.7h4.8l3.4 4.6 4.1-4.6h2.7zm-1 11.9-8.7-11.4H5.4l8.7 11.4h3.2z"/>
            </svg>
            X
          </a>
          <a href="#" target="_blank" style="font-size:13px; color:#5a6068; text-decoration:none; display:flex; align-items:center; justify-content:center; gap:7px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2.2c3.2 0 3.6 0 4.9.1 3.3.1 4.8 1.7 4.9 4.9.1 1.3.1 1.6.1 4.8 0 3.2 0 3.6-.1 4.8-.1 3.2-1.6 4.8-4.9 4.9-1.3.1-1.6.1-4.9.1-3.2 0-3.6 0-4.8-.1-3.3-.1-4.8-1.7-4.9-4.9C2.2 15.6 2.2 15.2 2.2 12c0-3.2 0-3.6.1-4.8C2.4 3.9 3.9 2.3 7.2 2.3 8.4 2.2 8.8 2.2 12 2.2zm0-2.2C8.7 0 8.3 0 7.1.1 2.7.3.3 2.7.1 7.1 0 8.3 0 8.7 0 12c0 3.3 0 3.7.1 4.9.2 4.4 2.6 6.8 7 7C8.3 24 8.7 24 12 24c3.3 0 3.7 0 4.9-.1 4.4-.2 6.8-2.6 7-7 .1-1.2.1-1.6.1-4.9 0-3.3 0-3.7-.1-4.9C23.7 2.7 21.3.3 16.9.1 15.7 0 15.3 0 12 0zm0 5.8a6.2 6.2 0 1 0 0 12.4 6.2 6.2 0 0 0 0-12.4zm0 10.2a4 4 0 1 1 0-8 4 4 0 0 1 0 8zm6.4-11.8a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8z"/>
            </svg>
            Instagram
          </a>
        </div>

      </div>

      <!-- Bottom bar -->
      <div style="font-size:12px; color:#3a3d40; text-align:center; padding-top:1.5rem; border-top:1px solid #2a2d30; width:100%;">
        © ${new Date().getFullYear()} Lurker. All rights reserved.
      </div>

    </div>
  `;

  document.body.appendChild(footer);
});
