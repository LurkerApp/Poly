document.addEventListener('DOMContentLoaded', function() {
  var isLoggedIn = localStorage.getItem('loggedIn') === 'true';
  var destination = isLoggedIn ? 'settings.html' : 'signup.html';
  var avatarStyle = isLoggedIn ? '' : 'display:none';
  var label = isLoggedIn ? 'Username' : 'Sign up';
  document.body.insertAdjacentHTML('afterbegin',
    '<nav>' +
      '<a href="index.html" style="text-decoration:none;">' +
        '<span style="font-family: Poppins, sans-serif; font-size:22px; font-weight:800; color:#111; letter-spacing:-0.5px;">Lurker<span style="color:#1D9E75;">.</span></span>' +
      '</a>' +
      '<div class="nav-center">' +
        '<button class="nav-btn">X</button>' +
        '<button class="nav-btn">XX</button>' +
        '<button class="nav-btn">XXX</button>' +
      '</div>' +
      '<button class="user-btn" onclick="window.location.href=\'' + destination + '\'">' +
        '<div class="avatar" style="' + avatarStyle + '">U</div>' +
        '<span>' + label + '</span>' +
      '</button>' +
    '</nav>'
  );
});
