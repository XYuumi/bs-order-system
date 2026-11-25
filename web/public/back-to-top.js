;(function(){
  var bt = document.createElement("button");
  bt.className = "bs-backtop";
  bt.innerHTML = "&#8593;";
  bt.title = "返回顶部";
  bt.onclick = function() {
    window.scrollTo({top: 0, behavior: "smooth"});
    var main = document.querySelector(".el-main");
    if (main) main.scrollTo({top: 0, behavior: "smooth"});
  };
  document.body.appendChild(bt);
  function chk() {
    var y = window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
    bt.classList.toggle("show", y > 300);
  }
  window.addEventListener("scroll", chk, {passive: true, capture: true});
  setInterval(chk, 1000);
})();
