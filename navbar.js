document.addEventListener('DOMContentLoaded', function() {
  var isLoggedIn = localStorage.getItem('loggedIn') === 'true';
  var destination = isLoggedIn ? 'settings.html' : 'signup.html';
  var avatarStyle = isLoggedIn ? '' : 'display:none';
  var label = isLoggedIn ? 'Username' : 'Sign up';
  
  document.body.insertAdjacentHTML('afterbegin',
    '<style>' +
      '.nav-dropdown { position: relative; display: inline-block; }' +
      '.dropdown-btn { background-color: transparent; border: none; padding: 8px 12px; cursor: pointer; font-family: Poppins, sans-serif; font-size: 14px; font-weight: 500; color: #111; }' +
      '.dropdown-btn:hover { background-color: #f0f0f0; border-radius: 4px; }' +
      '.dropdown-content { display: none; position: absolute; top: 100%; left: 0; background-color: white; min-width: 200px; box-shadow: 0 8px 16px rgba(0,0,0,0.1); border-radius: 4px; z-index: 1000; }' +
      '.dropdown-content a { color: #111; padding: 12px 16px; text-decoration: none; display: block; font-family: Poppins, sans-serif; font-size: 14px; }' +
      '.dropdown-content a:hover { background-color: #f0f0f0; }' +
      '.nav-dropdown:hover .dropdown-content { display: block; }' +
      '.wave-container { width: 100%; height: 120px; overflow: hidden; position: relative; margin-top: 20px; }' +
      '.wave-svg { width: 100%; height: 100%; display: block; }' +
      '@keyframes waveAnimation { 0% { d: path("M0,60 Q180,20 360,60 T720,60 T1080,60 T1440,60 L1440,120 L0,120 Z"); } 25% { d: path("M0,40 Q180,80 360,40 T720,40 T1080,40 T1440,40 L1440,120 L0,120 Z"); } 50% { d: path("M0,60 Q180,20 360,60 T720,60 T1080,60 T1440,60 L1440,120 L0,120 Z"); } 75% { d: path("M0,80 Q180,30 360,80 T720,80 T1080,80 T1440,80 L1440,120 L0,120 Z"); } 100% { d: path("M0,60 Q180,20 360,60 T720,60 T1080,60 T1440,60 L1440,120 L0,120 Z"); } }' +
      '.wave-path { animation: waveAnimation 4s ease-in-out infinite; fill: #1D9E75; opacity: 0.8; }' +
    '</style>' +
    '<nav>' +
      '<a href="index.html" style="text-decoration:none;">' +
        '<span style="font-family: Poppins, sans-serif; font-size:22px; font-weight:600; color:#111; letter-spacing:-0.5px;">Lurker<span style="color:#1D9E75;">.</span></span>' +
      '</a>' +
      '<div class="nav-center">' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Category 1</button>' +
          '<div class="dropdown-content">' +
            '<a href="page1.html">Page 1</a>' +
            '<a href="page2.html">Page 2</a>' +
            '<a href="page3.html">Page 3</a>' +
          '</div>' +
        '</div>' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Category 2</button>' +
          '<div class="dropdown-content">' +
            '<a href="page4.html">Page 4</a>' +
            '<a href="page5.html">Page 5</a>' +
            '<a href="page6.html">Page 6</a>' +
          '</div>' +
        '</div>' +
        '<div class="nav-dropdown">' +
          '<button class="dropdown-btn">Category 3</button>' +
          '<div class="dropdown-content">' +
            '<a href="page7.html">Page 7</a>' +
            '<a href="page8.html">Page 8</a>' +
            '<a href="page9.html">Page 9</a>' +
          '</div>' +
        '</div>' +
      '</div>' +
      '<button class="user-btn" onclick="window.location.href=\'' + destination + '\'">' +
        '<div class="avatar" style="' + avatarStyle + '">U</div>' +
        '<span>' + label + '</span>' +
      '</button>' +
    '</nav>' +
    '<div class="wave-container" id="wave-container"></div>'
  );

  // Add wave animation only on index.html
  if (window.location.pathname.endsWith('index.html') || window.location.pathname === '/') {
    var waveContainer = document.getElementById('wave-container');
    waveContainer.innerHTML = '<svg class="wave-svg" viewBox="0 0 1440 120" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none"><path class="wave-path" d="M0,60 Q180,20 360,60 T720,60 T1080,60 T1440,60 L1440,120 L0,120 Z"></path></svg>';
  }
});
