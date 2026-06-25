const isLoggedIn = localStorage.getItem('loggedIn') === 'true';

document.body.insertAdjacentHTML('afterbegin', `
  <nav>
    <div class="nav-logo">Lurker<span>.</span></div>
    <div class="nav-center">
      <button class="nav-btn">X</button>
      <button class="nav-btn">XX</button>
      <button class="nav-btn">XXX</button>
    </div>
    <button class="user-btn" id="userBtn" onclick="window.location.href='${isLoggedIn ? 'settings.html' : 'signup.html'}'">
      <div class="avatar" style="${isLoggedIn ? '' : 'display:none'}">U</div>
      <span>${isLoggedIn ? 'Username' : 'Sign up'}</span>
    </button>
  </nav>
`);
