function giveOnchangeEvent(input) {
    document.getElementById('file').onchange = function() {
        document.getElementById('form1').submit();
    }
}
function delaySubmit(input, delay = 50) {
    setTimeout(function() {
        if (document.getElementById('url').value.startsWith('http')) {
            document.getElementById('form2').submit();
        }
    }, delay);
}
function toggleVisibility(input) {
    var e = document.getElementById('api-info');
    if (e.style.display == 'block')
        e.style.display = 'none';
    else
        e.style.display = 'block';
}
document.getElementById('file').addEventListener('focus', giveOnchangeEvent);
document.getElementById('url').addEventListener('paste', delaySubmit);
document.getElementById('api').addEventListener('click', toggleVisibility);