function giveOnchangeEvent(input) {
    document.getElementById('file').onchange = function() {
        showSpinner();
        document.getElementById('form1').submit();
    }
}
function delaySubmit(input, delay = 50) {
    setTimeout(function() {
        if (document.getElementById('url').value.startsWith('http')) {
            showSpinner();
            document.getElementById('form2').submit();
        }
    }, delay);
}
function toggleVisibility(id) {
    var e = document.getElementById(id);
    if (e.style.display == 'block')
        e.style.display = 'none';
    else
        e.style.display = 'block';
}
function showSpinner(){
  document.getElementById("spinner-back").classList.add("show");
  document.getElementById("spinner-front").classList.add("show");
}
function hideSpinner(){
  document.getElementById("spinner-back").classList.remove("show");
  document.getElementById("spinner-front").classList.remove("show");
}
document.getElementById('file').addEventListener('focus', giveOnchangeEvent);
document.getElementById('url').addEventListener('paste', delaySubmit);
document.getElementById('api').addEventListener('click', function() {
    toggleVisibility('api-info');
}, false);
document.getElementById('why').addEventListener('click', function() {
    toggleVisibility('why-info');
}, false);
document.getElementById('imgjpg').onclick = function() {
    this.classList.toggle('maxwidth');
}
document.getElementById('imgavif').onclick = function() {
    this.classList.toggle('maxwidth');
}
document.getElementById('form2').addEventListener('submit', showSpinner);
