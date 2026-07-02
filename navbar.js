document.addEventListener('DOMContentLoaded', function() {
  var isLoggedIn = localStorage.getItem('loggedIn') === 'true';
  var username = localStorage.getItem('username') || 'User';
  var destination = isLoggedIn ? 'settings.html' : 'signup.html';
  var avatarStyle = isLoggedIn ? '' : 'display:none';
  var label = isLoggedIn ? username : 'Sign up';
  var avatarLetter = username.charAt(0).toUpperCase();

  document.body.insertAdjacentHTML('afterbegin',
    '<style>' +
      '.nav-dropdown { position: relative; display: inline-block; }' +
      '.dropdown-btn { background: none; border: none; padding: 8px 14px; cursor: pointer; font-family: Inter, sans-serif; font-size: 14px; font-weight: 500; color: #7F8C8D; border-radius: 6px; transition: background 0.15s, color 0.15s; }' +
      '.dropdown-btn:hover { background: #2a2d30; color: #e0e0e0; }' +
      '.dropdown-content { display: none; position: absolute; top: 100%; left: 0; background: #1f2224; min-width: 200px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); border-radius: 8px; border: 1px solid #2a2d30; z-index: 200; overflow: hidden; }' +
      '.dropdown-content a { color: #c0c0c0; padding: 11px 16px; text-decoration: none; display: block; font-family: Inter, sans-serif; font-size: 13px; font-weight: 500; transition: background 0.1s, color 0.1s; }' +
      '.dropdown-content a:hover { background: #2a2d30; color: #1ABC9C; }' +
      '.nav-dropdown:hover .dropdown-content { display: block; }' +
    '</style>' +
    '<nav>' +
      '<a href="index.html" style="text-decoration:none;">' +
        '<span style="font-family: Inter, sans-serif; font-size:22px; font-weight:700; color:#e0e0e0; letter-spacing:-0.5px;">Lurker<span style="color:#1ABC9C;">.</span></span>' +
      '</a>' +
      '<div class="nav-center">' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Trading</button>' +
          '<div class="dropdown-content">' +
            '<a href="insider_trades.html">Insider Trades</a>' +
            '<a href="page2.html">Page 2</a>' +
            '<a href="gov-spending.html">Gov Spending</a>' +
          '</div>' +
        '</div>' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Predictions</button>' +
          '<div class="dropdown-content">' +
            '<a href="polywatcher.html">Whale Watcher</a>' +
            '<a href="polytopaccounts.html">Top Accounts</a>' +
            '<a href="page6.html">Page 6</a>' +
          '</div>' +
        '</div>' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Insights</button>' +
          '<div class="dropdown-content">' +
            '<a href="gov-spending.html">Gov Spending</a>' +
            '<a href="page8.html">Page 8</a>' +
            '<a href="page9.html">Page 9</a>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<button class="user-btn" onclick="window.location.href=\'' + destination + '\'">' +
        '<div class="avatar" style="' + avatarStyle + '">' + avatarLetter + '</div>' +
        '<span>' + label + '</span>' +
      '</button>' +
    '</nav>'
  );
});
