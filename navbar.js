document.addEventListener('DOMContentLoaded', function() {
  var isLoggedIn = localStorage.getItem('loggedIn') === 'true';
  var destination = isLoggedIn ? 'settings.html' : 'signup.html';
  var avatarStyle = isLoggedIn ? '' : 'display:none';
  var label = isLoggedIn ? 'Username' : 'Sign up';

  document.body.insertAdjacentHTML('afterbegin',
    '<nav>' +
      '<div class="nav-logo">Lurker<span>.</span></div>' +
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
