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
      '.dropdown-btn { background-color: transparent; border: none; padding: 8px 12px; cursor: pointer; font-family: Poppins, sans-serif; font-size: 14px; font-weight: 500; color: #111; }' +
      '.dropdown-btn:hover { background-color: #f0f0f0; border-radius: 4px; }' +
      '.dropdown-content { display: none; position: absolute; top: 100%; left: 0; background-color: white; min-width: 200px; box-shadow: 0 8px 16px rgba(0,0,0,0.1); border-radius: 4px; z-index: 10; }' +
      '.dropdown-content a { color: #111; padding: 12px 16px; text-decoration: none; display: block; font-family: Poppins, sans-serif; font-size: 14px; }' +
      '.dropdown-content a:hover { background-color: #f0f0f0; }' +
      '.nav-dropdown:hover .dropdown-content { display: block; }' +
    '</style>' +
    '<nav>' +
      '<a href="index.html" style="text-decoration:none;">' +
        '<span style="font-family: Poppins, sans-serif; font-size:22px; font-weight:600; color:#111; letter-spacing:-0.5px;">Lurker<span style="color:#1D9E75;">.</span></span>' +
      '</a>' +
      '<div class="nav-center">' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Trading</button>' +
          '<div class="dropdown-content">' +
            '<a href="page1.html">Page 1</a>' +
            '<a href="page2.html">Page 2</a>' +
            '<a href="gov-spending.html">Gov Spending</a>' +
          '</div>' +
        '</div>' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Predictions</button>' +
          '<div class="dropdown-content">' +
            '<a href="page4.html">Page 4</a>' +
            '<a href="page5.html">Page 5</a>' +
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
