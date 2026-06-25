document.addEventListener('DOMContentLoaded', function() {
  var isLoggedIn = localStorage.getItem('loggedIn') === 'true';
  var destination = isLoggedIn ? 'settings.html' : 'signup.html';
  var avatarStyle = isLoggedIn ? '' : 'display:none';
  var label = isLoggedIn ? 'Username' : 'Sign up';
  document.body.insertAdjacentHTML('afterbegin',
    '<nav>' +
      '<a href="index.html" style="display:flex; align-items:center; text-decoration:none;">' +
        '<img src="Lurker.png" alt="Lurker" style="height:40px; width:auto;">' +
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
