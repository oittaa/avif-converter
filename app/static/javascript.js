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
function toggleApiVisibility(input) {
    var e = document.getElementById('api-info');
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
document.getElementById('api').addEventListener('click', toggleApiVisibility);
document.getElementById('form2').addEventListener('submit', showSpinner);
